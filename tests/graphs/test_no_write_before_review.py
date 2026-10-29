"""P3-T10 (NFR4, NFR5): on every G1 path tutor.db changes only the session row until commit ②."""

import sqlite3

import pytest

from tests.bankfix import P1, P2
from tests.fakes import lane_handlers
from tests.graphs.g1 import THREE, prob
from tests.graphs.test_review import full
from tutor.agents import ingest
from tutor.db import repo
from tutor.graphs import runner as rmod
from tutor.graphs import threads


def snapshot(conn) -> dict:
    """Every row of every table except session."""
    return {t: conn.execute(f"SELECT * FROM {t} ORDER BY rowid").fetchall() for t in repo.TABLES if t != "session"}


def no_flags(go, conn, r):
    out, _, _ = go(THREE)
    return out["thread_id"]


def low_match(go, conn, r):
    h = lane_handlers() | {"01": ingest.MatchResult(candidates=[ingest.Candidate(ref=P1[0], score=0.5)])}
    out, _, _ = go(prob(None, "LANE1 $4x = 20$"), handlers=h)
    tid = out["thread_id"]
    with pytest.raises(rmod.UndecidedItems):
        r.resume(tid)
    r.save_decisions(tid, {"1": {"problem_ref": P1[0]}})
    r.resume(tid)
    r.wait(tid)
    return tid


def rubric_at_step_3(go, conn, r):
    out, _, _ = go(prob(P2[0], "LANE1 $m = -4$"))
    tid = out["thread_id"]
    r.save_decisions(tid, {"1": {"rubric_items": [{"item_id": "r1", "text": "m = -4", "points": 1}]}})
    r.resume(tid)
    r.wait(tid)
    return tid


def lane_failure_then_rerun(go, conn, r):
    failed = []

    def boom(user):
        if not failed:
            failed.append(1)
            return RuntimeError("gài lỗi 03")
        return None

    out, row, _ = go(THREE, handlers=lane_handlers(fail_03=boom))
    assert row["status"] == "failed"
    r.resume(out["thread_id"])
    r.wait(out["thread_id"])
    return out["thread_id"]


@pytest.mark.parametrize("path", [no_flags, low_match, rubric_at_step_3, lane_failure_then_rerun])
def test_only_session_row_changes_until_commit(env, monkeypatch, path):
    go, conn, r = env
    before = snapshot(conn)
    tid = path(go, conn, r)
    assert r.get(tid)["node"] == "gate_review"
    n = len(r.state(tid)["proposals"])
    # pause with nothing decided, then with all but one: no command may commit
    for partial in ({"cards": {}}, {"cards": dict(list(full(conn)["cards"].items())[: n - 1])}):
        r.save_decisions(tid, partial)
        with pytest.raises(rmod.UndecidedItems):
            threads.resume(r, tid)
    assert snapshot(conn) == before
    # a failure inside commit ② rolls back to the same state
    r.save_decisions(tid, {"cards": {p["pid"]: {"action": "accept"} for p in r.state(tid)["proposals"]}})
    monkeypatch.setattr(repo, "_insert_mistake", lambda *a: (_ for _ in ()).throw(sqlite3.OperationalError("gài")))
    threads.resume(r, tid)
    assert r.wait(tid)["status"] == "failed" and snapshot(conn) == before
    monkeypatch.undo()
    threads.resume(r, tid)
    assert r.wait(tid)["status"] == "committed" and snapshot(conn) != before


def test_cancel_leaves_no_trace(env):
    go, conn, r = env
    before, sessions = snapshot(conn), repo.row_counts(conn)["session"]
    out, _, _ = go(THREE)
    r.save_decisions(out["thread_id"], full(conn))
    threads.cancel(r, r._paths_for_test, out["thread_id"])
    assert snapshot(conn) == before and repo.row_counts(conn)["session"] == sessions
