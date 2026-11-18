"""G5 report (P7-T05, P7-T06 file): write → DỪNG gate_report → commit the report row, then the .md."""

import json
import re
from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.assistant_fix import SWAP, _problem_of_grade, world
from tests.db import test_profile_repo as prof
from tests.fakes import FakeLLM, lane_handlers
from tutor import llm
from tutor.agents.a09_reporter.reporter import ReportOut, Sentence
from tutor.api import errors
from tutor.db import repo
from tutor.graphs import report, session
from tutor.graphs.registry import make_runner
from tutor.graphs.runner import AlreadyCommitted, NotResumable, UndecidedItems
from tutor.services import facts

TODAY = date(2026, 10, 21)
WEEK = {"period_kind": "week", "period_start": "2026-10-12"}  # An: 1 session (14/10); previous week has 07/10


def writer(user, system):
    """09: up to 3 fact lines that hold a number, each citing itself, so they pass the audit."""
    lines = re.findall(r"^(F\d\d) · (.*\d.*)$", user, re.M)[:3]
    return ReportOut(sentences=[Sentence(text=t, facts=[f]) for f, t in lines])


@pytest.fixture
def g5(paths, conn):
    """(runner, conn, fake_llm, An's id)."""
    w = world(conn)
    llm.configure(paths.logs / "llm.jsonl", {})
    fake = FakeLLM({"09": writer} | lane_handlers())
    llm.set_backend(fake)
    r = make_runner(paths)
    yield r, conn, fake, w["an"]
    r.close()


def draft(paths, r, sid, period=WEEK):
    out = report.start(paths, r, student_id=sid, **period, today=TODAY)
    r.wait(out["thread_id"])
    return out


def approve(r, tid):
    r.resume(tid)
    return r.wait(tid)


def rows(conn):
    return conn.execute("SELECT student_id, period_kind, period_start, text_md, audit_json FROM report").fetchall()


def full_md(state):
    """The three-part text_md of a draft as it stands, untouched."""
    d = state["draft"]
    return report.text_md(report.sentences(state, None), d["sessions"], report.sentences(state, None, "plan"),
                          d["plan_title"])  # fmt: skip


def test_no_write_until_approve(g5, paths):
    """09 runs inside the runner's worker thread; nothing is written until approve."""
    r, conn, fake, sid = g5
    before = repo.row_counts(conn)
    out = draft(paths, r, sid)
    tid = out["thread_id"]
    row = r.get(tid)
    assert out == {"thread_id": "g5-hs01w-20261012", "status": "running", "existing": False}
    assert (row["status"], row["node"], row["graph"], row["error"]) == ("awaiting_review", "gate_report", "G5", None)
    assert (row["subject"], row["student_id"]) == ("HS-01 · báo cáo tuần 12/10/2026", sid)
    assert fake.count["09"] == 1
    assert repo.row_counts(conn) == before
    assert not report.report_file(paths, sid, "week", "2026-10-12").exists()  # R3: no draft .md
    logged = [x for x in llm.iter_log(paths.logs / "llm.jsonl") if x["agent"] == "09"]
    assert [(x["graph"], x["thread_id"], x["student_code"]) for x in logged] == [("G5", tid, "HS-01")]  # R15
    shown = report.sentences(r.state(tid), None)
    assert shown and all(s["flag"] is None and s["why"] is None and s["facts"] for s in shown)


