"""Run graphs in the background inside the app process (MONO-P1-01, SDD monolith §4.5).

State of each thread (status, last node, error, saved decisions) lives in table tutor_thread
inside checkpoints.db, next to LangGraph's own checkpoint tables.
"""

import json
import logging
import sqlite3
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import StateGraph
from langgraph.types import Command

from tutor.config import DataPaths
from tutor.db.repo import now

log = logging.getLogger("tutor")
_SCHEMA = """
CREATE TABLE IF NOT EXISTS tutor_thread (
  thread_id      TEXT PRIMARY KEY,
  graph          TEXT NOT NULL,
  subject        TEXT,
  student_id     INTEGER,
  session_id     INTEGER,
  held_on        TEXT,
  status         TEXT NOT NULL CHECK (status IN ('running','awaiting_review','committed','failed','done')),
  node           TEXT,
  error          TEXT,
  decisions_json TEXT,
  created_at     TEXT NOT NULL,
  updated_at     TEXT NOT NULL
)"""
_META = ("subject", "student_id", "session_id", "held_on")


class ThreadNotFound(Exception):
    pass


class ThreadBusy(Exception):
    """The thread is running right now (409 not_ready)."""


class AlreadyCommitted(Exception):
    pass


class NotResumable(Exception):
    pass


class UndecidedItems(Exception):
    """The gate's resume condition is not met yet (409 undecided_items, SDD §5.4)."""

    def __init__(self, n: int):
        super().__init__(f"Còn {n} mục chưa xử lý")
        self.n = n


