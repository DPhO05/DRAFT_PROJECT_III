"""P8-T02: repo.restore puts a chosen backup back into tutor.db (R7)."""

import shutil
import sqlite3
from contextlib import closing

import pytest

from tutor.db import repo


def students(conn, n):
    for i in range(n):
        repo.add_student(conn, name=f"HS {i}", grade=8)


def counts_of(path):
    with closing(sqlite3.connect(path)) as c:
        return repo.row_counts(c)


def start(conn, sha="a" * 64, status="awaiting_review"):
    sid = repo.commit_session_start(conn, student_id=1, held_on="2026-10-20", source_path="s01.tex", source_kind="tex",
                                    sha256=sha, thread_id="g1-hs01-20261020")  # fmt: skip
    repo.commit_session_status(conn, sid, status)
    return sid


def test_rows_equal_backup(paths, conn):
    students(conn, 1)
    b = repo.backup(paths.tutor_db, paths.backup)
    students(conn, 2)
    out = repo.restore(paths.tutor_db, paths.backup, b.name)
    assert repo.row_counts(conn) == counts_of(b)
    assert out["restored"] == b.name and out["sessions_dropped"] == 0
    assert out["rows"] == sum(counts_of(b).values())
    assert counts_of(paths.backup / out["safety_backup"])["student"] == 3


@pytest.mark.parametrize("name", ["../tutor.db", "x.db", "tutor-2026-10-20-120000.db", "tutor-2026-10-20-120000.db\n"])
def test_bad_name_is_not_found(paths, conn, name):
    students(conn, 1)
    before, files = repo.row_counts(conn), sorted(paths.backup.iterdir())
    with pytest.raises(repo.NotFound):
        repo.restore(paths.tutor_db, paths.backup, name)
    assert repo.row_counts(conn) == before and sorted(paths.backup.iterdir()) == files  # no safety backup either


def test_chosen_backup_survives_prune(paths, conn):
    students(conn, 1)
    oldest = repo.backup(paths.tutor_db, paths.backup).rename(paths.backup / "tutor-2020-01-01-000000.db")
    for day in range(2, 32):  # 31 backups in one month: the 30 newest + the month's newest stay
        shutil.copy(oldest, paths.backup / f"tutor-2020-01-{day:02d}-000000.db")
    students(conn, 2)
    repo.restore(paths.tutor_db, paths.backup, oldest.name)
    assert not oldest.exists()  # the safety backup's prune took the file we restored from
    assert repo.row_counts(conn)["student"] == 1


def test_old_backup_is_migrated(tmp_path, paths, conn):
    old = tmp_path / "old"
    old.mkdir()
    for n in ("001", "002"):
        shutil.copy(repo.MIGRATIONS / f"{n}.sql", old / f"{n}.sql")
    old_db = tmp_path / "old.db"
    assert repo.init_db(old_db, tmp_path / "bk", old) == 2
    b = repo.backup(old_db, paths.backup)
    repo.restore(paths.tutor_db, paths.backup, b.name)
    assert repo.schema_version(conn) == repo.latest_version() > 2


def test_uncommitted_sessions_dropped(paths, conn):
    students(conn, 1)
    start(conn)
    b = repo.backup(paths.tutor_db, paths.backup)
    out = repo.restore(paths.tutor_db, paths.backup, b.name)
    assert out["sessions_dropped"] == 1 and repo.row_counts(conn)["session"] == 0
    start(conn, status="running")  # same student, same sha: not a DuplicateSubmission, no date lock


def test_committed_sessions_stay(paths, conn):
    students(conn, 1)
    sid = start(conn)
    conn.execute("UPDATE session SET status = 'committed' WHERE id = ?", (sid,))
    b = repo.backup(paths.tutor_db, paths.backup)
    assert repo.restore(paths.tutor_db, paths.backup, b.name)["sessions_dropped"] == 0
    assert repo.row_counts(conn)["session"] == 1


def test_wal_kept(paths, conn):
    b = repo.backup(paths.tutor_db, paths.backup)
    with closing(sqlite3.connect(b)) as c:
        assert c.execute("PRAGMA journal_mode").fetchone()[0] == "delete"  # backups are single files
    repo.restore(paths.tutor_db, paths.backup, b.name)
    with closing(repo.connect(paths.tutor_db)) as c:
        assert c.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
