"""P8-T02: POST /api/backup/restore (api-v3 §7.1, R7, R19)."""

import os
import sqlite3
from contextlib import closing

import pytest

from tests.api.test_sessions import W
from tutor.db import repo


def counts_of(path):
    with closing(sqlite3.connect(path)) as c:
        return repo.row_counts(c)


def student(client, name):
    return client.post("/api/students", json={"name": name, "grade": 8}, headers=W).json()["id"]


def test_restore_returns_rows_of_the_backup(paths, client):
    student(client, "Lê An")
    made = client.post("/api/backup", headers=W).json()
    student(client, "Võ Bình")
    r = client.post("/api/backup/restore", json={"name": made["path"]}, headers=W)
    assert r.status_code == 200
    body = r.json()
    assert body["restored"] == made["path"] and body["rows"] == made["rows"]
    assert (body["sessions_dropped"], body["threads_removed"]) == (0, 0)
    assert counts_of(paths.backup / body["safety_backup"])["student"] == 2
    assert [s["name"] for s in client.get("/api/students").json()] == ["Lê An"]


def test_unknown_backup_is_404(paths, client):
    for name in ("x.db", "../tutor.db", "tutor-2026-10-20-120000.db"):
        r = client.post("/api/backup/restore", json={"name": name}, headers=W)
        assert r.status_code == 404 and r.json()["error"]["code"] == "not_found", name
    assert list(paths.backup.iterdir()) == []


def test_unfinished_thread_is_409_and_nothing_changes(paths, app, client):
    made = client.post("/api/backup", headers=W).json()
    app.state.runner._set("g1-hs01-20261020", create=True, graph="G1", status="awaiting_review", student_id=1)
    student(client, "Lê An")
    r = client.post("/api/backup/restore", json={"name": made["path"]}, headers=W)
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "not_ready" and err["detail"]["reason"] == "unfinished"
    assert err["detail"]["threads"] == [{"thread_id": "g1-hs01-20261020", "graph": "G1", "status": "awaiting_review",
                                         "running": False}]  # fmt: skip
    assert [p.name for p in paths.backup.iterdir()] == [made["path"]]
    assert len(client.get("/api/students").json()) == 1


def test_restore_needs_x_tutor_header(client):
    r = client.post("/api/backup/restore", json={"name": "x.db"})
    assert r.status_code == 403


def test_corrupt_backup_is_422_with_words_even_while_work_is_unfinished(paths, app, client):
    bad = paths.backup / "tutor-2026-10-20-120000.db"
    bad.write_bytes(b"not a database " * 200)
    app.state.runner._set("g1-hs01-20261020", create=True, graph="G1", status="awaiting_review", student_id=1)
    r = client.post("/api/backup/restore", json={"name": bad.name}, headers=W)
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    assert r.json()["error"]["message"] == "Bản sao lưu này bị hỏng, không khôi phục được."
    assert list(paths.backup.iterdir()) == [bad]  # asking the teacher to drop work would be for nothing


def test_failure_after_the_copy_is_500_naming_the_safety_file(paths, client, monkeypatch):
    student(client, "Lê An")
    made = client.post("/api/backup", headers=W).json()
    student(client, "Võ Bình")

    def boom(*a, **kw):
        raise repo.MigrationError("004.sql: gài lỗi")

    monkeypatch.setattr(repo, "migrate", boom)
    r = client.post("/api/backup/restore", json={"name": made["path"]}, headers=W)
    safety = next(p.name for p in paths.backup.iterdir() if p.name != made["path"])
    assert r.status_code == 500 and r.json()["error"]["code"] == "restore_failed"
    assert safety in r.json()["error"]["message"]
    assert len(client.get("/api/students").json()) == 2  # the data is back as it was
    assert "MigrationError: 004.sql: gài lỗi" in (paths.logs / "app.log").read_text(encoding="utf-8")


def test_backup_of_a_newer_app_is_422_and_nothing_moves(paths, client):
    student(client, "Lê An")
    made = client.post("/api/backup", headers=W).json()
    with closing(sqlite3.connect(paths.backup / made["path"])) as c:
        c.execute(f"PRAGMA user_version = {repo.latest_version() + 1}")
    db_bytes = paths.tutor_db.read_bytes()
    r = client.post("/api/backup/restore", json={"name": made["path"]}, headers=W)
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    assert r.json()["error"]["message"] == "Bản sao lưu này của bản app mới hơn, cập nhật app trước."
    assert paths.tutor_db.read_bytes() == db_bytes
    assert [p.name for p in paths.backup.iterdir()] == [made["path"]]


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file modes")
def test_unwritable_backup_folder_is_500_with_words_and_nothing_moves(paths, client):
    student(client, "Lê An")
    made = client.post("/api/backup", headers=W).json()
    student(client, "Võ Bình")
    db_bytes = paths.tutor_db.read_bytes()
    paths.backup.chmod(0o555)
    try:
        r = client.post("/api/backup/restore", json={"name": made["path"]}, headers=W)
    finally:
        paths.backup.chmod(0o755)
    err = r.json()["error"]
    assert r.status_code == 500 and err["code"] == "restore_failed"
    assert err["message"] == "Không sao lưu được dữ liệu hiện tại (ổ đầy hoặc không ghi được), chưa khôi phục gì."
    assert paths.tutor_db.read_bytes() == db_bytes and not list(paths.root.glob("tutor.db.broken*"))
    assert len(client.get("/api/students").json()) == 2
    assert "OperationalError" in (paths.logs / "app.log").read_text(encoding="utf-8")