class Runner:
    def __init__(self, paths: DataPaths, graphs: dict[str, StateGraph], max_workers: int = 2):
        paths.root.mkdir(parents=True, exist_ok=True)
        self._saver_conn = sqlite3.connect(paths.checkpoints_db, check_same_thread=False)
        self._saver_conn.execute("PRAGMA journal_mode = WAL")
        self.saver = SqliteSaver(self._saver_conn)
        self.saver.setup()
        self._conn = sqlite3.connect(paths.checkpoints_db, check_same_thread=False, isolation_level=None, timeout=5)
        self._lock = threading.Lock()  # one statement at a time on _conn; also guards _futures
        with self._lock:
            self._conn.execute(_SCHEMA)
        self.graphs = {name: g.compile(checkpointer=self.saver) for name, g in graphs.items()}
        self._pool = ThreadPoolExecutor(max_workers, thread_name_prefix="graph")
        self._futures: dict[str, Future] = {}
        self._fail_hooks: dict[str, Callable[[dict], None]] = {}
        self._pending: dict[str, Callable[[dict, object, str], int]] = {}

    def on_fail(self, graph: str, fn: Callable[[dict], None]) -> None:
        """fn(row) after a thread of `graph` fails (G1: session.status = failed)."""
        self._fail_hooks[graph] = fn

    def pending_fn(self, graph: str, fn: Callable[[dict, object, str], int]) -> None:
        """fn(state, decisions, gate node) -> items still undecided there (0 = may resume); may raise NotResumable."""
        self._pending[graph] = fn

    def _undecided(self, row: dict, decisions: object) -> int | None:
        fn = self._pending.get(row["graph"])
        if fn is None or row["status"] != "awaiting_review":
            return None
        return fn(self.state(row["thread_id"]), decisions, row["node"])

    def _set(self, thread_id: str, *, create: bool = False, **fields) -> None:
        fields["updated_at"] = now()
        with self._lock:
            if create:
                fields |= {"thread_id": thread_id, "created_at": fields["updated_at"]}
                cols = ", ".join(fields)
                self._conn.execute(
                    f"INSERT INTO tutor_thread ({cols}) VALUES ({', '.join('?' * len(fields))})", list(fields.values())
                )
            else:
                sets = ", ".join(f"{k} = ?" for k in fields)
                self._conn.execute(f"UPDATE tutor_thread SET {sets} WHERE thread_id = ?", [*fields.values(), thread_id])

    def _rows(self, where: str = "", args: tuple = ()) -> list[dict]:
        with self._lock:
            # checkpoints: LangGraph's own table; checkpoint_ns '' = root graph, not subgraphs (C-05)
            cur = self._conn.execute(
                "SELECT *, (SELECT COUNT(*) FROM checkpoints c WHERE c.thread_id = tutor_thread.thread_id"
                f" AND c.checkpoint_ns = '') AS checkpoints FROM tutor_thread {where} ORDER BY created_at, thread_id",
                args,
            )
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]
            for r in rows:
                f = self._futures.get(r["thread_id"])
                r["running"] = f is not None and not f.done()
        return rows

    def get(self, thread_id: str) -> dict:
        rows = self._rows("WHERE thread_id = ?", (thread_id,))
        if not rows:
            raise ThreadNotFound(thread_id)
        return rows[0]

    def list_threads(
        self, *, graph: str | None = None, status: str | None = None, student_id: int | None = None
    ) -> list[dict]:
        conds = {"graph": graph, "status": status, "student_id": student_id}
        conds = {k: v for k, v in conds.items() if v is not None}
        where = ("WHERE " + " AND ".join(f"{k} = ?" for k in conds)) if conds else ""
        return self._rows(where, tuple(conds.values()))

    def exists(self, thread_id: str) -> bool:
        return bool(self._rows("WHERE thread_id = ?", (thread_id,)))

    def state(self, thread_id: str) -> dict:
        row = self.get(thread_id)
        return self.graphs[row["graph"]].get_state({"configurable": {"thread_id": thread_id}}).values

    def start(self, graph: str, thread_id: str, inp: dict, meta: dict) -> None:
        self._set(thread_id, create=True, graph=graph, status="running", **{k: meta.get(k) for k in _META})
        self._submit(graph, thread_id, inp)

    def save_decisions(self, thread_id: str, decisions: object) -> int | None:
        """Store without resuming (Tạm dừng, duyệt sau). Returns items still undecided, None if no gate check."""
        row = self.get(thread_id)
        self._set(thread_id, decisions_json=json.dumps(decisions, ensure_ascii=False))
        try:
            return self._undecided(row, decisions)
        except NotResumable:  # the gate cannot resume yet, but saving a draft is still fine
            return None

    def resume(self, thread_id: str) -> None:
        """At a gate: continue with the saved decisions. Failed: re-run from the last checkpoint."""
        row = self.get(thread_id)
        if row["running"]:
            raise ThreadBusy(thread_id)
        if row["status"] == "committed":
            raise AlreadyCommitted(thread_id)
        if row["status"] == "awaiting_review":
            # Always a non-empty dict: langgraph 1.2 fails on resume=None and reads {} as an empty id map.
            # Gate nodes take interrupt(...)["decisions"].
            saved = json.loads(row["decisions_json"]) if row["decisions_json"] else None
            if n := self._undecided(row, saved):
                raise UndecidedItems(n)
            inp = Command(resume={"decisions": saved})
        elif row["status"] == "failed":
            inp = None
        else:
            raise NotResumable(f"{thread_id}: {row['status']}")
        self._set(thread_id, status="running", error=None)
        self._submit(row["graph"], thread_id, inp)

    def _submit(self, graph: str, thread_id: str, inp: object) -> None:
        with self._lock:
            f = self._futures.get(thread_id)
            if f is not None and not f.done():
                raise ThreadBusy(thread_id)
            self._futures[thread_id] = self._pool.submit(self._run, graph, thread_id, inp)

    def _run(self, graph: str, thread_id: str, inp: object) -> None:
        g, cfg = self.graphs[graph], {"configurable": {"thread_id": thread_id}}
        try:
            for chunk in g.stream(inp, cfg, stream_mode="updates"):
                done = [n for n in chunk if not n.startswith("__")]
                if done:
                    self._set(thread_id, node=done[-1])
            snap = g.get_state(cfg)
            if snap.interrupts:
                self._set(thread_id, status="awaiting_review", node=snap.next[0] if snap.next else None)
            else:
                # "done": graph ended without a commit node
                self._set(thread_id, status="committed" if snap.values.get("committed") else "done")
        except Exception as e:
            log.error("thread %s lỗi", thread_id, exc_info=e)
            nxt = g.get_state(cfg).next
            self._set(thread_id, status="failed", error=f"{type(e).__name__}: {e}"[:500], node=nxt[0] if nxt else None)
            self._after_fail(graph, thread_id)

    def _after_fail(self, graph: str, thread_id: str) -> None:
        if hook := self._fail_hooks.get(graph):
            try:
                hook(self.get(thread_id))
            except Exception as e:
                log.error("on_fail %s lỗi", thread_id, exc_info=e)

    def delete(self, thread_id: str) -> None:
        """Remove a thread's checkpoints and its tutor_thread row (cancel / cleanup check status first)."""
        if self.get(thread_id)["running"]:
            raise ThreadBusy(thread_id)
        self.saver.delete_thread(thread_id)
        with self._lock:
            self._conn.execute("DELETE FROM tutor_thread WHERE thread_id = ?", (thread_id,))
            self._futures.pop(thread_id, None)

    def wait(self, thread_id: str, timeout: float = 60) -> dict:
        with self._lock:
            f = self._futures.get(thread_id)
        if f is not None:
            f.result(timeout)
        return self.get(thread_id)

    def recover_on_startup(self) -> list[str]:
        """Threads left 'running' by a dead process become 'failed' (ADR-M08)."""
        stuck = [r for r in self.list_threads(status="running") if not r["running"]]
        for r in stuck:
            self._set(
                r["thread_id"], status="failed", error="Tiến trình dừng giữa chừng (tắt app / máy ngủ); bấm Chạy lại"
            )
            self._after_fail(r["graph"], r["thread_id"])
        return [r["thread_id"] for r in stuck]

    def close(self) -> None:
        self._pool.shutdown(wait=True)
        self._conn.close()
        self._saver_conn.close()
