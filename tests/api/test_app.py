"""MONO-P0-01: one FastAPI process serving app/ and /api."""

from fastapi.testclient import TestClient

from tutor import __version__
from tutor.api.app import APP_DIR, create_app
from tutor.db import repo


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "version": __version__, "db": "ok", "llm": "unknown", "fake_llm": False}


def test_health_reports_db_error(paths, client):
    paths.tutor_db.unlink()
    paths.tutor_db.write_bytes(b"not a database")
    assert client.get("/api/health").json()["db"] == "error"


def test_serves_app_shell(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert client.get("/api.js").status_code == 200


def test_v3_served(client):
    r = client.get("/v3/")
    assert r.status_code == 200
    assert "<title>" in r.text
    assert client.get("/v3/core.js").status_code == 200
    assert client.get("/").content == (APP_DIR / "index.html").read_bytes()


def test_unknown_host_rejected(client):
    r = client.get("/api/health", headers={"host": "evil.example:8000"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "bad_request"


def test_localhost_host_allowed(client):
    assert client.get("/api/health", headers={"host": "localhost:8000"}).status_code == 200


def test_write_without_x_tutor_forbidden(client):
    r = client.post("/api/backup", json={})
    assert r.status_code == 403
    assert r.json() == {"error": {"code": "forbidden", "message": "Thiếu header X-Tutor: 1", "detail": None}}


def test_unknown_api_path_is_json_404(client):
    r = client.get("/api/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_storage_counts_rows(client):
    r = client.get("/api/backup").json()
    assert r["rows"]["error_code"] == 18
    assert r["total"] == 18
    assert r["backups"] == []


def test_unexpected_error_is_json_500_and_logged(paths, app, monkeypatch):
    def boom(conn):
        raise RuntimeError("gài lỗi")

    monkeypatch.setattr(repo, "row_counts", boom)
    with TestClient(app, base_url="http://127.0.0.1:8000", raise_server_exceptions=False) as c:
        r = c.get("/api/backup")
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "internal"
    assert "gài lỗi" in (paths.logs / "app.log").read_text(encoding="utf-8")


def test_corrupt_settings_start_with_defaults(paths):
    paths.settings.write_text("{oops", encoding="utf-8")
    repo.init_db(paths.tutor_db, paths.backup)
    app = create_app(paths, port=8000)
    with TestClient(app, base_url="http://127.0.0.1:8000") as c:
        assert c.get("/api/health").status_code == 200
    assert app.state.settings["app"]["port"] == 8000
    assert app.state.settings_error
    assert paths.settings.read_text(encoding="utf-8") == "{oops"
