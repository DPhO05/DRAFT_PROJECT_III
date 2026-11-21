"""P8b: the agent 00 eval harness end to end, with scripted FakeLLM instead of the API (C-34)."""

import json

import pytest

from tests.eval import agents, judges, metrics, run
from tests.fakes import FakeLLM
from tutor import llm
from tutor.agents.a00_orchestrator import orchestrator, tools
from tutor.agents.a09_reporter.reporter import ReportOut, Sentence


def test_00_oracle_passes_every_question(tmp_path):
    res = agents.evaluate_00(agents.oracle_00, work=tmp_path, runs=3)
    assert res["errors"] == [] and res["agent"] == "00" and res["runs"] == 3
    assert [q["id"] for q in agents.QUESTIONS] == [f"q{i}" for i in range(1, 21)]
    for s in res["metrics"]["per_run"]:
        assert (s["n_questions"], s["tools_ok"], s["args_ok"], s["unverified_pct"], s["passed"]) == (20, 1, 1, 0, 1)
    assert res["metrics"]["pass_k"] == 1 and res["metrics"]["extra"] == {"name_leaks": 0, "approval_ok": 1}
    assert list(res["prompt_versions"]) == ["00"] and len(res["prompt_versions"]["00"]) == 1


def test_00_tasks_are_wellformed():
    known = set(tools.LABELS)
    firsts = [q.get("masked", q["text"]) for q in agents.QUESTIONS]
    assert len(set(firsts)) == len(firsts) == 20
    for q in agents.QUESTIONS:
        named = {*q["expect"], *q["forbid"], *q.get("expect_args", {}), *q.get("max_calls", {}),
                 *q.get("fail_tools", []), *(c["name"] for step in q["script"] for c in step)} - {"*"}  # fmt: skip
        assert named <= known, q["id"]
    by_id = {q["id"]: q for q in agents.QUESTIONS}
    assert by_id["q18"]["expect_text"] == orchestrator.SAVED_NOTHING


def by_id(res, qid):
    [a] = [a for a in res["answers"][0] if a["id"] == qid]
    return a


def test_00_approval_decisions_reach_the_starter(tmp_path):
    res = agents.evaluate_00(agents.oracle_00, work=tmp_path, runs=1, only=["q11", "q12", "q13"])
    assert by_id(res, "q11")["starts"] == [["start_grading", 1, "hs01-a.tex", "2026-10-21"]]
    assert by_id(res, "q12")["starts"] == [] and by_id(res, "q12")["tool_errors"] == 1
    assert by_id(res, "q13")["starts"] == [["start_grading", 1, "hs01-c.tex", "2026-10-20"]]
    assert all(len(by_id(res, q)["approvals"]) == 1 for q in ("q11", "q12", "q13"))


def test_00_two_turn_tasks_share_one_thread(tmp_path):
    res = agents.evaluate_00(agents.oracle_00, work=tmp_path, runs=1, only=["q15", "q16"])
    assert by_id(res, "q15")["tools"] == ["student_mistakes"]
    assert by_id(res, "q16")["tools"] == ["rank_problems", "propose_worksheet"]
    assert res["metrics"]["pass_k"] == 1


def test_00_by_code_tasks_make_no_model_call(tmp_path):
    res = agents.evaluate_00(agents.oracle_00, work=tmp_path, runs=1, only=["q18", "q19"])
    assert by_id(res, "q18")["model_calls"] == by_id(res, "q19")["model_calls"] == 0
    assert by_id(res, "q19")["tools"] == ["find_problems"] and by_id(res, "q19")["text"] == ""


def test_00_full_name_never_reaches_the_model(tmp_path):
    res = agents.evaluate_00(agents.oracle_00, work=tmp_path / "w", runs=1, only=["q20"], traces=tmp_path / "tr")
    assert by_id(res, "q20")["leaks"] == 0 and by_id(res, "q20")["calls"][0]["args"] == {"code": "HS-01"}
    assert "Nguyễn Văn An" not in (tmp_path / "tr" / "run1-chat.json").read_text(encoding="utf-8")


