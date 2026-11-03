import shutil
import sqlite3

import pytest

from tutor.db import repo


def test_old_rows_become_months(tmp_path):
    db, old = tmp_path / "t.db", tmp_path / "old"
    old.mkdir()
    for n in (1, 2, 3):
        shutil.copy(repo.MIGRATIONS / f"{n:03}.sql", old)
    with repo.connect(db) as c:
        repo.create_schema(c)
    assert repo.migrate(db, tmp_path / "bk", old) == 3
    with repo.connect(db) as c, repo.write_tx(c):
        c.execute("INSERT INTO student (name) VALUES ('A')")
        c.execute(
            "INSERT INTO report (student_id, month, facts_json, text_md, audit_json, approved_at)"
            " VALUES (1, '2026-09', '[]', 't', '[]', 't')"
        )

    assert repo.migrate(db, tmp_path / "bk") == 4

    with repo.connect(db) as c:
        assert repo.schema_version(c) == 4
        assert c.execute("SELECT student_id, period_kind, period_start FROM report").fetchall() == [
            (1, "month", "2026-09-01")
        ]
        week = "INSERT INTO report VALUES (NULL, 1, 'week', '2026-10-19', '[]', 't', '[]', 't')"
        c.execute(week)
        with pytest.raises(sqlite3.IntegrityError):
            c.execute(week)
