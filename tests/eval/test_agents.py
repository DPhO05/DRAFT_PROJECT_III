"""P8b: the agent 00 eval harness end to end, with scripted FakeLLM instead of the API (C-34)."""

import json

import pytest

from tests.eval import agents, metrics, run
from tutor import llm
from tutor.agents.a09_reporter.reporter import ReportOut, Sentence


def test_00_oracle_passes_every_question(tmp_path):
    res = agents.evaluate_00(agents.oracle_00, work=tmp_path, runs=3)
    assert res["errors"] == [] and res["agent"] == "00" and res["runs"] == 3
    assert [q["id"] for q in agents.QUESTIONS] == [f"q{i}" for i in range(1, 9)]
    for s in res["metrics"]["per_run"]:
        assert s == {"n_questions": 8, "tools_ok": 1, "unverified_pct": 0, "passed": 1}
    assert res["metrics"]["pass_k"] == 1
    assert list(res["prompt_versions"]) == ["00"] and len(res["prompt_versions"]["00"]) == 1


def test_00_prompt_version_is_the_apps(tmp_path):
    res = agents.evaluate_00(agents.oracle_00, work=tmp_path, runs=1)
    assert res["prompt_versions"]["00"] == [res["app_version"]]


def wrong_00(conn):
    """q2 asks for mistakes, not the profile; q3 states a number no tool returned; q6 looks up a missing ref."""
    fake, models = agents.oracle_00(conn)
    right = fake.handlers["00"]

    def handle(messages):
        turn, qid = right(messages), agents.question_of(messages)["id"]
        if qid == "q2":
            return [b | {"name": "student_mistakes"} if b["type"] == "tool_use" else b for b in turn]
        if qid == "q3" and turn[0]["type"] == "text":
            return [{"type": "text", "text": "HS-01 sai 99 lần."}]
        if qid == "q6" and turn[0]["type"] == "tool_use":
            return [{"type": "tool_use", "name": "find_problems", "input": {"refs": ["ZZ-000"]}}]
        return turn

    fake.handlers["00"] = handle
    return fake, models


def broken_q4(conn):
    fake, models = agents.oracle_00(conn)
    right = fake.handlers["00"]
    fake.handlers["00"] = lambda messages: (
        llm.LLMUnavailable("down") if agents.question_of(messages)["id"] == "q4" else right(messages)
    )
    return fake, models


def unknown_student_q2(conn):
    fake, models = agents.oracle_00(conn)
    right = fake.handlers["00"]

    def handle(messages):
        turn = right(messages)
        if agents.question_of(messages)["id"] != "q2":
            return turn
        return [b | {"input": {"code": "HS-99"}} if b["type"] == "tool_use" else b for b in turn]

    fake.handlers["00"] = handle
    return fake, models


def test_00_wrong_oracle_scores_drop(tmp_path):
    res = agents.evaluate_00(wrong_00, work=tmp_path, runs=2)
    s = res["metrics"]["per_run"][0]
    assert s["tools_ok"] == 6 / 8 and s["unverified_pct"] == 100 / 8 and s["passed"] == 5 / 8
    assert res["metrics"]["pass_k"] == 5 / 8
    [q3] = [a for a in res["answers"][0] if a["id"] == "q3"]
    assert q3["text"] == "HS-01 sai 99 lần." and [w["kind"] for w in q3["warnings"]] == ["unverified_number"]


def test_00_one_failing_question_is_an_error_not_a_crash(tmp_path):
    res = agents.evaluate_00(broken_q4, work=tmp_path, runs=1)
    assert [e["id"] for e in res["errors"]] == ["q4"]
    assert res["metrics"]["per_run"][0]["n_questions"] == 7 and res["metrics"]["pass_k"] == 7 / 8


