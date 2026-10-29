"""P1-T06: students (minimal)."""

import pytest

from tutor.db import repo


def test_add_list_update_archive(conn):
    sid = repo.add_student(conn, name="Nguyễn Văn An", grade=8)
    [s] = repo.list_students(conn)
    assert (s["id"], s["code"], s["name"], s["grade"]) == (sid, f"HS-{sid:02d}", "Nguyễn Văn An", 8)
    repo.update_student(conn, sid, note="yếu phân thức")
    assert repo.list_students(conn)[0]["note"] == "yếu phân thức"
    assert repo.archive_student(conn, sid)
    assert repo.list_students(conn) == []
    assert repo.list_students(conn, include_archived=True)[0]["archived_at"]


def test_validation_and_not_found(conn):
    with pytest.raises(ValueError):
        repo.add_student(conn, name="  ")
    with pytest.raises(ValueError):
        repo.add_student(conn, name="A", grade=13)
    with pytest.raises(repo.NotFound):
        repo.update_student(conn, 99, name="x")
