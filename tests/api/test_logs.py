"""P2-T08 / MONO-P2-02: /api/logs calls and cost from llm.jsonl."""

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.test_llm_openai import GBASE, GCTX, OK, RESP, ask, guarded
from tests.test_llm_provider import anthropic_model, msg
from tutor import llm

SAMPLE = Path(__file__).resolve().parents[1] / "fixtures" / "llm.jsonl"


@pytest.fixture
def logged(paths):
    shutil.copy(SAMPLE, paths.logs / "llm.jsonl")


def test_cost_equals_hand_computation(logged, client):
    c = client.get("/api/logs/cost?month=2026-10").json()
    # 0.011 + 0.045 + 0 + 0.003, see tests/test_llm.py
    assert c["month"] == "2026-10" and c["total_usd"] == 0.059 and c["calls"] == 4
    assert c["budget_usd"] == 30 and c["pct"] == pytest.approx(0.059 / 30)
    assert c["assumption"] is True and c["prices"]["cache_write_per_mtok"] == 6.25
    assert set(c["by_agent"]) == {"01", "02", "03"} and len(c["by_session"]) == 2


LABELS = ["Chấm bài", "Trợ lý", "Báo cáo", "Khác"]


def test_cost_parts_sum_to_total(logged, client):
    c = client.get("/api/logs/cost?month=2026-10").json()
    assert [p["label"] for p in c["parts"]] == LABELS
    assert sum(p["usd"] for p in c["parts"]) == pytest.approx(c["total_usd"], abs=1e-6)
    assert c["parts"][0]["usd"] == c["total_usd"]  # fixture holds only agents 01-03


