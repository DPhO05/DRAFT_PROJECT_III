"""P4-T04: node 05 profile + gate_confirm_commit between review and commit ②."""

import sqlite3

import pytest

from tests.db.test_profile_repo import skill_rows
from tests.fakes import FakeLLM, lane_handlers
from tests.graphs.g1 import THREE, approve, status
from tests.graphs.test_review import full
from tutor import llm
from tutor.db import repo
from tutor.graphs import runner as rmod
from tutor.graphs import session


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
    assert st["preview"] == {} and st["profile_prior"] == repo.profile_prior(conn, 1)


def test_commit_writes_exactly_the_preview(env):
    go, conn, r = env
    out, _, _ = go(THREE)
    tid = out["thread_id"]
    r.save_decisions(tid, full(conn))
    row = approve(r, tid)
    assert row["status"] == "committed"
    assert skill_event_rows(conn) == r.state(tid)["profile"]["events"]  # previewed numbers = written numbers
    assert r.state(tid)["receipt"]["skill_event"] == 3


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
    r.resume(a["thread_id"])
    assert r.wait(a["thread_id"])["status"] == "committed"
    after_a = max(e["theta_after"] for e in r.state(a["thread_id"])["profile"]["events"] if e["seq"] == 3)
    r.resume(b["thread_id"])
    row = r.wait(b["thread_id"])
    assert (row["status"], row["node"]) == ("awaiting_review", "gate_confirm_commit")  # back at the preview
    assert status(conn, b["session_id"]) == "awaiting_review"
    fresh = r.state(b["thread_id"])["profile"]
    assert fresh["events"][0]["theta_before"] == after_a != stale["events"][0]["theta_before"]
    assert r.state(b["thread_id"])["profile_prior"] == repo.profile_prior(conn, 1)
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
