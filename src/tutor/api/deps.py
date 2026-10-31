import sqlite3
from collections.abc import Iterator

from fastapi import Request

from tutor.db import repo


def db(request: Request) -> Iterator[sqlite3.Connection]:
    """One tutor.db connection per request (sqlite3 connections are not shared across threads)."""
    conn = repo.connect(request.app.state.paths.tutor_db)
    try:
        yield conn
    finally:
        conn.close()
