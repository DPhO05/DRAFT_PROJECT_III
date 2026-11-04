"""P8-T02: POST /api/backup/restore (api-v3 §7.1, R7, R19)."""

import sqlite3
from contextlib import closing

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
