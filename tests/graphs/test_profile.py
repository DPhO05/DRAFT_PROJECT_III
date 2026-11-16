"""P4-T04: node 05 profile + gate_confirm_commit between review and commit ②."""

import json
import re
import sqlite3

import pytest

from tests.bankfix import P2
from tests.db.test_profile_repo import skill_rows
from tests.fakes import FakeLLM, lane_handlers
from tests.graphs.g1 import THREE, approve, prob, status
from tests.graphs.test_review import full
from tutor import llm
from tutor.db import repo
from tutor.graphs import runner as rmod
from tutor.graphs import session, threads


def skill_event_rows(conn) -> list[dict]:
    cur = conn.execute(
        "SELECT a.seq, e.kc_id, e.outcome, e.p_expected, e.theta_before, e.theta_after, e.delta"
        " FROM skill_event e JOIN attempt a ON a.id = e.attempt_id ORDER BY e.id"
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur]


def submit(r, sid, day, name, text):
    """Another student / another file next to what `go` does; returns the thread id once G1 stops."""
    paths = r._paths_for_test
    llm.set_backend(FakeLLM(lane_handlers()))
    (paths.inbox / name).write_text(text, encoding="utf-8")
    tid = session.submit(paths, r, student_id=sid, held_on=day, rel_path=name)["thread_id"]
    r.wait(tid)
    return tid


def test_resume_at_review_stops_at_preview_not_commit(env):
    go, conn, r = env
    out, _, fake = go(THREE)
    tid = out["thread_id"]
    r.save_decisions(tid, full(conn))
    n_calls = len(fake.calls)
    before = repo.row_counts(conn)
    r.resume(tid)
    row = r.wait(tid)
    assert (row["status"], row["node"]) == ("awaiting_review", "gate_confirm_commit")
    assert repo.row_counts(conn) == before and len(fake.calls) == n_calls  # 0 writes, 0 LLM at 05
    assert status(conn, out["session_id"]) == "awaiting_review"
    st = r.state(tid)
    assert [(e["seq"], e["outcome"]) for e in st["profile"]["events"]] == [(1, 1), (2, 0), (3, 1)]
    assert st["profile_prior"] == repo.profile_prior(conn, 1)


def test_preview_words_have_no_numbers_or_codes(env):
    go, conn, r = env
    out, _, _ = go(THREE)
    tid = out["thread_id"]
    r.save_decisions(tid, full(conn))
    r.resume(tid)
    assert r.wait(tid)["node"] == "gate_confirm_commit"
    pv = r.state(tid)["preview"]
    assert pv["kcs"] == [
        {"kc": "Chuyển vế", "before": "đang hình thành", "after": "đang hình thành", "trend": "tiến bộ",
         "n_mistakes": 1}  # only p2's edit names the KC
    ]  # fmt: skip
    assert pv["miscon"] == {"new": ["Đáp số cuối sai dù các bước trước đúng (Chuyển vế)"], "again": [], "resolved": []}
    assert pv["codes"] == {
        "repeat": [], "gone": [],
        "new": ["Đáp số cuối sai dù các bước trước đúng", "Dùng sai ký hiệu", "Không xác định được loại lỗi"],
    }  # fmt: skip
    assert pv["writes"] == {"attempt": 3, "mistake": 4, "rubric": 0, "skill_event": 3, "skill_state": 1,
                            "misconception_log": 1}  # fmt: skip
    assert not re.search(r"θ|δ|\b[a-z]+\.[a-z_]+\b", json.dumps(pv, ensure_ascii=False))


def test_preview_without_any_kc_says_nothing_to_update(env):
    go, conn, r = env
    repo.add_bank_problem(conn, ref="X-001", statement="s", solution="s", source="t", delta=None, tags=[],
                          rubric_items=[{"item_id": "r1", "text": "t", "points": 1}])  # fmt: skip
    out, _, _ = go(prob("X-001", "LANE1 $x = 1$"))
    tid = out["thread_id"]
    r.save_decisions(tid, {"cards": {"p1": {"action": "accept"}}})
    r.resume(tid)
    assert r.wait(tid)["node"] == "gate_confirm_commit"
    pv = r.state(tid)["preview"]
    assert pv["kcs"] == [] and pv["miscon"] == {"new": [], "again": [], "resolved": []}
    assert pv["codes"]["new"] == ["Không xác định được loại lỗi"]
    assert pv["writes"] == {"attempt": 1, "mistake": 1, "rubric": 0, "skill_event": 0, "skill_state": 0,
                            "misconception_log": 0}  # fmt: skip