def test_approve_writes_report_and_md(g5, paths):
    r, conn, _, sid = g5
    tid = draft(paths, r, sid)["thread_id"]
    row = approve(r, tid)
    assert row["status"] == "committed", row["error"]
    [(student_id, kind, start, md, audit)] = rows(conn)
    assert (student_id, kind, start) == (sid, "week", "2026-10-12")
    assert "[F0" in md and md == full_md(r.state(tid))
    f = report.report_file(paths, sid, "week", "2026-10-12")
    assert f == paths.out / "baocao-HS-01-week-2026-10-12.md"
    assert f.read_text(encoding="utf-8") == md  # P7-T06: the approved .md = report.text_md
    audit = json.loads(audit)
    assert set(audit) == {"writer", "approved", "approved_plan"} and audit["writer"] == r.state(tid)["draft"]["audit"]
    assert audit["approved"][0] == {"i": 0, "flag": None, "why": None}
    assert audit["approved_plan"] and all(a["flag"] is None for a in audit["approved_plan"])
    receipt = r.state(tid)["receipt"]
    assert repo.report_for(conn, sid, "week", "2026-10-12") == {"id": receipt["report_id"],
                                                                "approved_at": receipt["approved_at"]}  # fmt: skip
    assert repo.reports(conn) == repo.reports(conn, sid) == [
        {"id": receipt["report_id"], "student_id": sid, "period_kind": "week", "period_start": "2026-10-12",
         "approved_at": receipt["approved_at"]}]  # fmt: skip
    assert repo.report(conn, receipt["report_id"])["text_md"] == md
    with pytest.raises(repo.NotFound):
        repo.report(conn, receipt["report_id"] + 1)


def test_text_md_one_line_per_sentence():
    """R17: each sentence with its fact ids; a teacher sentence with none has no tail."""
    got = report.text_md([{"text": "Em học 1 buổi.", "facts": ["F01", "F03"]}, {"text": "Em cố gắng.", "facts": []}])
    assert got == "Em học 1 buổi. [F01][F03]\nEm cố gắng.\n"


NEW_MD = "## Các buổi học trong kỳ\nA. [F01]\n## Nhận xét\nB. [F02]\n## Lộ trình 4 tuần tới (16/11–13/12)\nC. [F09]\n"


def test_text_md_three_headings():
    md = report.text_md([{"text": "B.", "facts": ["F02"]}], [{"text": "A.", "facts": ["F01"]}],
                        [{"text": "C.", "facts": ["F09"]}], "Lộ trình 4 tuần tới (16/11–13/12)")  # fmt: skip
    assert md == NEW_MD


def test_text_md_old_format():
    assert report.text_md([{"text": "B.", "facts": ["F02"]}]) == "B. [F02]\n"


def test_sections_old_and_new():
    assert report.sections("B. [F02]\n") == [{"title": None, "lines": ["B."]}]
    assert report.sections(NEW_MD) == [
        {"title": "Các buổi học trong kỳ", "lines": ["A."]},
        {"title": "Nhận xét", "lines": ["B."]},
        {"title": "Lộ trình 4 tuần tới (16/11–13/12)", "lines": ["C."]},
    ]
    assert report.lines(NEW_MD) == ["A.", "B.", "C."]  # no headings, no fact ids


def test_md_file_has_headings(g5, paths):
    """The approved .md is text_md with the three parts, and the "Nhận xét" part holds the approved sentences."""
    r, conn, _, sid = g5
    tid = draft(paths, r, sid)["thread_id"]
    approve(r, tid)
    [(_, _, _, md, _)] = rows(conn)
    d = r.state(tid)["draft"]
    assert md == full_md(r.state(tid)) == report.report_file(paths, sid, "week", "2026-10-12").read_text("utf-8")
    assert [s["title"] for s in report.sections(md)] == ["Các buổi học trong kỳ", "Nhận xét", d["plan_title"]]
    assert "## Nhận xét\n" in md and [s["text"] for s in d["sentences"]] == report.sections(md)[1]["lines"]


def test_second_approval_blocked(g5, paths):
    """Review Focus 3: a period is approved once; another text never replaces the row or the .md."""
    r, conn, _, sid = g5
    tid = draft(paths, r, sid)["thread_id"]
    approve(r, tid)
    receipt = r.state(tid)["receipt"]
    f = report.report_file(paths, sid, "week", "2026-10-12")
    md = f.read_text(encoding="utf-8")
    with pytest.raises(repo.ReportApproved) as e:
        report.start(paths, r, student_id=sid, **WEEK, today=TODAY)
    assert (e.value.report_id, e.value.approved_at) == (receipt["report_id"], receipt["approved_at"])
    args = {"student_id": sid, **WEEK, "facts": [], "audit": {}}
    with pytest.raises(repo.ReportApproved):
        repo.commit_report(conn, **args, text_md="Câu khác.\n")
    assert repo.commit_report(conn, **args, text_md=md) == receipt  # same text: a rerun, nothing written
    assert len(rows(conn)) == 1 and f.read_text(encoding="utf-8") == md
    with pytest.raises(AlreadyCommitted):
        r.resume(tid)


