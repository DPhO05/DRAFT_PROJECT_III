"""/api/sessions: inbox, submit (S1), list (MONO-P1-03), committed session view (MONO-P3-01)."""

import hashlib
import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from tutor.api import deps
from tutor.config import guess_submission
from tutor.db import repo
from tutor.graphs import session

router = APIRouter(prefix="/api/sessions")
DB = Annotated[sqlite3.Connection, Depends(deps.db)]


class Submit(BaseModel):
    student_id: int
    held_on: str
    path: str  # relative to data/inbox/


@router.get("/inbox")
def inbox(request: Request, conn: DB) -> list[dict]:
    """Student files in data/inbox/ (bank files excluded); `guess` = student and day read from the file name."""
    root = request.app.state.paths.inbox
    done = repo.submitted_sha256(conn)
    active = {s["id"] for s in repo.list_students(conn)}
    out = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() in (".tex", ".pdf") and "bank" not in p.relative_to(root).parts[:1]:
            sha = hashlib.sha256(p.read_bytes()).hexdigest()
            rel = p.relative_to(root).as_posix()
            guess = guess_submission(rel)
            out.append({"path": rel, "kind": p.suffix.lower()[1:], "bytes": p.stat().st_size, "sha256": sha,
                        "submitted_by": done.get(sha, []),
                        "guess": guess if guess and guess["student_id"] in active else None})  # fmt: skip
    return out


@router.post("", status_code=202)
def submit(body: Submit, request: Request) -> JSONResponse:
    # Idempotency-Key is accepted and ignored: the duplicate check runs inside BEGIN IMMEDIATE (S2).
    out = session.submit(
        request.app.state.paths, request.app.state.runner,
        student_id=body.student_id, held_on=body.held_on, rel_path=body.path,
    )  # fmt: skip
    return JSONResponse(out, status_code=202)


@router.get("")
def list_sessions(conn: DB, student: int | None = None, month: str | None = None, status: str | None = None) -> list:
    return repo.list_sessions(conn, student_id=student, month=month, status=status)


@router.get("/{session_id}")
def detail(session_id: int, conn: DB) -> dict:
    return repo.session_detail(conn, session_id)
