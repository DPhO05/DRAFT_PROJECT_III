"""One error envelope for every /api response: {"error": {code, message, detail}} (SDD §5.4, S3)."""

import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from tutor.db import repo
from tutor.graphs import runner, threads

log = logging.getLogger("tutor")
_CODES = {400: "bad_request", 403: "forbidden", 404: "not_found", 422: "validation_error"}


def error(status: int, code: str, message: str, detail: object = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message, "detail": detail}}, status_code=status)


def install(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    def _http(request: Request, e: HTTPException) -> JSONResponse:
        return error(e.status_code, _CODES.get(e.status_code, "bad_request"), str(e.detail))

    @app.exception_handler(RequestValidationError)
    def _invalid(request: Request, e: RequestValidationError) -> JSONResponse:
        return error(422, "validation_error", "Dữ liệu gửi lên không đúng dạng", jsonable_encoder(e.errors()))

    # domain errors -> (status, code, detail)
    mapping = {
        repo.NotFound: lambda e: (404, "not_found", None),
        runner.ThreadNotFound: lambda e: (404, "not_found", None),
        repo.DuplicateSubmission: lambda e: (409, "duplicate_submission", {"session_id": e.session_id,
                                                                           "thread_id": e.thread_id}),
        repo.DateOrderLocked: lambda e: (409, "date_order_locked", {"last_committed": e.last_committed}),
        runner.ThreadBusy: lambda e: (409, "not_ready", {"reason": "thread đang chạy"}),
        runner.AlreadyCommitted: lambda e: (409, "already_committed", None),
        runner.NotResumable: lambda e: (409, "not_ready", {"reason": str(e)}),
        runner.UndecidedItems: lambda e: (409, "undecided_items", {"n": e.n}),
        threads.ThreadLocked: lambda e: (409, "date_order_locked", {"blocking_thread_id": e.blocking_thread_id}),
        repo.CatalogError: lambda e: (422, "validation_error", {"cycle": e.cycle} if e.cycle else None),
        ValueError: lambda e: (422, "validation_error", None),
    }  # fmt: skip
    for exc, fn in mapping.items():

        def handler(request: Request, e: Exception, fn=fn) -> JSONResponse:
            status, code, detail = fn(e)
            return error(status, code, str(e) or code, detail)

        app.add_exception_handler(exc, handler)

    @app.exception_handler(Exception)
    def _unexpected(request: Request, e: Exception) -> JSONResponse:
        log.error("%s %s", request.method, request.url.path, exc_info=e)
        return error(500, "internal", "Lỗi không lường trước, chi tiết ở data/logs/app.log")