def test_cost_parts_group_agents(paths, client):
    rows = [{"agent": a, "ts": "2026-11-01T08:00:00Z", "input_tokens": 10**6} for a in ("04", "00", "09", "05", None)]
    (paths.logs / "llm.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    c = client.get("/api/logs/cost?month=2026-11").json()
    assert [(p["label"], p["usd"]) for p in c["parts"]] == [
        ("Chấm bài", 5),
        ("Trợ lý", 5),
        ("Báo cáo", 5),
        ("Khác", 10),
    ]


def test_cost_parts_add_up_to_total(monkeypatch, client):
    # four lines of 1.4e-6 each: rounded one by one they total 4e-6, but total_usd is round(5.6e-6) = 6e-6
    by_agent = {a: {"calls": 1, "usd": 1.4e-6} for a in ("01", "00", "09", "05")}
    fake = {"total_usd": 6e-6, "calls": 4, "by_agent": by_agent, "by_session": []}
    monkeypatch.setattr("tutor.api.logs.cost", lambda *a, **k: fake)
    c = client.get("/api/logs/cost?month=2026-11").json()
    assert sum(p["usd"] for p in c["parts"]) == pytest.approx(c["total_usd"], abs=1e-9)
    assert all(p["usd"] >= 0 for p in c["parts"])


def test_cost_parts_add_up_with_cache_read_rows(paths, client):
    # cache-read-only rows cost 0.5e-6 or 1e-6 each: many agents, sub-micro amounts
    agents = ("00", "01", "02", "03", "04", "05", "09")
    rows = [
        {"agent": a, "ts": "2026-11-01T08:00:00Z", "cache_read_tokens": 1 + (i * 7 + j) % 3}
        for i, a in enumerate(agents)
        for j in range(5 + i)
    ]
    (paths.logs / "llm.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    c = client.get("/api/logs/cost?month=2026-11").json()
    assert 0 < c["total_usd"] < 1e-4
    assert sum(p["usd"] for p in c["parts"]) == pytest.approx(c["total_usd"], abs=1e-9)


@pytest.mark.parametrize(
    ("usd", "budget", "warning"),
    [
        (23.99, 30, None),
        (24, 30, "near"),
        (30, 30, "over"),
        (5, 0, None),
        (5.6, 7, "near"),
    ],  # 5.6 / 7 = 0.7999999999999999
)
def test_cost_warning_thresholds(paths, app, client, usd, budget, warning):
    app.state.settings["budget_usd_month"] = budget
    row = {"ts": "2026-11-01T08:00:00Z", "input_tokens": round(usd / 5 * 1e6)}  # input price is 5 USD per Mtok
    (paths.logs / "llm.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    c = client.get("/api/logs/cost?month=2026-11").json()
    assert c["total_usd"] == usd and c["warning"] == warning


def test_cost_by_model(paths, client):
    tok = {"input_tokens": 1000, "output_tokens": 200, "cache_read_tokens": 2000}
    rows = [
        {"model": m, "ts": f"2026-11-0{i}T08:00:00Z", **tok}
        for i, m in enumerate(["claude-opus-5-5", "openai:gpt-5.6-sol"], 1)
    ]
    (paths.logs / "llm.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    c = client.get("/api/logs/cost?month=2026-11").json()
    assert c["total_usd"] == 0.0198 and "openai:gpt-5.6-sol" in c["price_by_model"]
    items = client.get("/api/logs/calls").json()["items"]
    assert [i["cost_usd"] for i in items] == [0.0088, 0.011]


def test_filter_by_thread_returns_exactly_its_calls_newest_first(logged, client):
    r = client.get("/api/logs/calls?thread=g1-hs01-20261005").json()
    assert r["total"] == 2 and [(c["id"], c["thread_id"]) for c in r["items"]] == [
        (3, "g1-hs01-20261005"),
        (2, "g1-hs01-20261005"),
    ]
    assert [c["cost_usd"] for c in r["items"]] == [0.045, 0.011]
    page = client.get("/api/logs/calls?offset=1&limit=2").json()
    assert page["total"] == 5 and [c["id"] for c in page["items"]] == [5, 3]
    assert client.get("/api/logs/calls?agent=02&student=HS-02&graph=G1&month=2026-10").json()["total"] == 2


def test_call_detail_has_user_turn_and_output(logged, client):
    c = client.get("/api/logs/calls/2").json()
    assert c["prompt_version"] == "01-a1b2c3d4" and c["user"] == "Đề 8DS-PT1-001 của HS-01"
    assert c["output"] == '{"problems": []}' and c["cost_usd"] == 0.011
    assert client.get("/api/logs/calls/4").json()["error"]["code"] == "not_found"  # unreadable line
    assert client.get("/api/logs/calls/99").status_code == 404


def test_empty_log_and_default_month(client):
    assert client.get("/api/logs/calls").json() == {"items": [], "total": 0}
    c = client.get("/api/logs/cost").json()
    assert c["month"] == datetime.now(UTC).strftime("%Y-%m")
    assert c["total_usd"] == 0 and c["calls"] == 0 and c["by_agent"] == {} and c["by_session"] == []


def test_bad_month_is_rejected(client):
    assert client.get("/api/logs/cost?month=2026-1").status_code == 422
    assert client.get("/api/logs/calls?month=10-2026").status_code == 422


@pytest.fixture
def two_providers(paths, monkeypatch):
    """One real GuardedOpenAI call and one real GuardedAnthropic call, each over a mock transport, into llm.jsonl."""
    log = paths.logs / "llm.jsonl"
    llm.set_backend(None)
    monkeypatch.setattr(llm, "_chat", {})
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    llm.configure(log, {"01": "anthropic:claude-x"})
    m, _ = guarded(RESP(OK))
    ask(m)
    a, _ = anthropic_model(msg([{"type": "text", "text": "ok"}]))
    with llm.scope(GCTX, GBASE | {"agent": "01", "model": "anthropic:claude-x"}):
        a.invoke("hi")
    return log


def test_log_holds_both_providers_and_month_total_is_hand_computed(two_providers, client):
    month = datetime.now(UTC).strftime("%Y-%m")
    items = client.get("/api/logs/calls").json()["items"]
    assert sorted(i["model"] for i in items) == ["anthropic:claude-x", "openai:gpt-5.6-sol"]
    # openai (price_by_model 4 / 20 / 0.4 / 5): 3*4 + 6*20 + 1874*0.4 + 19*5 = 976.6 -> 0.000977
    # anthropic (default 5 / 25 / 0.5 / 6.25): 100*5 + 7*25 + 60*0.5 + 20*6.25 = 830 -> 0.00083
    assert {i["model"]: i["cost_usd"] for i in items} == {"openai:gpt-5.6-sol": 0.000977, "anthropic:claude-x": 0.00083}
    assert client.get(f"/api/logs/cost?month={month}").json()["total_usd"] == 0.001807


@pytest.mark.parametrize(("share", "warning"), [(0.79, None), (0.8, "near"), (0.99, "near"), (1, "over"), (2, "over")])
def test_two_provider_cost_warns_at_80_and_100_percent(two_providers, app, client, share, warning):
    app.state.settings["budget_usd_month"] = 0.001807 / share
    c = client.get(f"/api/logs/cost?month={datetime.now(UTC).strftime('%Y-%m')}").json()
    assert c["calls"] == 2 and c["warning"] == warning