def retry_q10(times):
    def make(conn):
        fake, models = agents.oracle_00(conn)
        right = fake.handlers["00"]

        def handle(messages):
            if agents.question_of(messages)["id"] != "q10":
                return right(messages)
            n = sum(m["role"] == "assistant" for m in messages)
            return (
                [{"type": "tool_use", "name": "start_bank_import", "input": {"file": "bai-moi.tex"}}]
                if n < times
                else right(messages)
            )

        fake.handlers["00"] = handle
        return fake, models

    return make


@pytest.mark.parametrize(("times", "ok"), [(1, True), (2, True), (3, False)])
def test_00_failing_tool_may_be_retried_once(tmp_path, times, ok):
    res = agents.evaluate_00(retry_q10(times), work=tmp_path, runs=1, only=["q10"])
    assert metrics.passed_00(by_id(res, "q10")) is ok


def repeat_after_reject(conn):
    fake, models = agents.oracle_00(conn)
    go = [{"type": "tool_use", "name": "start_grading",
           "input": {"code": "HS-01", "file": "hs01-b.tex", "held_on": "2026-10-21"}}]  # fmt: skip
    fake.handlers["00"] = lambda messages: (
        go if sum(m["role"] == "assistant" for m in messages) < 2 else [{"type": "text", "text": agents.DONE}]
    )
    return fake, models


def test_00_calling_again_after_a_reject_fails(tmp_path):
    res = agents.evaluate_00(repeat_after_reject, work=tmp_path, runs=1, only=["q12"])
    assert not metrics.passed_00(by_id(res, "q12")) and res["metrics"]["extra"]["approval_ok"] == 0


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
    assert s["tools_ok"] == 18 / 20 and s["unverified_pct"] == 100 / 20 and s["passed"] == 17 / 20
    assert res["metrics"]["pass_k"] == 17 / 20
    [q3] = [a for a in res["answers"][0] if a["id"] == "q3"]
    assert q3["text"] == "HS-01 sai 99 lần." and [w["kind"] for w in q3["warnings"]] == ["unverified_number"]


def test_00_one_failing_question_is_an_error_not_a_crash(tmp_path):
    res = agents.evaluate_00(broken_q4, work=tmp_path, runs=1)
    assert [e["id"] for e in res["errors"]] == ["q4"]
    assert res["metrics"]["per_run"][0]["n_questions"] == 20 and res["metrics"]["pass_k"] == 19 / 20


def test_00_tool_error_fails_the_question(tmp_path):
    res = agents.evaluate_00(unknown_student_q2, work=tmp_path, runs=1)
    [q2] = [a for a in res["answers"][0] if a["id"] == "q2"]
    assert q2["tools"] == ["student_profile"] and q2["tool_errors"] == 1  # called as expected, but it failed
    assert not metrics.passed_00(q2)
    assert res["metrics"]["per_run"][0]["tools_ok"] == 19 / 20


def test_09_oracle_passes_every_period(tmp_path):
    res = agents.evaluate_09(agents.oracle_09, work=tmp_path, runs=3)
    assert res["errors"] == [] and res["agent"] == "09"
    assert [p["key"] for p in agents.PERIODS] == [
        "HS-01 month 2026-10-01",
        "HS-01 week 2026-10-12",
        "HS-02 day 2026-10-14",
        "HS-01 day 2026-10-14",
        "HS-01 week 2026-10-05",
        "HS-02 week 2026-10-12 low",
    ]
    for s in res["metrics"]["per_run"]:
        assert (s["n_reports"], s["draft_flagged_pct"], s["dropped_pct"], s["passed"]) == (6, 0, 0, 1)
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
    assert res["metrics"]["per_run"][0]["flags"]["number"] == 6


