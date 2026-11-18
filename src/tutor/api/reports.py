"""/api/reports: start a period report (G5), list drafts and approved ones, read one (api-v3 §5, P7-T07).

Nothing here commits: the tutor's Duyệt báo cáo is `POST /api/threads/{id}/resume` (C-39)."""

import sqlite3
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from tutor.api import deps
from tutor.db import repo
from tutor.graphs import report

router = APIRouter(prefix="/api/reports")
DB = Annotated[sqlite3.Connection, Depends(deps.db)]


class Period(BaseModel):
    student_id: int
    period_kind: str
    period_start: str


@router.post("", status_code=202)
def create(body: Period, request: Request, response: Response) -> dict:
    """202 a new draft is being written; 200 `existing` the period already has one (R16)."""
    out = report.start(request.app.state.paths, request.app.state.runner, **body.model_dump(), today=date.today())
    if out.pop("existing"):
        response.status_code = 200
        return out | {"existing": True}
    return out


@router.get("")
def listing(request: Request, conn: DB, student: int | None = None) -> dict:
    return {"drafts": report.drafts(request.app.state.runner, student), "approved": repo.reports(conn, student)}


@router.get("/{report_id}")
def get_report(report_id: int, request: Request, conn: DB) -> dict:
    r = repo.report(conn, report_id)
    file = report.report_file(request.app.state.paths, r["student_id"], r["period_kind"], r["period_start"])
    return {k: v for k, v in r.items() if k != "text_md"} | {"sentences": report.lines(r["text_md"]),
                                                             "sections": report.sections(r["text_md"]),
                                                             "file": file.name}  # fmt: skip
