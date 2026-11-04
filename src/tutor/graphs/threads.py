"""Review queue, date lock (C-28), cancel (C-15), cleanup and restore over the runner's threads (P3-T03, P3-T08)."""

from contextlib import closing
from datetime import date

from tutor.config import DataPaths, student_code
from tutor.db import repo
from tutor.graphs.runner import AlreadyCommitted, Runner, ThreadBusy

GRAPH_ORDER = {"G1": 1, "G2": 2, "G4": 4, "G5": 5}
_BLOCKING = {"awaiting_review": "", "failed": " đang lỗi — chạy lại và duyệt buổi đó trước",
             "running": " đang chạy — chờ xong và duyệt buổi đó trước"}  # fmt: skip


class ThreadLocked(Exception):
    """409 date_order_locked: an earlier session of the same student is not committed yet."""

    def __init__(self, reason: str, blocking_thread_id: str):
        super().__init__(reason)
        self.blocking_thread_id = blocking_thread_id


class Unfinished(Exception):
    """409 not_ready: a thread is still running or waiting for the teacher, so tutor.db must not be replaced."""

    def __init__(self, threads: list[dict]):
        super().__init__(f"Còn {len(threads)} việc chưa xong")
        self.threads = threads


def annotate(rows: list[dict]) -> list[dict]:
    """Add locked / lock_reason / blocking_thread_id / blocking_held_on / blocking_status. Computed, never stored
    (C-28): an awaiting G1 thread is locked while the same student has an earlier G1 session waiting, failed or
    running."""
    for t in rows:
        t |= {"locked": False, "lock_reason": None, "blocking_thread_id": None, "blocking_held_on": None,
              "blocking_status": None}  # fmt: skip
        if t["graph"] != "G1" or t["status"] != "awaiting_review" or not t["held_on"]:
            continue
        earlier = sorted(
            (o for o in rows if o is not t and o["graph"] == "G1" and o["student_id"] == t["student_id"]
             and o["status"] in _BLOCKING and o["held_on"] and o["held_on"] < t["held_on"]),
            key=lambda o: o["held_on"],
        )  # fmt: skip
        if earlier:
            b = earlier[0]
            day = f"{date.fromisoformat(b['held_on']):%d/%m}"
            tail = _BLOCKING[b["status"]]
            what = f"buổi {day} của {student_code(t['student_id'])}" + (tail or " trước")
            t |= {"locked": True, "blocking_thread_id": b["thread_id"], "blocking_held_on": b["held_on"],
                  "blocking_status": b["status"],
                  "lock_reason": f"Elo cập nhật tuần tự: {'' if tail else 'duyệt '}{what}"}  # fmt: skip
    return rows


def queue(rows: list[dict]) -> list[dict]:
    """Awaiting threads: G1 → G5; G1 by student then held_on, other graphs by last update (`tutor review`)."""
    aw = [t for t in annotate(rows) if t["status"] == "awaiting_review"]
    return sorted(aw, key=lambda t: (GRAPH_ORDER.get(t["graph"], 9),
                                     *((t["student_id"] or 0, t["held_on"] or "") if t["graph"] == "G1"
                                       else (0, t["updated_at"]))))  # fmt: skip


def listing(runner: Runner, *, graph: str | None = None, status: str | None = None,
            student_id: int | None = None) -> list[dict]:  # fmt: skip
    """GET /api/threads: lock info needs every thread, so filter after annotating; awaiting → queue order."""
    rows = annotate(runner.list_threads())
    rows = [t for t in rows if (graph is None or t["graph"] == graph) and (status is None or t["status"] == status)
            and (student_id is None or t["student_id"] == student_id)]  # fmt: skip
    return queue(rows) if status == "awaiting_review" else rows


def resume(runner: Runner, thread_id: str) -> None:
    """runner.resume, refused for a date-locked G1 thread."""
    t = next((t for t in annotate(runner.list_threads()) if t["thread_id"] == thread_id), None)
    if t and t["locked"]:
        raise ThreadLocked(t["lock_reason"], t["blocking_thread_id"])
    runner.resume(thread_id)


def cancel(runner: Runner, paths: DataPaths, thread_id: str) -> dict:
    """Drop a thread's checkpoints. G1: also delete its session row while it has no attempt (C-15, extended to
    awaiting_review) so the same file can be resubmitted and later sessions unlock."""
    t = runner.get(thread_id)
    if t["running"] or t["status"] == "running":
        raise ThreadBusy(thread_id)
    if t["status"] == "committed":
        raise AlreadyCommitted(thread_id)
    deleted = 0
    if t["graph"] == "G1" and t["session_id"]:
        with closing(repo.connect(paths.tutor_db)) as conn:
            deleted = repo.delete_uncommitted_session(conn, t["session_id"])
    runner.delete(thread_id)
    return {"cancelled": thread_id, "session_deleted": deleted}


def cleanup(runner: Runner) -> dict:
    """Dọn: drop checkpoints of committed threads (tutor.db already has their result)."""
    gone = [t["thread_id"] for t in runner.list_threads() if t["status"] in ("committed", "done") and not t["running"]]
    for tid in gone:
        runner.delete(tid)
    return {"removed": gone}


def restore(runner: Runner, paths: DataPaths, name: str) -> dict:
    """Restore backup `name` unless a thread is unfinished (R7, R19), then drop the committed threads' checkpoints."""
    repo.read_backup(paths.backup, name).close()  # a bad file is refused before the teacher is asked to drop work
    # shortcut: no lock between this check and the copy (one teacher, one app); a grading started in between loses
    # its session row. Add a restore lock if the app is ever shared.
    open_ = [{k: t[k] for k in ("thread_id", "graph", "status", "running")} for t in runner.list_threads()
             if t["running"] or t["status"] in ("running", "awaiting_review", "failed")]  # fmt: skip
    if open_:
        raise Unfinished(open_)
    out = repo.restore(paths.tutor_db, paths.backup, name)
    return out | {"threads_removed": len(cleanup(runner)["removed"])}
