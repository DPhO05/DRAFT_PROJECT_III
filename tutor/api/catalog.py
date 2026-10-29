"""/api/catalog: KC, prerequisites, CSV import / export (MONO-P1-02); error codes (MONO-P2-02)."""

import sqlite3
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel

from tutor.api import deps
from tutor.db import repo
from tutor.graphs import session

router = APIRouter(prefix="/api/catalog")
DB = Annotated[sqlite3.Connection, Depends(deps.db)]


class NewKc(BaseModel):
    code: str
    name: str
    description: str
    parent_id: int | None = None
    lop: int | None = None


class KcPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    parent_id: int | None = None
    lop: int | None = None


class Prereq(BaseModel):
    prereq_id: int


class NewErrorCode(BaseModel):
    code: str
    category: str
    description: str
    example: str | None = None


class ErrorCodePatch(BaseModel):
    description: str | None = None
    example: str | None = None
    active: bool | None = None


class CatalogCsv(BaseModel):
    kc_csv: str
    prereq_csv: str = "kc_code,prereq_code\n"


def _kc(conn: sqlite3.Connection, kc_id: int) -> dict:
    for k in repo.list_kc(conn):
        if k["id"] == kc_id:
            return k
    raise repo.NotFound(f"KC {kc_id}")


@router.get("/kc")
def list_kc(conn: DB) -> list[dict]:
    return repo.list_kc(conn)


@router.post("/kc")
def add_kc(body: NewKc, conn: DB) -> dict:
    return _kc(conn, repo.add_kc(conn, **body.model_dump()))


@router.patch("/kc/{kc_id}")
def patch_kc(kc_id: int, body: KcPatch, conn: DB) -> dict:
    repo.update_kc(conn, kc_id, **body.model_dump(exclude_unset=True))
    return _kc(conn, kc_id)


@router.post("/kc/{kc_id}/prereqs")
def add_prereq(kc_id: int, body: Prereq, conn: DB) -> dict:
    repo.add_prereq(conn, kc_id, body.prereq_id)
    return {"ok": True}


@router.delete("/kc/{kc_id}/prereqs/{prereq_id}")
def remove_prereq(kc_id: int, prereq_id: int, conn: DB) -> dict:
    repo.remove_prereq(conn, kc_id, prereq_id)
    return {"ok": True}


@router.post("/import/preview")
def import_preview(body: CatalogCsv, conn: DB) -> dict:
    return repo.import_catalog(conn, *repo.read_catalog(body.kc_csv, body.prereq_csv), apply=False)


@router.post("/import")
def import_apply(body: CatalogCsv, conn: DB) -> dict:
    return repo.import_catalog(conn, *repo.read_catalog(body.kc_csv, body.prereq_csv), apply=True)


@router.get("/export")
def export(conn: DB, file: Literal["kc", "prereq", "error_code"] = "kc") -> Response:
    if file == "error_code":
        text, name = repo.export_error_codes(conn), "error_code.csv"
    else:
        kc_csv, prereq_csv = repo.export_catalog(conn)
        text, name = (kc_csv, "kc.csv") if file == "kc" else (prereq_csv, "kc_prereq.csv")
    return Response(
        text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/error-codes")
def list_error_codes(conn: DB) -> list[dict]:
    return repo.error_codes(conn)


@router.post("/error-codes", status_code=201)
def add_error_code(body: NewErrorCode, conn: DB) -> dict:
    row = repo.add_error_code(conn, **body.model_dump())
    return row | {"prompt_version": session.diagnoser_prompt_version(conn)}


@router.patch("/error-codes/{code}")
def patch_error_code(code: str, body: ErrorCodePatch, conn: DB) -> dict:
    row = repo.update_error_code(conn, code, **body.model_dump(exclude_unset=True))
    return row | {"prompt_version": session.diagnoser_prompt_version(conn)}


@router.get("/error-codes/{code}/mistakes")
def error_code_mistakes(code: str, conn: DB) -> list[dict]:
    return repo.error_code_mistakes(conn, code)
