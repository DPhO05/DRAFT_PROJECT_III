"""P8b: the agent 00 eval harness end to end, with scripted FakeLLM instead of the API (C-34)."""

from tests.eval import agents, metrics
from tutor import llm


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
