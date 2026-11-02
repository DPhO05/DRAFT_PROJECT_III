"""/api/threads: list + lock, poll, save decisions, resume, cancel, cleanup (MONO-P1-03, P2-01, P3-01, P3-02)."""

from contextlib import closing

from fastapi import APIRouter, Body, Request

from tutor.db import repo
from tutor.graphs import bank, session, threads, worksheet
from tutor.graphs.runner import ThreadNotFound

router = APIRouter(prefix="/api/threads")


@router.get("")
def list_threads(request: Request, graph: str | None = None, status: str | None = None,
                 student: int | None = None) -> list[dict]:  # fmt: skip
    """status=awaiting_review → the review queue order (`tutor review`)."""
    return threads.listing(request.app.state.runner, graph=graph, status=status, student_id=student)


@router.post("/cleanup")
def cleanup(request: Request) -> dict:
    """Dọn: drop checkpoints of committed threads."""
    return threads.cleanup(request.app.state.runner)


@router.get("/{thread_id}")
def get_thread(thread_id: str, request: Request, include: str | None = None, view: str = "") -> dict:
    """view=teacher: the short row plus `card`, built by the server per graph (null for graphs with no card yet)."""
    r = request.app.state.runner
    r.get(thread_id)  # 404 first
    row = next((t for t in threads.annotate(r.list_threads()) if t["thread_id"] == thread_id), None)
    if row is None:  # deleted after the lookup above (a draft replaced by `propose`)
        raise ThreadNotFound(thread_id)
    if view == "teacher":
        card = None
        if row["graph"] == session.GRAPH:
            card = session.card(request.app.state.paths, row, r.state(thread_id), r.done_count(thread_id, "lane"))
        elif row["graph"] == bank.GRAPH:
            with closing(repo.connect(request.app.state.paths.tutor_db, readonly=True)) as conn:
                card = bank.card(row, r.state(thread_id), repo.list_kc(conn))
        elif row["graph"] == worksheet.GRAPH:
            with closing(repo.connect(request.app.state.paths.tutor_db, readonly=True)) as conn:
                card = worksheet.card(row, r.state(thread_id), conn)
        return {k: row[k] for k in ("thread_id", "graph", "status", "updated_at")} | {"card": card}
    if include == "state" or row["status"] == "committed":
        state = r.state(thread_id)
        row["receipt"] = state.get("receipt")
        if include == "state":
            row["state"] = state
    return row


@router.put("/{thread_id}/decisions")
def save_decisions(thread_id: str, request: Request, decisions: dict = Body(...)) -> dict:  # noqa: B008
    """Store the teacher's answers without resuming (Tạm dừng, duyệt sau)."""
    return {"saved": True, "pending": request.app.state.runner.save_decisions(thread_id, decisions)}


@router.post("/{thread_id}/resume", status_code=202)
def resume(thread_id: str, request: Request) -> dict:
    """Continue at a gate with the saved decisions (review → commit ②), or rerun a failed thread."""
    threads.resume(request.app.state.runner, thread_id)
    return {"thread_id": thread_id, "status": "running"}


@router.post("/{thread_id}/cancel")
def cancel(thread_id: str, request: Request) -> dict:
    return threads.cancel(request.app.state.runner, request.app.state.paths, thread_id)