def test_second_thread_of_approved_period(g5, paths, conn, monkeypatch):
    """Important 1: a start that read "not approved" just before thread A committed, then found no draft."""
    r, _, _, sid = g5
    a = draft(paths, r, sid)["thread_id"]
    approve(r, a)
    real, reads = repo.report_for, []

    def stale(*args):  # the first read happened before A committed its row
        reads.append(args)
        return None if len(reads) == 1 else real(*args)

    monkeypatch.setattr(repo, "report_for", stale)
    with pytest.raises(repo.ReportApproved):  # read again under the start lock
        report.start(paths, r, student_id=sid, **WEEK, today=TODAY)
    assert [t["thread_id"] for t in r.list_threads(graph="G5")] == [a]
    monkeypatch.setattr(repo, "report_for", lambda *args: None)  # both reads missed: B gets to its gate
    b = draft(paths, r, sid)["thread_id"]
    assert (b, r.get(b)["status"]) == (f"{a}-2", "awaiting_review")
    monkeypatch.setattr(repo, "report_for", real)
    with pytest.raises(repo.ReportApproved):  # 409 at resume, not a failed thread
        r.resume(b)
    assert r.get(b)["status"] == "awaiting_review" and len(rows(conn)) == 1


@pytest.mark.parametrize(("day", "stale"), [("2026-10-20", False), ("2026-10-16", True)])
def test_stale_draft_not_approved(g5, paths, conn, day, stale):
    """H13: a session approved in the period after the draft was written: approving would lock an old count.
    A later week's session only moves `repeat` (R9), so that draft still goes through."""
    r, _, _, sid = g5
    tid = draft(paths, r, sid)["thread_id"]
    p9, kc = _problem_of_grade(conn, 9)
    prof.commit(conn, prof.start(conn, sid, day), [(p9, [prof.mk(SWAP, kc)])])
    before = repo.row_counts(conn)
    if not stale:
        assert approve(r, tid)["status"] == "committed"
        return
    with pytest.raises(NotResumable) as e:
        r.resume(tid)
    assert str(e.value) == "Có buổi mới được duyệt trong kỳ này. Bỏ bản nháp rồi tạo lại."
    assert r.get(tid)["status"] == "awaiting_review" and repo.row_counts(conn) == before
    assert not rows(conn) and not report.report_file(paths, sid, "week", "2026-10-12").exists()


def test_write_uses_start_today(g5, paths, monkeypatch):
    """H7: write reads report_facts with the day start was given, not the wall clock."""
    r, _, _, sid = g5
    seen, real = [], facts.report_facts
    monkeypatch.setattr(facts, "report_facts", lambda *a, **k: seen.append(k["today"]) or real(*a, **k))
    tid = draft(paths, r, sid)["thread_id"]
    assert r.get(tid)["status"] == "awaiting_review" and seen == [TODAY, TODAY]  # start, then write


def test_write_empty_period_in_words(g5, paths, monkeypatch):
    """A period emptied between start and write: the thread fails with the words, not a code."""
    r, _, _, sid = g5
    real, n = facts.report_facts, []

    def flaky(*a, **k):
        if n:
            raise facts.NotReady({"reason": "no_committed_session"})
        n.append(1)
        return real(*a, **k)

    monkeypatch.setattr(facts, "report_facts", flaky)
    row = r.get(draft(paths, r, sid)["thread_id"])
    assert (row["status"], row["node"]) == ("failed", "write") and "Kỳ này chưa có buổi học nào đã duyệt" in row[
        "error"
    ]


