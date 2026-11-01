"""/api/students (MONO-P1-02)."""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from tutor.api import deps
from tutor.db import repo

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


@router.get("")
def list_students(conn: DB, archived: bool = False) -> list[dict]:
    return repo.list_students(conn, include_archived=archived)


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
