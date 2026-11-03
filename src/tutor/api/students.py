"""/api/students (MONO-P1-02)."""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from tutor.api import deps
from tutor.db import repo
from tutor.graphs import session
from tutor.services import students

router = APIRouter(prefix="/api/students")
DB = Annotated[sqlite3.Connection, Depends(deps.db)]


class NewStudent(BaseModel):
    name: str
    grade: int | None = None
    note: str | None = None


class StudentPatch(BaseModel):
    name: str | None = None
    grade: int | None = None
    note: str | None = None


def _full_name(name: str) -> None:
    if len(name.split()) < 2:
        raise ValueError("Nhập đủ họ và tên (ít nhất 2 chữ)")


def _pending(request: Request) -> dict[int, list[dict]]:
    """Grading threads waiting on the tutor (at a gate, or failed), by student, oldest day first."""
    out: dict[int, list[dict]] = {}
    threads = request.app.state.runner.list_threads(graph=session.GRAPH)
    for t in sorted(threads, key=lambda t: (t["held_on"] or "", t["thread_id"])):
        if t["status"] in ("awaiting_review", "failed"):
            out.setdefault(t["student_id"], []).append({"thread_id": t["thread_id"], "held_on": t["held_on"]})
    return out


@router.get("")
def list_students(request: Request, conn: DB, archived: bool = False, view: str = "") -> list[dict]:
    """view=teacher adds since, last_session, level_counts and pending_grading (api-v3 §4.1)."""
    rows = repo.list_students(conn, include_archived=archived)
    if view != "teacher":
        return rows
    info, pending = students.overview(conn), _pending(request)
    return [r | info[r["id"]] | {"pending_grading": len(pending.get(r["id"], []))} for r in rows]


@router.post("", status_code=201)
def add(body: NewStudent, conn: DB) -> dict:
    _full_name(body.name)
    sid = repo.add_student(conn, name=body.name, grade=body.grade, note=body.note)
    return repo.get_student(conn, sid)


@router.patch("/{student_id}")
def patch(student_id: int, body: StudentPatch, conn: DB) -> dict:
    if body.name is not None:
        _full_name(body.name)
    repo.update_student(conn, student_id, **body.model_dump(exclude_unset=True))
    return repo.get_student(conn, student_id)


@router.post("/{student_id}/archive")
def archive(student_id: int, conn: DB) -> dict:
    return {"archived_at": repo.archive_student(conn, student_id)}


@router.post("/{student_id}/unarchive")
def unarchive(student_id: int, conn: DB) -> dict:
    repo.unarchive_student(conn, student_id)
    return {"archived_at": None}


@router.get("/{student_id}/profile")
def profile(student_id: int, request: Request, conn: DB) -> dict:
    s = repo.get_student(conn, student_id)
    return {
        "student": {
            "id": s["id"],
            "name": s["name"],
            "grade": s["grade"],
            "note": s["note"],
            "since": students.overview(conn)[student_id]["since"],
            "archived_at": s["archived_at"],
        },
        "skills": students.skills(conn, student_id),
        "recurring": students.recurring(conn, student_id),
        "pending": _pending(request).get(student_id, []),
    }


@router.get("/{student_id}/progress")
def progress(student_id: int, conn: DB) -> dict:
    repo.get_student(conn, student_id)  # 404 first
    return students.progress(conn, student_id)