def test_not_ready_lists_pending(g5, paths, conn):
    """An's week of 19/10 has only a G1 still waiting for review: 409 not_ready names it and the week before."""
    r, _, fake, sid = g5
    (paths.inbox / "a.tex").write_text("\\begin{problem}[9DS-BPT-001]\n$4x = 20$\n$x = 5$\n\\end{problem}\n",
                                       encoding="utf-8")  # fmt: skip
    g1 = session.submit(paths, r, student_id=sid, held_on="2026-10-20", rel_path="a.tex")["thread_id"]
    assert r.wait(g1)["status"] == "awaiting_review"
    before = repo.row_counts(conn)
    with pytest.raises(facts.NotReady) as e:
        report.start(paths, r, student_id=sid, period_kind="week", period_start="2026-10-19", today=TODAY)
    assert e.value.detail == {"reason": "no_committed_session", "pending": [{"thread_id": g1, "held_on": "2026-10-20"}],
                              "previous_start": "2026-10-12"}  # fmt: skip
    assert r.list_threads(graph="G5") == [] and fake.count["09"] == 0 and repo.row_counts(conn) == before
    with pytest.raises(ValueError, match="thứ Hai"):  # 422 before anything else
        report.start(paths, r, student_id=sid, period_kind="week", period_start="2026-10-20", today=TODAY)


def test_existing_draft_and_ids(g5, paths):
    """R16: one draft per period; C-05 ids differ by period kind even on the same start day."""
    r, _, fake, sid = g5
    first = draft(paths, r, sid)
    again = report.start(paths, r, student_id=sid, **WEEK, today=TODAY)
    assert again == {"thread_id": first["thread_id"], "status": "awaiting_review", "existing": True}
    assert fake.count["09"] == 1
    tids = [draft(paths, r, sid, {"period_kind": k, "period_start": s})["thread_id"]
            for k, s in (("day", "2026-10-14"), ("month", "2026-10-01"))]  # fmt: skip
    assert tids == ["g5-hs01d-20261014", "g5-hs01m-20261001"]
    assert [report.base_id("HS-01", k, "2026-06-01") for k in facts.KINDS] == [
        "g5-hs01d-20260601", "g5-hs01w-20260601", "g5-hs01m-20260601"]  # fmt: skip


def test_edits_reaudited(g5, paths, conn):
    """Review Focus 1: a teacher sentence is audited against every fact, flagged, and still approvable."""
    r, _, _, sid = g5
    tid = draft(paths, r, sid)["thread_id"]
    state = r.state(tid)
    kept = state["draft"]["sentences"][0]
    saved = {"sentences": [{"text": "Em làm 45 bài.", "facts": []}, kept,
                           {"text": "Em đúng 80% số ý.", "facts": kept["facts"]}]}  # fmt: skip
    assert r.save_decisions(tid, saved) == 0
    shown = report.sentences(state, saved)
    assert [s["flag"] for s in shown] == ["number", None, "percent"]
    assert shown[0]["why"] == "Số “45” không có trong dữ liệu đã duyệt." and shown[0]["facts"] == []
    one = report.sentences(state, {"sentences": [{"text": " Em làm\n1 bài. ", "facts": ["F99"]}]})
    assert one == [{"text": "Em làm 1 bài.", "facts": [], "flag": None, "why": None}]  # F99 cites nothing: every fact
    day = report.sentences(state, {"sentences": [{"text": "Buổi 14/10 em làm 1 bài.", "facts": []}]})
    assert day[0]["flag"] is None  # H3/H4: a session day of the period is no number
    typed = {"sentences": [{"text": "Em làm 1 bài [F07].", "facts": []}]}
    assert report.sentences(state, typed)[0]["text"] == "Em làm 1 bài."  # H9: C-44, no id on screen
    assert report.text_md(report.sentences(state, typed)) == "Em làm 1 bài.\n"
    assert report.pending(paths)(state, {"sentences": [{"text": " [F07] ", "facts": []}]}, "gate_report") == 1
    row = approve(r, tid)
    assert row["status"] == "committed", row["error"]
    audit = json.loads(rows(conn)[0][4])
    assert [(a["i"], a["flag"]) for a in audit["approved"]] == [(0, "number"), (1, None), (2, "percent")]
    assert "## Nhận xét\nEm làm 45 bài.\n" in rows(conn)[0][3]


