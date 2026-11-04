"""/api/backup: storage and row counts, backup now, restore (SDD Phụ lục B #44, #45; api-v3 §7.1)."""

import sqlite3
from contextlib import closing
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from tutor.api import deps
from tutor.db import repo
from tutor.graphs import threads

router = APIRouter(prefix="/api/backup")


@router.get("")
def storage(request: Request, conn: Annotated[sqlite3.Connection, Depends(deps.db)]) -> dict:
    paths = request.app.state.paths
    rows = repo.row_counts(conn)
    backups = sorted(paths.backup.glob("tutor-*.db"), reverse=True)
    return {
        "data_dir": str(paths.root),
        "rows": rows,
        "total": sum(rows.values()),
        "backups": [{"name": p.name, "bytes": p.stat().st_size} for p in backups],
    }


@router.post("")
def backup_now(request: Request) -> dict:
    paths = request.app.state.paths
    dst = repo.backup(paths.tutor_db, paths.backup)
    with closing(sqlite3.connect(dst)) as c:
        return {"path": dst.name, "rows": sum(repo.row_counts(c).values())}


class RestoreIn(BaseModel):
    name: str


@router.post("/restore")
def restore(body: RestoreIn, request: Request) -> dict:
    return threads.restore(request.app.state.runner, request.app.state.paths, body.name)
