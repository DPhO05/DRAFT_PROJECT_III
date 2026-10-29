"""/api/bank (read part used by Buổi học bước 3 › Chọn bài khác; the Ngân hàng screen is phase P5)."""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends

from tutor.api import deps
from tutor.db import repo

router = APIRouter(prefix="/api/bank")
DB = Annotated[sqlite3.Connection, Depends(deps.db)]


@router.get("/problems")
def list_problems(conn: DB, q: str = "", limit: int = 50) -> list[dict]:
    """q matches the ref or the statement, case-insensitive, ignoring $ math delimiters."""
    q = q.strip().lower().replace("$", "")
    rows = [p for p in repo.bank_problems(conn)
            if q in p["ref"].lower() or q in p["statement_latex"].lower().replace("$", "")]  # fmt: skip
    return rows[: max(limit, 0)]


@router.get("/problems/{problem_id}")
def get_problem(problem_id: int, conn: DB) -> dict:
    return repo.problem_detail(conn, problem_id)
