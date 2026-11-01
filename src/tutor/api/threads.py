"""/api/threads: list + lock, poll, save decisions, resume, cancel, cleanup (MONO-P1-03, P2-01, P3-01, P3-02)."""

from contextlib import closing

from fastapi import APIRouter, Body, Request

from tutor.db import repo
from tutor.graphs import bank, threads

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
    t = r.get(thread_id)  # 404 first
    if view == "teacher":
        card = None
        if t["graph"] == bank.GRAPH:
            with closing(repo.connect(request.app.state.paths.tutor_db, readonly=True)) as conn:
                card = bank.card(t, r.state(thread_id), repo.list_kc(conn))
        return {k: t[k] for k in ("thread_id", "graph", "status", "updated_at")} | {"card": card}
    row = next(t for t in threads.annotate(r.list_threads()) if t["thread_id"] == thread_id)
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