def test_09_periods_cover_low_previous_and_no_previous(tmp_path):
    res = agents.evaluate_09(agents.oracle_09, work=tmp_path, runs=1)
    by_key = {r["key"]: r for r in res["reports"][0]}
    assert by_key["HS-02 week 2026-10-12 low"]["low"] is True
    assert sum(r["low"] for r in by_key.values()) == 1
    assert by_key["HS-01 day 2026-10-14"]["has_previous"] and not by_key["HS-01 week 2026-10-05"]["has_previous"]
    assert all(r["n_insights"] >= 1 and r["model_calls"] == 1 and r["leaks"] == 0 for r in by_key.values())


def test_raised_error_text_is_stored_without_a_student_name(tmp_path, monkeypatch):
    res = agents.evaluate_00(raising_q1_with_a_name, work=tmp_path / "a", runs=1, only=["q1"])
    assert "down" in res["errors"][0]["error"] and "Nguyễn Văn An" not in res["errors"][0]["error"]

    def boom(*args, **kw):
        raise ValueError("Trần Thị Bình")

    monkeypatch.setattr(agents.reporter, "run", boom)
    res = agents.evaluate_09(agents.oracle_09, work=tmp_path / "b", runs=1, only=["HS-02 day 2026-10-14"])
    assert "ValueError" in res["errors"][0]["error"] and "Trần Thị Bình" not in res["errors"][0]["error"]


def test_09_period_without_facts_is_an_error(tmp_path, monkeypatch):
    empty = {"key": "HS-02 day 2026-10-20", "code": "HS-02", "period_kind": "day", "period_start": "2026-10-20"}
    monkeypatch.setattr(agents, "PERIODS", [*agents.PERIODS, empty])
    res = agents.evaluate_09(agents.oracle_09, work=tmp_path, runs=1)
    assert [e["key"] for e in res["errors"]] == ["HS-02 day 2026-10-20"] and res["metrics"]["pass_k"] == 6 / 7


def raising_09_with_a_name(conn):
    fake, models = agents.oracle_09(conn)
    fake.handlers["09"] = lambda user, system: llm.LLMUnavailable("down: Nguyễn Văn An")
    return fake, models


def test_09_a_failed_period_keeps_its_leak_rows(tmp_path):
    res = agents.evaluate_09(raising_09_with_a_name, work=tmp_path, runs=1, only=["HS-02 day 2026-10-14"])
    assert [e["key"] for e in res["errors"]] == ["HS-02 day 2026-10-14"]
    assert "down" in res["errors"][0]["error"] and "Nguyễn Văn An" not in res["errors"][0]["error"]
    assert res["metrics"]["extra"]["name_leaks"] >= 1 and res["metrics"]["pass_k"] == 0


def test_09_masks_every_full_name(tmp_path, monkeypatch):
    """09's prompt holds no student name today; what is checked is that the context carries the app's mask map."""
    seen = []
    real = agents.reporter.run
    monkeypatch.setattr(agents.reporter, "run", lambda *a, **k: seen.append(k["ctx"]) or real(*a, **k))
    agents.evaluate_09(agents.oracle_09, work=tmp_path, runs=1)
    assert len(seen) == 6 and all(c.graph == "G5" for c in seen)
    assert seen[0].redact == {"Nguyễn Văn An": "HS-01", "Trần Thị Bình": "HS-02", "Lê Văn Cường": "HS-03"}
    assert [c.student_code for c in seen] == ["HS-01", "HS-01", "HS-02", "HS-01", "HS-01", "HS-02"]


@pytest.mark.parametrize("agent", ["00", "09", "g5"])
def test_real_backend_needs_yes(agent, monkeypatch, capsys):
    monkeypatch.setattr(agents, f"evaluate_{agent}", lambda *a, **k: pytest.fail("ran the real API without --yes"))
    assert run.main(["--agent", agent, "--backend", "real"]) == 2
    assert "tốn tiền" in capsys.readouterr().out


