"""/api/bank: the Ngân hàng bài tab (list, view, edit, import)."""

import sqlite3
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from tutor.api import deps
from tutor.db import repo
from tutor.graphs import bank as g2
from tutor.services import search

router = APIRouter(prefix="/api/bank")
DB = Annotated[sqlite3.Connection, Depends(deps.db)]


class ProblemPatch(BaseModel):
    kc_ids: list[int] | None = None
    level: Literal["dễ", "vừa", "khó"] | None = None
    rubric_items: list[dict] | None = None


class ImportBody(BaseModel):
    file: str


@router.get("/inbox")
def inbox(request: Request, conn: DB) -> list[dict]:
    """The .tex files waiting in data/inbox/bank/ and how many of their problems are already in the bank."""
    return g2.inbox(request.app.state.paths, conn)


@router.post("/imports", status_code=202)
def start_import(body: ImportBody, request: Request, response: Response) -> dict:
    """Start G2 for one inbox file; a file whose import is not committed yet answers 200 with that thread."""
    out = g2.start_import(request.app.state.paths, request.app.state.runner, file=body.file)
    if out["existing"]:
        response.status_code = 200
    return {"thread_id": out["thread_id"], "status": out["status"]}


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
def get_problem(problem_id: int, conn: DB, tech: int = 0) -> dict:
    out = repo.problem_view(conn, problem_id)
    if tech:
        out["tech"] = repo.problem_tech(conn, problem_id)
    return out


@router.patch("/problems/{problem_id}")
def patch_problem(problem_id: int, body: ProblemPatch, conn: DB) -> dict:
    """A key left out is unchanged; level null clears the level."""
    repo.update_problem_labels(conn, problem_id, **body.model_dump(exclude_unset=True))
    return repo.problem_view(conn, problem_id) | {"applies_from_now": True}