@pytest.mark.parametrize("decisions", [{"sentences": []}, {"sentences": "x"}, {"sentences": [{"text": " "}]},
                                       {"sentences": [{"text": "a", "facts": "F01"}]}, ["x"]])  # fmt: skip
def test_malformed_or_empty_stays_undecided(g5, paths, decisions):
    r, _, _, sid = g5
    tid = draft(paths, r, sid)["thread_id"]
    assert r.save_decisions(tid, decisions) == 1


def test_rerun_after_file_error(g5, paths, conn, monkeypatch):
    """DB first, file second: a rerun finds the row with the same text and only writes the file."""
    r, _, _, sid = g5
    tid = draft(paths, r, sid)["thread_id"]
    real = Path.write_text

    def boom(self, *a, **k):
        if self.suffix == ".md":
            raise OSError("disk full")
        return real(self, *a, **k)

    monkeypatch.setattr(Path, "write_text", boom)
    row = approve(r, tid)
    assert (row["status"], row["node"]) == ("failed", "commit") and "disk full" in row["error"]
    assert len(rows(conn)) == 1
    monkeypatch.setattr(Path, "write_text", real)
    row = approve(r, tid)
    assert row["status"] == "committed", row["error"]
    assert len(rows(conn)) == 1
    assert report.report_file(paths, sid, "week", "2026-10-12").read_text(encoding="utf-8") == rows(conn)[0][3]


def test_period_errors_are_409():
    app = FastAPI()
    errors.install(app)

    @app.get("/approved")
    def approved():
        raise repo.ReportApproved(4, "2026-10-03T07:30:00Z")

    @app.get("/empty")
    def empty():
        raise facts.NotReady({"reason": "no_committed_session", "previous_start": None})

    c = TestClient(app)
    got = c.get("/approved")
    assert got.status_code == 409 and got.json()["error"]["code"] == "already_committed"
    assert got.json()["error"]["detail"] == {"report_id": 4, "approved_at": "2026-10-03T07:30:00Z"}
    got = c.get("/empty")
    assert got.status_code == 409 and got.json()["error"]["code"] == "not_ready"
    assert got.json()["error"]["detail"] == {"reason": "no_committed_session", "previous_start": None}


def test_readers_work_before_the_worker_runs(g5, paths, monkeypatch):
    r, _, _, sid = g5
    monkeypatch.setattr(r, "_submit", lambda *a, **k: None)  # worker never picks the job
    out = report.start(paths, r, student_id=sid, **WEEK, today=TODAY)
    tid = out["thread_id"]
    row, state = r.get(tid), r.state(tid)
    assert "draft" not in state and state["period_start"] == WEEK["period_start"]

    assert report.card(row, state) == {
        "kind": "report", "stage": "writing", "student_id": sid, **WEEK,
        "n_flagged": 0, "report_id": None, "error_words": None, "sentences": [],
        "sessions": [], "plan_title": None, "plan": [],
    }  # fmt: skip
    assert report.reminder(row, state) == {
        "kind": "report", "thread_id": tid, "student_id": sid, **WEEK, "words": "chưa làm xong",
    }  # fmt: skip
    assert report.drafts(r, sid) == []

    r._set(tid, status="failed", error="x")  # failed before the first node wrote a checkpoint
    row = r.get(tid)
    assert report.card(row, r.state(tid))["stage"] == "failed"
    (got,) = report.drafts(r, sid)
    assert (got["thread_id"], got["status"], got["n_flagged"]) == (tid, "failed", 0)
    assert (got["period_kind"], got["period_start"]) == (WEEK["period_kind"], WEEK["period_start"])


def _plan_state(paths, r, sid):
    tid = draft(paths, r, sid)["thread_id"]
    return tid, r.state(tid), report.card(r.get(tid), r.state(tid))


