"""P3-T03 queue + date lock (C-28), P3-T08 cancel (C-15) / cleanup."""

import pytest
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from tests.graphs.g1 import THREE, approve
from tests.graphs.test_review import full
from tutor.db import repo
from tutor.graphs import runner as rmod
from tutor.graphs import threads


def row(tid, held_on, status, graph="G1", student_id=1, updated_at="2026-10-20T00:00:00Z"):
    return {"thread_id": tid, "graph": graph, "student_id": student_id, "held_on": held_on, "status": status,
            "updated_at": updated_at, "running": status == "running"}  # fmt: skip


@pytest.mark.parametrize("blocker", ["awaiting_review", "failed", "running"])
def test_earlier_session_not_committed_locks_later_one(blocker):
    rows = threads.annotate([row("b", "2026-10-17", blocker), row("a", "2026-10-20", "awaiting_review")])
    a = rows[1]
    assert a["locked"] and a["blocking_thread_id"] == "b"
    assert (a["blocking_held_on"], a["blocking_status"]) == ("2026-10-17", blocker)
    assert "17/10" in a["lock_reason"] and "HS-01" in a["lock_reason"]


def test_committed_earlier_session_unlocks():
    rows = threads.annotate([row("b", "2026-10-17", "committed"), row("a", "2026-10-20", "awaiting_review")])
    assert rows[1]["locked"] is False and rows[1]["blocking_thread_id"] is None
    assert (rows[1]["blocking_held_on"], rows[1]["blocking_status"]) == (None, None)


def test_lock_only_same_student_earlier_g1():
    rows = threads.annotate([
        row("x", "2026-10-17", "awaiting_review", student_id=2),
        row("y", "2026-10-25", "awaiting_review"),
        row("g", None, "awaiting_review", graph="G4"),
        row("a", "2026-10-20", "awaiting_review"),
    ])  # fmt: skip
    assert [r["locked"] for r in rows] == [False, True, False, False]  # y waits for a, not for x or g
    assert rows[1]["blocking_thread_id"] == "a"


def test_earliest_blocker_is_named():
    rows = threads.annotate([row("c", "2026-10-18", "failed"), row("b", "2026-10-17", "awaiting_review"),
                             row("a", "2026-10-20", "awaiting_review")])  # fmt: skip
    assert rows[2]["blocking_thread_id"] == "b"


def test_queue_orders_g1_by_student_then_date_then_other_graphs():
    rows = [
        row("g5", None, "awaiting_review", graph="G5", updated_at="2026-10-19T00:00:00Z"),
        row("g4", None, "awaiting_review", graph="G4", updated_at="2026-10-21T00:00:00Z"),
        row("s2", "2026-10-10", "awaiting_review", student_id=2),
        row("s1b", "2026-10-20", "awaiting_review"),
        row("s1a", "2026-10-17", "awaiting_review"),
        row("f", "2026-10-01", "failed"),
    ]
    assert [r["thread_id"] for r in threads.queue(rows)] == ["s1a", "s1b", "s2", "g4", "g5"]


# ---------------------------------------------------------------- with the real G1 graph


def test_resume_of_locked_thread_raises_until_earlier_commits(env):
    go, conn, r = env
    first, _, _ = go(THREE, day="2026-10-17")
    later, _, _ = go(THREE.replace("LANE", "LAN"), name="b.tex", day="2026-10-20")
    r.save_decisions(later["thread_id"], full(conn))
    with pytest.raises(threads.ThreadLocked) as e:
        threads.resume(r, later["thread_id"])
    assert e.value.blocking_thread_id == first["thread_id"]
    r.save_decisions(first["thread_id"], full(conn))
    assert approve(r, first["thread_id"])["status"] == "committed"
    assert approve(r, later["thread_id"])["status"] == "committed"


def test_cancel_g1_awaiting_deletes_session_and_checkpoints(env):
    go, conn, r = env
    out, _, _ = go(THREE)
    before = repo.row_counts(conn)
    assert threads.cancel(r, r._paths_for_test, out["thread_id"]) == {
        "cancelled": out["thread_id"],
        "session_deleted": 1,
    }
    assert not r.exists(out["thread_id"])
    after = repo.row_counts(conn)
    assert {k: before[k] - after[k] for k in after if after[k] != before[k]} == {"session": 1}
    n = r._saver_conn.execute("SELECT count(*) FROM checkpoints WHERE thread_id = ?", (out["thread_id"],))
    assert n.fetchone()[0] == 0
    again, row, _ = go(THREE)  # same file, same day: no duplicate_submission, no date lock (C-15)
    assert row["status"] == "awaiting_review"


def test_cancel_committed_or_running_is_refused(env):
    go, conn, r = env
    out, _, _ = go(THREE)
    r.save_decisions(out["thread_id"], full(conn))
    approve(r, out["thread_id"])
    with pytest.raises(rmod.AlreadyCommitted):
        threads.cancel(r, r._paths_for_test, out["thread_id"])


def gate_graph():
    g = StateGraph(dict)
    g.add_node("work", lambda s: {"x": 1})
    g.add_node("gate", lambda s: interrupt({"gate": "x"}) and {})
    g.add_edge(START, "work")
    g.add_edge("work", "gate")
    g.add_edge("gate", END)
    return g


def test_cancel_other_graph_leaves_tutor_db_alone_and_cleanup_removes_committed(paths, conn):
    r = rmod.Runner(paths, {"G4": gate_graph()})
    try:
        r.start("G4", "g4-a", {"x": 0}, {"student_id": None})
        assert r.wait("g4-a")["status"] == "awaiting_review"
        before = repo.row_counts(conn)
        assert threads.cancel(r, paths, "g4-a") == {"cancelled": "g4-a", "session_deleted": 0}
        assert repo.row_counts(conn) == before and not r.exists("g4-a")
        r.start("G4", "g4-b", {"x": 0}, {})
        r.wait("g4-b")
        r._set("g4-b", status="committed")
        r.start("G4", "g4-c", {"x": 0}, {})
        r.wait("g4-c")
        assert threads.cleanup(r) == {"removed": ["g4-b"]}
        assert [t["thread_id"] for t in r.list_threads()] == ["g4-c"]
    finally:
        r.close()
