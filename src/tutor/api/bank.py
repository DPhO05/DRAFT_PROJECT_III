"""/api/bank (read part used by Buổi học bước 3 › Chọn bài khác; the Ngân hàng screen is phase P5)."""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends

from tutor.api import deps
from tutor.db import repo
from tutor.services import search

router = APIRouter(prefix="/api/bank")
DB = Annotated[sqlite3.Connection, Depends(deps.db)]


@router.get("/problems")
def list_problems(
    conn: DB,
    q: str = "",
    limit: int | None = None,
    view: str = "",
    topic: int | None = None,
    grade: int | None = None,
    level: str | None = None,
    kc: int | None = None,
    offset: int = 0,
) -> list[dict] | dict:
    """view=teacher: the filtered grid {total, topic_counts, items}. Otherwise q matches the ref or the statement,
    case-insensitive, ignoring $ math delimiters."""
    if view == "teacher":
        return search.browse(
            conn,
            q=q,
            topic=topic,
            grade=grade,
            level=level,
            kc=kc,
            offset=max(offset, 0),
            limit=min(max(limit or 12, 1), 100),
        )
    q = q.strip().lower().replace("$", "")
    rows = [p for p in repo.bank_problems(conn)
            if q in p["ref"].lower() or q in p["statement_latex"].lower().replace("$", "")]  # fmt: skip
    return rows[: max(limit if limit is not None else 50, 0)]


@router.get("/problems/{problem_id}")
def get_problem(problem_id: int, conn: DB) -> dict:
    return repo.problem_detail(conn, problem_id)
