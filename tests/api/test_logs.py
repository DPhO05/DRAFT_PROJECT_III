"""P2-T08 / MONO-P2-02: /api/logs calls and cost from llm.jsonl."""

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

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