def test_draft_has_three_parts(g5, paths):
    """Part (a) from the session facts, (c) from facts.plan; 09 sees no plan line (C-40, spec 4.4)."""
    r, conn, fake, sid = g5
    n = conn.execute("SELECT count(*) FROM session WHERE student_id = ? AND status = 'committed'"
                     " AND held_on BETWEEN '2026-10-12' AND '2026-10-18'", (sid,)).fetchone()[0]  # fmt: skip
    tid, state, c = _plan_state(paths, r, sid)
    assert n == 1 and len(c["sessions"]) == n and c["plan"]
    assert c["plan_title"] == "Lộ trình 4 tuần tới (26/10–22/11)"  # the Monday after TODAY, not after 18/10
    assert all(s["flag"] is None and s["facts"] for s in c["plan"]) and c["n_flagged"] == 0
    d = state["draft"]
    by_id = {f["fact_id"]: f for f in d["facts"]}
    assert len(by_id) == len(d["facts"]) and [s["text"] for s in d["sessions"]] == c["sessions"]
    assert [by_id[s["facts"][0]]["kind"] for s in d["sessions"]] == ["session"] * n
    plan = [f for f in d["facts"] if f["kind"] == "plan"]
    assert [p["text"] for p in d["plan"]] == [f["text"] for f in plan] and d["plan_title"] == c["plan_title"]
    assert d["facts"][-len(plan) :] == plan and [p["facts"] for p in d["plan"]] == [[f["fact_id"]] for f in plan]
    assert {"2026-10-26", "2026-11-01"} <= set(d["dates"])  # week 1 bounds: the audit lets its dates through
    (call,) = [x for x in fake.calls if x["agent"] == "09"]
    assert not any(f["text"] in call["user"] for f in plan) and "Lộ trình" not in call["user"]
    assert any(f["text"] in call["user"] for f in d["facts"] if f["kind"] == "session")  # (a) still reaches 09


def test_plan_edits_reaudited(g5, paths):
    r, _, _, sid = g5
    tid, state, c = _plan_state(paths, r, sid)
    plain = [{"text": s["text"], "facts": s["facts"]} for s in c["sentences"]]
    week = state["draft"]["plan"][0]["text"].split(":")[0]
    pid = state["draft"]["plan"][0]["facts"][0]
    got = report.save(r, tid, {"sentences": plain, "plan": [{"text": f"{week}: làm 45 bài.", "facts": [pid]}]})
    assert got["pending"] == 0 and [a["flag"] for a in got["audit"]] == [None] * len(plain)
    assert [(a["i"], a["flag"]) for a in got["audit_plan"]] == [(0, "number")]
    assert got["audit_plan"][0]["why"] == "Số “45” không có trong dữ liệu đã duyệt."
    shown = report.card(r.get(tid), r.state(tid))
    assert [p["text"] for p in shown["plan"]] == [f"{week}: làm 45 bài."] and shown["n_flagged"] == 1
    with pytest.raises(ValueError):
        report.save(r, tid, {"sentences": plain, "plan": "x"})
    assert report.card(r.get(tid), r.state(tid))["n_flagged"] == 1  # a refused answer is not stored


def test_uncited_line_not_checked_against_plan_dates(g5, paths):
    """C-41: a line citing no fact is checked against the period's facts; plan dates must not become known numbers."""
    r, _, _, sid = g5
    _, state, _ = _plan_state(paths, r, sid)
    assert "2026-10-26" in json.dumps([f["value"] for f in state["draft"]["facts"] if f["kind"] == "plan"])
    for n in (26, 2026):
        got = report.sentences(state, {"sentences": [{"text": f"Em làm {n} bài.", "facts": []}]})
        assert [s["flag"] for s in got] == ["number"], n