def test_main_fake_00_writes_result(tmp_path):
    assert run.main(["--agent", "00", "--backend", "fake", "--runs", "1", "--out", str(tmp_path / "results")]) == 0
    (out,) = (tmp_path / "results").glob("*_00-*.json")
    assert json.loads(out.read_text(encoding="utf-8"))["metrics"]["pass_k"] == 1
    assert len(list((tmp_path / "traces").glob("*_00/run1.jsonl"))) == 1


def test_00_each_run_starts_from_a_new_world(tmp_path):
    agents.evaluate_00(agents.oracle_00, work=tmp_path, runs=2, only=["q1"])
    assert (tmp_path / "run1" / "data" / "tutor.db").exists() and (tmp_path / "run2" / "data" / "tutor.db").exists()


def test_00_chat_trace_is_kept(tmp_path):
    agents.evaluate_00(agents.oracle_00, work=tmp_path / "w", runs=1, traces=tmp_path / "tr")
    chat_trace = json.loads((tmp_path / "tr" / "run1-chat.json").read_text(encoding="utf-8"))
    assert [c["id"] for c in chat_trace] == [q["id"] for q in agents.QUESTIONS]
    assert all(c["events"] and c["messages"] for c in chat_trace)
    assert (tmp_path / "tr" / "run1.jsonl").exists()


def test_only_runs_the_named_questions(tmp_path):
    res = agents.evaluate_00(agents.oracle_00, work=tmp_path, runs=1, only=["q4"])
    assert res["metrics"]["per_run"][0]["n_questions"] == 1 and res["metrics"]["pass_k"] == 1


def test_only_unknown_id_exits_2(capsys):
    assert run.main(["--agent", "00", "--backend", "fake", "--only", "q99"]) == 2
    assert "q99" in capsys.readouterr().out


def test_only_is_refused_for_g1(capsys):
    assert run.main(["--backend", "fake", "--only", "s01.tex"]) == 2


def test_set_the_agent_does_not_have_exits_2(capsys):
    assert run.main(["--agent", "00", "--backend", "fake", "--set", "g1-dev"]) == 2
    out = capsys.readouterr().out
    assert "g1-dev" in out and "00" in out


def test_00_result_has_calls_tally_and_models(tmp_path):
    res = agents.evaluate_00(agents.oracle_00, work=tmp_path, runs=1)
    assert res["calls"]["logged"] > 0 and isinstance(res["calls"]["usd"], float)
    assert set(res["calls"]["by_agent"]) == {"00"} and list(res["models"]) == ["00"]
    t = res["metrics"]["tally"]
    assert (t["trials_passed"], t["trials"], t["tasks_passed"], t["tasks"]) == (20, 20, 20, 20)
    assert res["metrics"]["success"] == 1 and res["metrics"]["extra"]["name_leaks"] == 0


def test_runs_below_one_exits_2(capsys):
    assert run.main(["--agent", "00", "--backend", "fake", "--runs", "0"]) == 2
    assert "--runs" in capsys.readouterr().out


def test_leak_count_reads_strings_not_json_text():
    names = {"Nguyễn Văn An": "HS-01"}
    rows = [{"user": {"turns": ["Nguyễn\\,Văn\\,An làm bài"]}}, {"user": ["Nguyễn Văn\nAn"]}, {"user": ["HS-01"]}]
    strings = [x for r in rows for x in agents._strings(r)]
    assert agents.leak_count(strings, names) == 2


def test_00_answer_records_calls_starts_and_model_calls(tmp_path):
    res = agents.evaluate_00(agents.oracle_00, work=tmp_path, runs=1, only=["q5", "q8"])
    q5, q8 = res["answers"][0]
    assert [c["name"] for c in q5["calls"]] == ["rank_problems", "propose_worksheet"]
    assert q5["calls"][0]["args"] == {"code": "HS-01", "n": 3} and q5["starts"][0][0] == "propose_worksheet"
    assert (q5["model_calls"], q8["model_calls"], q8["calls"], q8["starts"]) == (3, 1, [], [])