def test_preview_counts_rubrics_approved_at_step_3(env):
    go, conn, r = env
    out, _, _ = go(prob(P2[0], "LANE1 $m = -4$"))
    tid = out["thread_id"]
    r.save_decisions(tid, {"1": {"rubric_items": [{"item_id": "r1", "text": "m = -4", "points": 1}]}})
    r.resume(tid)
    assert r.wait(tid)["node"] == "gate_review"
    r.save_decisions(tid, {"cards": {"p1": {"action": "reject"}}})
    r.resume(tid)
    assert r.wait(tid)["node"] == "gate_confirm_commit"
    w = r.state(tid)["preview"]["writes"]
    assert (w["rubric"], w["mistake"]) == (1, 1)  # a rejected card still gets its row
    r.resume(tid)
    assert r.wait(tid)["status"] == "committed"
    rec = r.state(tid)["receipt"]
    assert w == {k: rec[k] for k in ("attempt", "mistake", "rubric", "skill_event")} | {
        "skill_state": 1, "misconception_log": 0}  # fmt: skip


def test_commit_writes_exactly_the_preview(env):
    go, conn, r = env
    out, _, _ = go(THREE)
    tid = out["thread_id"]
    r.save_decisions(tid, full(conn))
    row = approve(r, tid)
    assert row["status"] == "committed"
    assert skill_event_rows(conn) == r.state(tid)["profile"]["events"]  # previewed numbers = written numbers
    rec, w = r.state(tid)["receipt"], r.state(tid)["preview"]["writes"]
    assert rec["skill_event"] == 3
    assert {k: rec[k] for k in ("attempt", "mistake", "rubric", "skill_event")} == {
        k: w[k] for k in ("attempt", "mistake", "rubric", "skill_event")}  # fmt: skip


def test_two_students_three_sessions_equal_replay(env):
    go, conn, r = env
    s1 = 1
    s2 = repo.add_student(conn, name="Trần Thị Bình", grade=8)
    for n, day in enumerate(("2026-10-20", "2026-10-21", "2026-10-22")):
        for sid in (s1, s2):
            tid = submit(r, sid, day, f"{sid}-{n}.tex", THREE.replace("LANE", f"S{n}"))
            r.save_decisions(tid, full(conn))
            assert approve(r, tid)["status"] == "committed"
    before = skill_rows(conn)
    assert before["event"] and before["state"] and before["miscon"]
    for sid in (s1, s2):
        repo.replay_student(conn, sid)
    assert skill_rows(conn) == before


def test_decisions_frozen_at_confirm_commit(env):
    go, conn, r = env
    out, _, _ = go(THREE)
    tid = out["thread_id"]
    r.save_decisions(tid, full(conn))
    r.resume(tid)
    r.wait(tid)
    saved = r.get(tid)["decisions_json"]
    with pytest.raises(rmod.NotResumable):
        r.save_decisions(tid, {"cards": {}})
    assert r.get(tid)["decisions_json"] == saved


def test_prior_changed_meanwhile_recomputes_instead_of_committing_stale(env):
    go, conn, r = env
    a, _, _ = go(THREE, name="a.tex")
    b, _, _ = go(THREE.replace("LANE", "LAN"), name="b.tex")  # same student, same day: no date lock
    for t in (a, b):
        r.save_decisions(t["thread_id"], full(conn))
        r.resume(t["thread_id"])
        assert r.wait(t["thread_id"])["node"] == "gate_confirm_commit"
    stale = r.state(b["thread_id"])["profile"]
    assert stale["events"][0]["theta_before"] == 0
    pv = r.state(b["thread_id"])["preview"]
    assert (len(pv["miscon"]["new"]), pv["miscon"]["again"], pv["codes"]["repeat"]) == (1, [], [])
    r.resume(a["thread_id"])
    assert r.wait(a["thread_id"])["status"] == "committed"
    after_a = max(e["theta_after"] for e in r.state(a["thread_id"])["profile"]["events"] if e["seq"] == 3)
    counts = repo.row_counts(conn)
    r.resume(b["thread_id"])
    row = r.wait(b["thread_id"])
    assert (row["status"], row["node"]) == ("awaiting_review", "gate_confirm_commit")  # back at the preview
    assert repo.row_counts(conn) == counts  # the stale profile wrote nothing
    assert status(conn, b["session_id"]) == "awaiting_review"
    fresh = r.state(b["thread_id"])["profile"]
    assert fresh["events"][0]["theta_before"] == after_a != stale["events"][0]["theta_before"]
    assert r.state(b["thread_id"])["profile_prior"] == repo.profile_prior(conn, 1)
    pv = r.state(b["thread_id"])["preview"]  # recomputed with the rest: now A's mistakes are history
    assert (pv["miscon"]["new"], len(pv["miscon"]["again"]), len(pv["codes"]["repeat"])) == ([], 1, 3)
    r.resume(b["thread_id"])
    assert r.wait(b["thread_id"])["status"] == "committed"
    before = skill_rows(conn)
    repo.replay_student(conn, 1)
    assert skill_rows(conn) == before


