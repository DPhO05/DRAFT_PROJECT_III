"""/api/worksheets: the sheets already given to a student and the .tex download (api-v3 §3.7, MONO-P6-02)."""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse

from tutor.api import deps
from tutor.db import repo
from tutor.graphs import worksheet

router = APIRouter(prefix="/api/worksheets")
DB = Annotated[sqlite3.Connection, Depends(deps.db)]


@router.get("")
def list_worksheets(student: int, conn: DB) -> list[dict]:
    repo.get_student(conn, student)  # 404
    return [w | {"tex": worksheet.tex_url(student, w["for_date"])} for w in repo.worksheets(conn, student)]


@router.get("/{student_id}/{for_date}.tex")
def download(student_id: int, for_date: str, request: Request) -> FileResponse:
    """The file commit wrote; for_date must be a real date (422), so the path cannot leave data/out/."""
    f = worksheet.sheet_file(request.app.state.paths, student_id, for_date)
    if not f.is_file():
        raise repo.NotFound(f"phiếu {for_date}")
    return FileResponse(f, media_type="text/x-tex; charset=utf-8", filename=f.name)