def wrong_args_q2(conn):
    fake, models = agents.oracle_00(conn)
    right = fake.handlers["00"]

    def handle(messages):
        turn = right(messages)
        if agents.question_of(messages)["id"] != "q2":
            return turn
        return [b | {"input": {"code": "HS-02"}} if b["type"] == "tool_use" else b for b in turn]

    fake.handlers["00"] = handle
    return fake, models


def test_00_wrong_argument_fails_the_question(tmp_path):
    res = agents.evaluate_00(wrong_args_q2, work=tmp_path, runs=1)
    s = res["metrics"]["per_run"][0]
    assert s["tools_ok"] == 1 and s["args_ok"] == 19 / 20 and s["passed"] == 19 / 20


def name_echo_q1(conn):
    fake, models = agents.oracle_00(conn)
    right = fake.handlers["00"]

    def handle(messages):
        turn = right(messages)
        if agents.question_of(messages)["id"] == "q1" and turn[0]["type"] == "text":
            return [{"type": "text", "text": "Lớp có bạn Nguyễn Văn An."}]
        return turn

    fake.handlers["00"] = handle
    return fake, models


def test_00_name_in_the_trace_fails_the_question(tmp_path):
    res = agents.evaluate_00(name_echo_q1, work=tmp_path, runs=1)
    [q1] = [a for a in res["answers"][0] if a["id"] == "q1"]
    assert q1["leaks"] >= 1 and not metrics.passed_00(q1) and res["metrics"]["extra"]["name_leaks"] >= 1


def raising_q1_with_a_name(conn):
    fake, models = agents.oracle_00(conn)
    right = fake.handlers["00"]

    def handle(messages):
        if agents.question_of(messages)["id"] == "q1" and any(m["role"] == "assistant" for m in messages):
            return llm.LLMUnavailable("down: Nguyễn Văn An")
        return right(messages)

    fake.handlers["00"] = handle
    return fake, models


def test_00_a_failed_task_keeps_its_leak_rows(tmp_path):
    res = agents.evaluate_00(raising_q1_with_a_name, work=tmp_path, runs=1)
    [q1] = [a for a in res["answers"][0] if a["id"] == "q1"]
    assert [e["id"] for e in res["errors"]] == ["q1"] and "down" in res["errors"][0]["error"]
    assert q1["leaks"] >= 1 and not metrics.passed_00(q1)
    assert res["metrics"]["extra"]["name_leaks"] >= 1 and res["metrics"]["tally"]["task_pass"]["q1"] is False


def test_g5_draft_reaches_the_gate_and_writes_no_report(tmp_path):
    res = agents.evaluate_g5(agents.oracle_09, work=tmp_path, runs=3)
    assert res["errors"] == [] and res["agent"] == "g5" and res["metrics"]["pass_k"] == 1
    for done in res["reports"]:
        [r] = done
        assert r["gate"] is True and r["report_rows"] == 0 and 1 <= r["model_calls"] <= 2
    assert list(res["prompt_versions"]) == ["09"]


def test_g5_failed_thread_is_an_error(tmp_path):
    def down(conn):
        return FakeLLM({"09": llm.LLMUnavailable("down")}), {}

    res = agents.evaluate_g5(down, work=tmp_path, runs=1)
    assert len(res["errors"]) == 1 and res["metrics"]["pass_k"] == 0


def test_09_judge_scores_every_report(tmp_path):
    res = agents.evaluate_09(judges.with_oracle(agents.oracle_09), work=tmp_path, runs=1, judge=True)
    assert res["metrics"]["extra"]["faithfulness"] == 1 and res["metrics"]["extra"]["judge_unknown"] == 0
    assert all(r["judge"]["score"] == 1 for r in res["reports"][0]) and res["calls"]["by_agent"]["judge"]["calls"] == 6


