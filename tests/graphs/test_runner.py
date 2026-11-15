"""MONO-P1-01: in-process graph runner on a sample graph (2 LLM-like nodes, 1 gate, 1 commit)."""

import sqlite3
import threading
from collections import Counter
from contextlib import closing
from typing import TypedDict

import pytest
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from tutor.graphs import runner as rmod


class S(TypedDict, total=False):
    a: int
    decision: dict
    committed: bool


def sample(calls: Counter, fail_commit: list[bool], block: threading.Event | None = None):
    def llm_a(st):
        calls["a"] += 1
        if block:
            block.wait(5)
        return {"a": 1}

    def llm_b(st):
        calls["b"] += 1
        return {}

    def gate(st):
        return {"decision": interrupt({"gate": "review"})["decisions"]}

    def commit(st):
        calls["commit"] += 1
        if fail_commit and fail_commit.pop():
            raise RuntimeError("gài lỗi ở commit")
        return {"committed": True}

    g = StateGraph(S)
    for name, fn in [("llm_a", llm_a), ("llm_b", llm_b), ("gate", gate), ("commit", commit)]:
        g.add_node(name, fn)
    g.add_edge(START, "llm_a")
    g.add_edge("llm_a", "llm_b")
    g.add_edge("llm_b", "gate")
    g.add_edge("gate", "commit")
    g.add_edge("commit", END)
    return g


@pytest.fixture
def make(paths):
    made = []

    def _make(**graphs):
        r = rmod.Runner(paths, graphs)
        made.append(r)
        return r

    yield _make
    for r in made:
        r.close()


def test_two_resumes_call_each_node_once(make):
    calls = Counter()
    r = make(T=sample(calls, []))
    r.start("T", "t1", {"a": 0}, {"subject": "mẫu"})
    assert r.wait("t1")["status"] == "awaiting_review"
    assert r.get("t1")["node"] == "gate"
    r.save_decisions("t1", {"ok": True})
    r.resume("t1")
    row = r.wait("t1")
    assert row["status"] == "committed" and row["error"] is None
    assert r.state("t1")["decision"] == {"ok": True}
    assert calls == Counter(a=1, b=1, commit=1)


def test_failed_commit_reruns_only_commit(make):
    calls = Counter()
    r = make(T=sample(calls, [True]))
    r.start("T", "t1", {"a": 0}, {})
    r.wait("t1")
    r.resume("t1")
    row = r.wait("t1")
    assert row["status"] == "failed" and "gài lỗi" in row["error"] and row["node"] == "commit"
    r.resume("t1")
    assert r.wait("t1")["status"] == "committed"
    assert calls == Counter(a=1, b=1, commit=2)


def test_resume_while_running_is_busy(make):
    block = threading.Event()
    r = make(T=sample(Counter(), [], block))
    r.start("T", "t1", {"a": 0}, {})
    with pytest.raises(rmod.ThreadBusy):
        r.resume("t1")
    block.set()
    assert r.wait("t1")["status"] == "awaiting_review"


def test_committed_thread_cannot_resume(make):
    r = make(T=sample(Counter(), []))
    r.start("T", "t1", {"a": 0}, {})
    r.wait("t1")
    r.resume("t1")
    r.wait("t1")
    with pytest.raises(rmod.AlreadyCommitted):
        r.resume("t1")


def test_crash_mid_node_becomes_failed_on_next_start(paths, make):
    r = make(T=sample(Counter(), []))
    r._set("t9", graph="T", status="running", node="llm_a", create=True)  # as if the process died here
    failed = []
    r2 = make(T=sample(Counter(), []))
    r2.on_fail("T", lambda row: failed.append(row["thread_id"]))
    r2.recover_on_startup()
    row = r2.get("t9")
    assert row["status"] == "failed" and "dừng giữa chừng" in row["error"]
    assert failed == ["t9"]


def test_pending_hook_blocks_resume_and_counts_on_save(make):
    calls = Counter()
    r = make(T=sample(calls, []))
    r.pending_fn("T", lambda state, decisions, node: 0 if (decisions or {}).get("ok") else 2 + (node != "gate"))
    r.start("T", "t1", {"a": 0}, {})
    r.wait("t1")
    with pytest.raises(rmod.UndecidedItems) as e:
        r.resume("t1")
    assert e.value.n == 2 and r.get("t1")["status"] == "awaiting_review"
    assert r.save_decisions("t1", {"ok": False}) == 2
    assert r.save_decisions("t1", {"ok": True}) == 0
    r.resume("t1")
    assert r.wait("t1")["status"] == "committed" and calls["commit"] == 1


def test_checkpoints_count_grows_with_the_run(make):
    r = make(T=sample(Counter(), []))
    r._set("t0", create=True, graph="T", status="failed")
    assert r.get("t0")["checkpoints"] == 0
    r.start("T", "t1", {"a": 0}, {})
    at_gate = r.wait("t1")["checkpoints"]
    assert at_gate > 0
    r.save_decisions("t1", {"ok": True})
    r.resume("t1")
    assert r.wait("t1")["checkpoints"] > at_gate
    assert {t["thread_id"]: t["checkpoints"] for t in r.list_threads()} == {"t0": 0, "t1": r.get("t1")["checkpoints"]}


def test_state_is_the_input_until_the_first_checkpoint(paths):
    r = rmod.Runner(paths, {"T": sample(Counter(), [])}, max_workers=1)
    hold = threading.Event()
    r._pool.submit(hold.wait, 5)  # the only worker is busy, so the thread cannot start yet
    try:
        r.start("T", "t1", {"a": 7}, {})
        assert r.state("t1") == {"a": 7}
        hold.set()
        assert r.wait("t1")["status"] == "awaiting_review"
        assert r.state("t1")["a"] == 1
    finally:
        hold.set()
        r.close()


def test_old_tutor_thread_table_gets_input_json(paths):
    paths.root.mkdir(parents=True, exist_ok=True)
    old = rmod._SCHEMA.replace("  input_json     TEXT,\n", "")
    assert "input_json" not in old
    with closing(sqlite3.connect(paths.checkpoints_db)) as c:
        c.execute(old)
        c.execute(
            "INSERT INTO tutor_thread (thread_id, graph, status, created_at, updated_at)"
            " VALUES ('o', 'T', 'done', 'x', 'x')"
        )
        c.commit()
    r = rmod.Runner(paths, {"T": sample(Counter(), [])})
    try:
        assert r.get("o")["input_json"] is None
        r.start("T", "t1", {"a": 3}, {})
        assert r.wait("t1")["status"] == "awaiting_review"
    finally:
        r.close()