def test_00_tool_error_fails_the_question(tmp_path):
    res = agents.evaluate_00(unknown_student_q2, work=tmp_path, runs=1)
    [q2] = [a for a in res["answers"][0] if a["id"] == "q2"]
    assert q2["tools"] == ["student_profile"] and q2["tool_errors"] == 1  # called as expected, but it failed
    assert not metrics.passed_00(q2)
    assert res["metrics"]["per_run"][0]["tools_ok"] == 7 / 8


def test_09_oracle_passes_every_period(tmp_path):
    res = agents.evaluate_09(agents.oracle_09, work=tmp_path, runs=3)
    assert res["errors"] == [] and res["agent"] == "09"
    assert [p["key"] for p in agents.PERIODS] == [
        "HS-01 month 2026-10-01",
        "HS-01 week 2026-10-12",
        "HS-02 day 2026-10-14",
    ]
    for s in res["metrics"]["per_run"]:
        assert s == {"n_reports": 3, "draft_flagged_pct": 0, "dropped_pct": 0, "passed": 1}
    assert res["metrics"]["pass_k"] == 1 and list(res["prompt_versions"]) == ["09"]


def wrong_09(conn):
    """One draft sentence states a number its fact does not have; the rewrite repeats it, so it is dropped."""
    fake, models = agents.oracle_09(conn)
    right = fake.handlers["09"]
    bad = Sentence(text="Em làm 99 bài.", facts=["F01"])

    def handle(user, system):
        if "Câu cần viết lại" in user:
            return ReportOut(sentences=[bad])
        return ReportOut(sentences=[*right(user, system).sentences, bad])

    fake.handlers["09"] = handle
    return fake, models


def test_09_bad_number_is_dropped_after_one_rewrite(tmp_path):
    res = agents.evaluate_09(wrong_09, work=tmp_path, runs=1)
    assert all(sum(a["status"] == "dropped" for a in r["audit"]) == 1 for r in res["reports"][0])
    assert res["metrics"]["pass_k"] == 0


def test_09_period_without_facts_is_an_error(tmp_path, monkeypatch):
    empty = {"key": "HS-02 day 2026-10-20", "code": "HS-02", "period_kind": "day", "period_start": "2026-10-20"}
    monkeypatch.setattr(agents, "PERIODS", [*agents.PERIODS, empty])
    res = agents.evaluate_09(agents.oracle_09, work=tmp_path, runs=1)
    assert [e["key"] for e in res["errors"]] == ["HS-02 day 2026-10-20"] and res["metrics"]["pass_k"] == 3 / 4


def test_09_masks_every_full_name(tmp_path, monkeypatch):
    """09's prompt holds no student name today; what is checked is that the context carries the app's mask map."""
    seen = []
    real = agents.reporter.run
    monkeypatch.setattr(agents.reporter, "run", lambda *a, **k: seen.append(k["ctx"]) or real(*a, **k))
    agents.evaluate_09(agents.oracle_09, work=tmp_path, runs=1)
    assert len(seen) == 3 and all(c.graph == "G5" for c in seen)
    assert seen[0].redact == {"Nguyễn Văn An": "HS-01", "Trần Thị Bình": "HS-02", "Lê Văn Cường": "HS-03"}
    assert [c.student_code for c in seen] == ["HS-01", "HS-01", "HS-02"]


@pytest.mark.parametrize("agent", ["00", "09"])
def test_real_backend_needs_yes(agent, monkeypatch, capsys):
    monkeypatch.setattr(agents, f"evaluate_{agent}", lambda *a, **k: pytest.fail("ran the real API without --yes"))
    assert run.main(["--agent", agent, "--backend", "real"]) == 2
    assert "tốn tiền" in capsys.readouterr().out


def test_main_fake_00_writes_result(tmp_path):
    assert run.main(["--agent", "00", "--backend", "fake", "--runs", "1", "--out", str(tmp_path)]) == 0
    (out,) = tmp_path.glob("*_00-*.json")
    assert json.loads(out.read_text(encoding="utf-8"))["metrics"]["pass_k"] == 1
