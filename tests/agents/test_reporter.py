"""P7-T04: agent 09 Reporter over MCP role 09 (design T9): facts in, cited sentences out, one rewrite at most."""

import json
from contextlib import closing
from datetime import date

import pytest

from tests.assistant_fix import world
from tests.fakes import FakeLLM
from tutor import config, llm
from tutor.agents import CallContext
from tutor.agents.a00_orchestrator.tools import Toolbox
from tutor.agents.a09_reporter import reporter
from tutor.agents.a09_reporter.reporter import ReportOut, Sentence
from tutor.db import repo
from tutor.mcp.client import connect
from tutor.services import facts

TODAY = date(2026, 10, 21)
MONTH = {"code": "HS-01", "period_kind": "month", "period_start": "2026-10-01"}
CTX = CallContext(graph="G5", thread_id="g5-hs01m-20261001", student_code="HS-01")


@pytest.fixture
def ro(conn, paths):
    w = world(conn)
    with closing(repo.connect(paths.tutor_db, readonly=True)) as c:
        yield c, w


def session(ro):
    return connect("09", Toolbox(ro[0], settings=config.defaults(), today=TODAY, text="", starters=None))


def fake(*turns):
    """FakeLLM answering 09 with `turns`, one per call; None = output off schema."""
    queue = list(turns)
    f = FakeLLM({"09": lambda user, system: queue.pop(0)})
    llm.set_backend(f)
    return f


def out(*sentences):
    """("text", "F01", …) per sentence."""
    return ReportOut(sentences=[Sentence(text=t, facts=list(ids)) for t, *ids in sentences])


# month of HS-01: F01 sessions = 2, F02 problems = 2, F04 session 07/10
DRAFT = out(("Tháng này em học 2 buổi.", "F01"), ("Em đã làm 5 bài.", "F02"), ("Em rất chăm chỉ.", "F99"))


def test_role_09_sees_only_its_tools(ro):
    s = session(ro)
    assert [t["name"] for t in s.tools()] == ["rank_problems", "report_facts"]
    content, is_error, _ = s.call("start_grading", {"code": "HS-01", "file": "a.tex", "held_on": "2026-10-21"})
    assert is_error and json.loads(content) == {"error": "Không có công cụ start_grading"}  # starters=None never ran
    content, is_error, meta = s.call("report_facts", MONTH)
    direct = facts.report_facts(ro[0], ro[1]["an"], "month", "2026-10-01", today=TODAY, low_pass_rate=0.5)
    assert (json.loads(content), is_error, meta) == (direct, False, {})


def test_report_facts_errors_in_words(ro):
    """R13: NotReady and a malformed period come back as a tool error in words; 09 then stops before any LLM call."""
    s = session(ro)
    for args, words in [
        (MONTH | {"period_start": "2026-09-01"}, "chưa có buổi học nào đã duyệt"),
        (MONTH | {"period_kind": "year"}, "Loại kỳ"),
        (MONTH | {"code": "HS-99"}, "Không có học sinh HS-99"),
    ]:
        content, is_error, _ = s.call("report_facts", args)
        assert is_error and words in json.loads(content)["error"]
    with pytest.raises(ValueError, match="chưa có buổi học nào đã duyệt"):
        reporter.run(s.call, **MONTH | {"period_start": "2026-09-01"}, ctx=CTX)


def test_rewrite_once_then_drop(ro):
    f = fake(DRAFT, out(("Em đã làm 2 bài.", "F02"), ("Em rất chăm chỉ.", "F99")))
    r = reporter.run(session(ro).call, **MONTH, ctx=CTX)
    assert f.count["09"] == 2
    assert [(a["i"], a["status"], a["flag"]) for a in r["audit"]] == [
        (0, "ok", None),
        (1, "rewritten", "number"),
        (2, "dropped", "no_fact"),
    ]
    assert r["sentences"] == [
        {"text": "Tháng này em học 2 buổi.", "facts": ["F01"]},
        {"text": "Em đã làm 2 bài.", "facts": ["F02"]},
    ]
    assert "F99" not in json.dumps(r)  # Review Focus 4
    first, again = f.calls[0]["user"], f.calls[1]["user"]
    assert again.startswith(first) and again.index("Em đã làm 5 bài.") < again.index("Em rất chăm chỉ.")