def test_plan_missing_keeps_draft_plan(g5, paths):
    r, _, _, sid = g5
    tid, state, c = _plan_state(paths, r, sid)
    got = report.save(r, tid, {"sentences": [{"text": "Em cố gắng.", "facts": []}]})
    assert got["pending"] == 0 and got["audit_plan"] == [{"i": i, "flag": None, "why": None}
                                                         for i in range(len(c["plan"]))]  # fmt: skip
    card = report.card(r.get(tid), r.state(tid))
    assert [p["text"] for p in card["plan"]] == [p["text"] for p in state["draft"]["plan"]]
    row = approve(r, tid)
    assert row["status"] == "committed", row["error"]


def test_empty_plan_stays_undecided(g5, paths):
    r, _, _, sid = g5
    tid, _, _ = _plan_state(paths, r, sid)
    got = report.save(r, tid, {"sentences": [{"text": "Em cố gắng.", "facts": []}], "plan": []})
    assert got["pending"] == 1 and got["audit_plan"] == []
    with pytest.raises(UndecidedItems):
        r.resume(tid)
    report.save(
        r, tid, {"sentences": [{"text": "Em cố gắng.", "facts": []}], "plan": [{"text": "Ôn bài.", "facts": []}]}
    )
    row = approve(r, tid)
    assert row["status"] == "committed", row["error"]


def test_plan_edit_survives_approval(g5, paths, conn):
    """The approved plan is audited like the live one; its facts reach facts_json."""
    r, _, _, sid = g5
    tid, state, _ = _plan_state(paths, r, sid)
    pid = state["draft"]["plan"][0]["facts"]
    mine = [{"text": "Em ôn lại 99 bài.", "facts": pid}]
    report.save(r, tid, {"sentences": [{"text": "Em cố gắng.", "facts": []}], "plan": mine})
    assert approve(r, tid)["status"] == "committed"
    audit = json.loads(rows(conn)[0][4])
    assert [(a["i"], a["flag"]) for a in audit["approved_plan"]] == [(0, "number")]
    kinds = {f["kind"] for f in json.loads(conn.execute("SELECT facts_json FROM report").fetchone()[0])}
    assert {"session", "plan"} <= kinds


def test_old_draft_without_parts(paths):
    """Review Focus 1: a draft made before the three parts has no sessions/plan: it reads as before."""
    state = {"period_kind": "week", "period_start": "2026-10-12", "today": "2026-10-21",
             "draft": {"facts": [], "dates": [], "low": False, "audit": [],
                       "sentences": [{"text": "Em cố gắng.", "facts": []}]}}  # fmt: skip
    row = {"status": "awaiting_review", "student_id": 1, "decisions_json": None}
    pend = report.pending(paths)
    assert pend(state, None, "gate_report") == 0
    assert pend(state, {"sentences": [{"text": "Em ổn.", "facts": []}]}, "gate_report") == 0
    assert pend(state, {"sentences": []}, "gate_report") == 1
    assert report.sentences(state, None, "plan") == [] and report.sentences(state, {"sentences": []}, "plan") == []
    card = report.card(row, state)
    assert (card["sessions"], card["plan_title"], card["plan"], card["n_flagged"]) == ([], None, [], 0)
    assert [s["text"] for s in card["sentences"]] == ["Em cố gắng."]


def test_old_draft_still_approves(g5, paths, conn):
    """Review Focus 1: the checkpoint of a draft written before this change: saves, resumes, commits as before."""
    r, _, _, sid = g5
    tid, state, _ = _plan_state(paths, r, sid)
    d = state["draft"]
    old = {k: v for k, v in d.items() if k not in ("sessions", "plan", "plan_title")}
    old["facts"] = [f for f in d["facts"] if f["kind"] != "plan"]
    r.graphs["G5"].update_state({"configurable": {"thread_id": tid}}, {"draft": old}, as_node="write")
    got = report.card(r.get(tid), r.state(tid))
    assert (got["sessions"], got["plan_title"], got["plan"]) == ([], None, []) and got["sentences"]
    assert report.save(r, tid, {"sentences": d["sentences"]})["audit_plan"] == []
    assert approve(r, tid)["status"] == "committed"
    [(_, _, _, md, audit)] = rows(conn)
    assert md == report.text_md(d["sentences"]) and set(json.loads(audit)) == {"writer", "approved"}