def test_profile_failure_then_rerun_marks_session_awaiting_again(env, monkeypatch):
    go, conn, r = env
    out, _, _ = go(THREE)
    tid = out["thread_id"]
    r.save_decisions(tid, full(conn))
    real = repo.profile_prior
    monkeypatch.setattr(repo, "profile_prior", lambda *a: (_ for _ in ()).throw(sqlite3.OperationalError("gài")))
    r.resume(tid)
    assert r.wait(tid)["status"] == "failed" and status(conn, out["session_id"]) == "failed"
    monkeypatch.setattr(repo, "profile_prior", real)
    r.resume(tid)
    row = r.wait(tid)
    assert (row["status"], row["node"]) == ("awaiting_review", "gate_confirm_commit")
    assert status(conn, out["session_id"]) == "awaiting_review"


def test_commit_failed_then_other_session_commits_rerun_recomputes(env, monkeypatch):
    go, conn, r = env
    a, _, _ = go(THREE, name="a.tex")
    b, _, _ = go(THREE.replace("LANE", "LAN"), name="b.tex")
    for t in (a, b):
        r.save_decisions(t["thread_id"], full(conn))
        r.resume(t["thread_id"])
        assert r.wait(t["thread_id"])["node"] == "gate_confirm_commit"
    real, broken = repo.backup, [True]

    def flaky(*args):
        if broken and broken.pop():
            raise OSError("gài lỗi sao lưu")
        return real(*args)

    monkeypatch.setattr(repo, "backup", flaky)
    r.resume(b["thread_id"])
    row = r.wait(b["thread_id"])
    assert row["status"] == "failed" and "gài lỗi" in row["error"]
    r.resume(a["thread_id"])
    assert r.wait(a["thread_id"])["status"] == "committed"
    after_a = max(e["theta_after"] for e in r.state(a["thread_id"])["profile"]["events"] if e["seq"] == 3)
    counts = repo.row_counts(conn)
    r.resume(b["thread_id"])  # a rerun runs only commit: it must not write B's stale profile
    row = r.wait(b["thread_id"])
    assert (row["status"], row["node"]) == ("awaiting_review", "gate_confirm_commit")
    assert repo.row_counts(conn) == counts and status(conn, b["session_id"]) == "awaiting_review"
    assert r.state(b["thread_id"])["profile"]["events"][0]["theta_before"] == after_a
    r.resume(b["thread_id"])
    assert r.wait(b["thread_id"])["status"] == "committed"
    before = skill_rows(conn)
    repo.replay_student(conn, 1)
    assert skill_rows(conn) == before


def test_failed_commit_rerun_waits_for_earlier_session(env, monkeypatch):
    go, conn, r = env
    later, _, _ = go(THREE, name="l.tex", day="2026-10-20")
    tl = later["thread_id"]
    r.save_decisions(tl, full(conn))
    threads.resume(r, tl)
    assert r.wait(tl)["node"] == "gate_confirm_commit"
    real, broken = repo.backup, [True]

    def flaky(*args):
        if broken and broken.pop():
            raise OSError("gài lỗi sao lưu")
        return real(*args)

    monkeypatch.setattr(repo, "backup", flaky)
    threads.resume(r, tl)
    assert r.wait(tl)["status"] == "failed"
    early, _, _ = go(THREE.replace("LANE", "E"), name="e.tex", day="2026-10-17")
    te = early["thread_id"]
    threads.resume(r, tl)  # rerun: commit refuses, bounces to the gate
    row = r.wait(tl)
    assert (row["status"], row["node"]) == ("awaiting_review", "gate_confirm_commit")
    assert status(conn, later["session_id"]) == "awaiting_review"
    with pytest.raises(threads.ThreadLocked):
        threads.resume(r, tl)
    r.save_decisions(te, full(conn))
    assert approve(r, te)["status"] == "committed"
    threads.resume(r, tl)
    assert r.wait(tl)["node"] == "gate_confirm_commit"  # E is history now: preview recomputed
    threads.resume(r, tl)
    assert r.wait(tl)["status"] == "committed"
    before = skill_rows(conn)
    repo.replay_student(conn, 1)
    assert skill_rows(conn) == before


def test_commit_refuses_while_earlier_session_uncommitted(env):
    go, conn, r = env
    later, _, _ = go(THREE, name="l.tex", day="2026-10-20")
    early, _, _ = go(THREE.replace("LANE", "E"), name="e.tex", day="2026-10-17")
    before = repo.row_counts(conn)
    with pytest.raises(repo.StaleProfile):  # a commit already in flight meets the rule inside its transaction
        repo.commit_session(conn, later["session_id"], transcript="", review_seconds=None, attempts=[])
    assert repo.row_counts(conn) == before and status(conn, later["session_id"]) == "awaiting_review"