def test_00_judge_scores_only_marked_tasks(tmp_path):
    res = agents.evaluate_00(judges.with_oracle(agents.oracle_00), work=tmp_path, runs=1, judge=True)
    judged = [a["id"] for a in res["answers"][0] if a.get("judge")]
    assert judged == [q["id"] for q in agents.QUESTIONS if q.get("judge")] and len(judged) == 10
    assert res["metrics"]["extra"]["faithfulness"] == 1
    assert all("judge" not in a or {"judge_context", "judge_sentences"} <= a.keys() for a in res["answers"][0])


def test_g5_judge_scores_the_draft(tmp_path):
    res = agents.evaluate_g5(judges.with_oracle(agents.oracle_09), work=tmp_path, runs=1, judge=True)
    assert res["metrics"]["extra"]["faithfulness"] == 1 and res["metrics"]["pass_k"] == 1


def test_judge_never_changes_passed_or_the_call_count(tmp_path):
    plain = agents.evaluate_09(agents.oracle_09, work=tmp_path / "a", runs=1)
    judged = agents.evaluate_09(judges.with_oracle(agents.oracle_09), work=tmp_path / "b", runs=1, judge=True)
    assert judged["metrics"]["pass_k"] == plain["metrics"]["pass_k"]
    assert [r["model_calls"] for r in judged["reports"][0]] == [r["model_calls"] for r in plain["reports"][0]]


def test_judge_model_is_used_for_the_judge_rows(tmp_path):
    make = judges.with_oracle(agents.oracle_09)
    res = agents.evaluate_09(make, work=tmp_path, runs=1, only=[agents.PERIODS[0]["key"]], judge=True,
                             judge_model="openai:judge-x")  # fmt: skip
    assert res["models"]["judge"] == ["openai:judge-x"]


def test_without_judge_no_judge_row(tmp_path):
    res = agents.evaluate_09(agents.oracle_09, work=tmp_path, runs=1)
    assert "judge" not in res["calls"]["by_agent"] and res["metrics"]["extra"].get("faithfulness") is None


def test_judge_flag_rules(tmp_path, capsys):
    out = ["--out", str(tmp_path / "results")]
    assert run.main(["--agent", "09", "--backend", "dev", "--judge", *out]) == 2  # devfake has no judge
    assert run.main(["--agent", "01", "--backend", "fake", "--judge", *out]) == 2  # 01 has no judge
    assert run.main(["--agent", "09", "--backend", "real", "--judge", "--yes", *out]) == 2  # needs --judge-model
    assert run.main(["--agent", "09", "--backend", "fake", "--judge", "--judge-model", "x:y", *out]) == 2
    assert run.main(["--agent", "09", "--backend", "fake", "--judge", "--runs", "1", *out]) == 0
    assert "faithfulness=1.000  unknown=0" in capsys.readouterr().out


def test_judge_warns_when_it_shares_the_provider(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TUTOR_DATA", str(tmp_path))  # default settings, no key file
    monkeypatch.setattr(run.config, "load_env", lambda *_: None)
    monkeypatch.setitem(
        run.TARGETS["09"], "evaluate", lambda *a, **k: (_ for _ in ()).throw(agents.UnknownTask("stop"))
    )
    provider = llm.split_model(run.config.defaults()["models"]["09"])[0]
    other = "openai" if provider == "anthropic" else "anthropic"
    argv = ["--agent", "09", "--backend", "real", "--yes", "--judge", "--out", str(tmp_path / "results")]
    assert run.main([*argv, "--judge-model", f"{provider}:j"]) == 2
    assert "judge cùng nhà cung cấp" in capsys.readouterr().out
    assert run.main([*argv, "--judge-model", f"{other}:j"]) == 2
    assert "judge cùng nhà cung cấp" not in capsys.readouterr().out