@pytest.mark.parametrize(
    ("again", "status"),
    [
        ((None, None), ["ok", "dropped", "dropped"]),
        ((out(("Em đã làm 2 bài.", "F02")),), ["ok", "rewritten", "dropped"]),
    ],
)
def test_failed_rewrite_drops(ro, again, status):
    """Rewrite off schema twice: every failed sentence dropped; one sentence short: the missing one dropped."""
    fake(DRAFT, *again)
    r = reporter.run(session(ro).call, **MONTH, ctx=CTX)
    assert [a["status"] for a in r["audit"]] == status
    assert len(r["sentences"]) == status.count("ok") + status.count("rewritten")


def test_schema_flag_on_first_call_raises(ro):
    fake(None, None)
    with pytest.raises(llm.SchemaFlag):
        reporter.run(session(ro).call, **MONTH, ctx=CTX)


def test_clean_draft_one_call(ro):
    f = fake(out(("Tháng này em học 2 buổi, làm 2 bài.", "F01", "F02"), ("Buổi 07/10 em đạt 1 trong 2 ý.", "F04")))
    r = reporter.run(session(ro).call, **MONTH, ctx=CTX)
    assert f.count["09"] == 1 and [a["status"] for a in r["audit"]] == ["ok", "ok"]
    user = f.calls[0]["user"]
    assert all(f"{x['fact_id']} · {x['text']}" in user.split("Số liệu:\n")[1] for x in r["facts"])
    assert all(f"{i['text']} ({', '.join(i['facts'])})" in user.split("Điểm cần nói:\n")[1] for i in r["insights"])
    assert r["insights"] and not any(x["kind"] == "suggestion" for x in r["facts"])  # no weak skill, no rank call


@pytest.mark.parametrize(
    ("kind", "start", "line"),
    [
        ("day", "2026-10-14", "Kỳ: ngày 14/10/2026"),
        ("week", "2026-10-12", "Kỳ: tuần 12/10–18/10/2026"),
        ("month", "2026-10-01", "Kỳ: tháng 10/2026"),
    ],
)
def test_period_line(ro, kind, start, line):
    f = fake(out(("Em đi học đều.", "F01")))
    reporter.run(session(ro).call, code="HS-01", period_kind=kind, period_start=start, ctx=CTX)
    assert line in f.calls[0]["user"].splitlines()


def test_low_period_no_praise(ro):
    """R23: 09 is told the result is low, and the audit's tone check rewrites praise all the same (C-41)."""
    settings = config.defaults()
    settings["report"]["low_pass_rate"] = 0.6  # 2 of 4 points
    s = connect("09", Toolbox(ro[0], settings=settings, today=TODAY, text="", starters=None))
    f = fake(out(("Tháng này em học 2 buổi, rất giỏi.", "F01")), out(("Tháng này em học 2 buổi.", "F01")))
    r = reporter.run(s.call, **MONTH, ctx=CTX)
    assert r["low"] is True and "Kết quả kỳ này thấp." in f.calls[0]["user"].splitlines()
    assert [(a["status"], a["flag"]) for a in r["audit"]] == [("rewritten", "tone")]
    assert r["sentences"] == [{"text": "Tháng này em học 2 buổi.", "facts": ["F01"]}]


