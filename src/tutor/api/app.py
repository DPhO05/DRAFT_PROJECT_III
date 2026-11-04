"""create_app(): one process serving the app (static files) and /api on 127.0.0.1 (SDD monolith §3, §5)."""

import logging
import sqlite3
from contextlib import asynccontextmanager, closing
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from tutor import __version__, config, devfake, llm
from tutor.api import assistant, backup, bank, catalog, errors, logs, reports, sessions, students, threads, worksheets
from tutor.api import settings as settings_api  # `settings` is a local of create_app
from tutor.db import repo
from tutor.graphs.registry import make_runner

APP_DIR = Path(__file__).resolve().parents[3] / "app"
APP_V3_DIR = Path(__file__).resolve().parents[3] / "app-v3"
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
log = logging.getLogger("tutor")


def _log_to(path: Path) -> None:
    for h in [h for h in log.handlers if getattr(h, "tutor_app_log", False)]:
        log.removeHandler(h)
        h.close()
    h = logging.FileHandler(path, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    h.tutor_app_log = True
    log.addHandler(h)
    log.setLevel(logging.INFO)


def create_app(paths: config.DataPaths, *, port: int, fake_llm: bool = False) -> FastAPI:
    """The DB must already be initialised by the runner.lock holder (`tutor app`)."""
    paths.ensure()
    _log_to(paths.logs / "app.log")
    try:
        settings, settings_error = config.load(paths.settings), None
    except config.SettingsError as e:
        log.error("settings.json hỏng, chạy với mặc định: %s", e)
        settings, settings_error = config.defaults(), str(e)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        llm.configure(paths.logs / "llm.jsonl", devfake.models() if fake_llm else settings["models"])
        if fake_llm:
            llm.set_backend(devfake.DevFakeLLM())
            log.warning("--fake-llm: không gọi Anthropic, mọi output là giả (model dev-fake)")
        runner = make_runner(paths, settings["runner"]["max_workers"])
        if stuck := runner.recover_on_startup():
            log.warning("thread dừng giữa chừng -> failed: %s", stuck)
        app.state.runner = runner
        yield
        runner.close()

    app = FastAPI(
        title="tutor", version=__version__, openapi_url="/api/openapi.json", docs_url=None, redoc_url=None,
        lifespan=lifespan,
    )  # fmt: skip
    app.state.paths, app.state.settings, app.state.settings_error = paths, settings, settings_error
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    @app.middleware("http")
    async def guard(request: Request, call_next):
        # No login (NFR1). Host check stops DNS rebinding; a custom header on writes stops
        # cross-site forms/fetch, since CORS is off and browsers preflight custom headers.
        if request.headers.get("host") not in hosts:
            return errors.error(400, "bad_request", "Host không hợp lệ")
        if request.method in WRITE_METHODS and request.headers.get("x-tutor") != "1":
            return errors.error(403, "forbidden", "Thiếu header X-Tutor: 1")
        return await call_next(request)

    errors.install(app)

    @app.get("/api/health")
    def health() -> dict:
        try:
            with closing(repo.connect(paths.tutor_db, readonly=True)) as c:
                db_ok = repo.schema_version(c) == repo.latest_version()
        except sqlite3.Error:
            db_ok = False
        return {"status": "ok", "version": __version__, "db": "ok" if db_ok else "error", "llm": llm.status(),
                "fake_llm": fake_llm}  # fmt: skip

    for r in (backup, students, catalog, sessions, threads, logs, bank, worksheets, assistant, reports, settings_api):
        app.include_router(r.router)
    app.mount("/v3", StaticFiles(directory=APP_V3_DIR, html=True), name="app-v3")  # before "/", which matches all
    app.mount("/", StaticFiles(directory=APP_DIR, html=True), name="app")
    return app