def test_fact_ids_never_in_text(ro):
    """C-44: fact ids the model writes into a sentence are cut out; look-alikes such as F1, F012, AF01 stay."""
    look_alike = "Em làm 2 bài dạng F1, F012 và AF01."
    f = fake(out(
        ("Em làm 2 bài [F02].", "F02"),
        ("Em học 2 buổi, làm 2 bài (F01, F02).", "F01", "F02"),
        ("Buổi 07/10 [F04][F99] em đạt 1 trong 2 ý.", "F04"),
        ("F01 Em học 2 buổi F01.", "F01"),
        (look_alike, "F02"),
    ))  # fmt: skip
    r = reporter.run(session(ro).call, **MONTH, ctx=CTX)
    assert f.count["09"] == 1
    assert [s["text"] for s in r["sentences"]] == [
        "Em làm 2 bài.",
        "Em học 2 buổi, làm 2 bài.",
        "Buổi 07/10 em đạt 1 trong 2 ý.",
        "Em học 2 buổi.",
        look_alike,
    ]
    assert [a["text"] for a in r["audit"]] == [s["text"] for s in r["sentences"]]
    assert "Không viết mã số liệu vào chữ của câu." in reporter.INSTRUCTIONS


@pytest.mark.parametrize(
    ("text", "kept"),
    [
        ("[F01]", None),
        ("(F01) · .", None),
        ("· Em làm 2 bài.", "Em làm 2 bài."),
        ("F01 · Em làm 2 bài.", "Em làm 2 bài."),
    ],
)
def test_fact_line_leftovers(ro, text, kept):
    """H6: a sentence left with no words is dropped, never sent to rewrite; a copied "F01 · " or "· " prefix is cut."""
    f = fake(out((text, "F02")))
    r = reporter.run(session(ro).call, **MONTH, ctx=CTX)
    assert f.count["09"] == 1
    assert [s["text"] for s in r["sentences"]] == ([kept] if kept else [])
    assert r["audit"][0]["status"] == ("ok" if kept else "dropped")


def test_weak_skill_gets_suggestions(conn, ro):
    conn.execute("UPDATE skill_event SET theta_after = -1 WHERE kc_id = ?", (ro[1]["kc_swap"],))  # level from events
    s, calls = session(ro), []

    def call(name, args):
        calls.append((name, args))
        return s.call(name, args)

    f = fake(out(("Tháng này em học 2 buổi.", "F01")))
    r = reporter.run(call, **MONTH, ctx=CTX)
    assert calls == [("report_facts", MONTH), ("rank_problems", {"code": "HS-01", "n": 3})]
    sug = [x for x in r["facts"] if x["kind"] == "suggestion"]
    assert len(sug) == 1 and sug[0] is r["facts"][-1] and sug[0]["fact_id"] == f"F{len(r['facts']):02d}"
    assert 1 <= sug[0]["value"]["n"] <= 3 and sug[0]["value"]["kcs"]
    assert f"{sug[0]['fact_id']} · {sug[0]['text']}" in f.calls[0]["user"].split("Số liệu:\n")[1]


def test_payload_masked(conn, ro, tmp_path):
    """Review Focus 5: a skill named after a student is masked before 09 sees it and in llm.jsonl."""
    repo.update_kc(conn, ro[1]["kc_swap"], name="Ôn cho Nguyễn Văn An")
    everyone = repo.list_students(ro[0], include_archived=True)
    redact = {x["name"]: x["code"] for x in everyone if len(x["name"].split()) >= 2}  # as G1's call context
    log = tmp_path / "llm.jsonl"
    llm.configure(log, {})
    f = fake(out(("Tháng này em học 2 buổi.", "F01")))
    reporter.run(session(ro).call, **MONTH, ctx=CallContext(graph="G5", student_code="HS-01", redact=redact))
    assert "Văn An" not in f.calls[0]["user"] and "Ôn cho HS-01" in f.calls[0]["user"]
    rows = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
    assert [x["agent"] for x in rows] == ["09"] and rows[0]["prompt_version"].startswith("09-")
    assert "Văn An" not in log.read_text(encoding="utf-8")
