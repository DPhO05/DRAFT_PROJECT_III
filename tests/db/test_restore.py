"""P8-T02: repo.restore puts a chosen backup back into tutor.db (R7)."""

import errno
import os
import re
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

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
    students(conn, 1)  # the 30 newer copies hold 2 students, the oldest only 1
    newer = repo.backup(paths.tutor_db, paths.backup).rename(paths.backup / "tutor-2020-01-02-000000.db")
    for day in range(3, 32):  # 31 backups in one month: the 30 newest + the month's newest stay
        shutil.copy(newer, paths.backup / f"tutor-2020-01-{day:02d}-000000.db")
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


def garbage(path, size=2000):
    path.write_bytes(b"not a database " * size)


@pytest.mark.parametrize("content", [b"not a database " * 200, b""])
def test_corrupt_backup_fails_before_anything_moves(paths, conn, content):
    students(conn, 1)
    bad = paths.backup / "tutor-2026-10-20-120000.db"
    bad.write_bytes(content)
    before = repo.row_counts(conn)
    with pytest.raises(repo.BackupCorrupt, match="Bản sao lưu này bị hỏng, không khôi phục được."):
        repo.restore(paths.tutor_db, paths.backup, bad.name)
    assert repo.row_counts(conn) == before and list(paths.backup.iterdir()) == [bad]


def test_unreadable_tutor_db_is_set_aside_and_restore_goes_on(paths):
    repo.init_db(paths.tutor_db, paths.backup)
    with closing(repo.connect(paths.tutor_db)) as c:
        students(c, 1)
        start(c)
    b = repo.backup(paths.tutor_db, paths.backup)
    garbage(paths.tutor_db)
    paths.tutor_db.with_name("tutor.db-wal").write_bytes(b"wal bytes")
    paths.tutor_db.with_name("tutor.db-shm").write_bytes(b"shm bytes")
    out = repo.restore(paths.tutor_db, paths.backup, b.name)
    kept = out["safety_backup"]
    assert re.fullmatch(r"tutor\.db\.broken-\d{8}-\d{6}", kept) and not repo._BACKUP_RE.match(kept)
    assert (paths.root / kept).read_bytes() == b"not a database " * 2000
    assert (paths.root / f"{kept}-wal").read_bytes() == b"wal bytes"
    assert (paths.root / f"{kept}-shm").read_bytes() == b"shm bytes"
    assert out["sessions_dropped"] == 1 and list(paths.backup.iterdir()) == [b]  # no half-written "backup" either
    with closing(repo.connect(paths.tutor_db)) as c:
        assert repo.row_counts(c) == counts_of(b) | {"session": 0}
        assert c.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_failure_after_the_copy_puts_the_data_back(paths, conn, monkeypatch):
    students(conn, 1)
    b = repo.backup(paths.tutor_db, paths.backup)
    students(conn, 2)
    before = repo.row_counts(conn)

    def boom(*a, **kw):
        raise repo.MigrationError("004.sql: gài lỗi")

    monkeypatch.setattr(repo, "migrate", boom)
    with pytest.raises(repo.RestoreFailed) as e:
        repo.restore(paths.tutor_db, paths.backup, b.name)
    safety = next(p for p in paths.backup.iterdir() if p != b)
    assert safety.name in str(e.value) and e.value.safety == safety.name
    assert repo.row_counts(conn) == before == counts_of(safety)
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def bump_version(path):
    with closing(sqlite3.connect(path)) as c:
        c.execute(f"PRAGMA user_version = {repo.latest_version() + 1}")


def test_backup_of_a_newer_app_is_refused_before_anything_moves(paths, conn):
    students(conn, 1)
    b = repo.backup(paths.tutor_db, paths.backup)
    bump_version(b)
    students(conn, 1)
    before, db_bytes = repo.row_counts(conn), paths.tutor_db.read_bytes()
    with pytest.raises(repo.BackupTooNew, match="Bản sao lưu này của bản app mới hơn, cập nhật app trước."):
        repo.restore(paths.tutor_db, paths.backup, b.name)
    assert paths.tutor_db.read_bytes() == db_bytes and repo.row_counts(conn) == before
    assert list(paths.backup.iterdir()) == [b]  # no safety backup


needs_perms = pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file modes")


@needs_perms
def test_unwritable_backup_folder_leaves_a_healthy_tutor_db_alone(paths, conn):
    students(conn, 1)
    b = repo.backup(paths.tutor_db, paths.backup)
    students(conn, 1)
    db_bytes, before = paths.tutor_db.read_bytes(), repo.row_counts(conn)
    paths.backup.chmod(0o555)
    try:
        with pytest.raises(repo.NotRestored, match="Không sao lưu được dữ liệu hiện tại .*chưa khôi phục gì."):
            repo.restore(paths.tutor_db, paths.backup, b.name)
    finally:
        paths.backup.chmod(0o755)
    assert paths.tutor_db.read_bytes() == db_bytes and repo.row_counts(conn) == before
    assert not list(paths.root.glob("tutor.db.broken*")) and list(paths.backup.iterdir()) == [b]


@needs_perms
def test_unreadable_backup_is_not_called_damaged(paths, conn):
    students(conn, 1)
    b = repo.backup(paths.tutor_db, paths.backup)
    before = repo.row_counts(conn)
    b.chmod(0)
    try:
        with pytest.raises(repo.NotRestored, match="Không đọc được bản sao lưu này .*chưa khôi phục gì."):
            repo.restore(paths.tutor_db, paths.backup, b.name)
    finally:
        b.chmod(0o644)
    assert repo.row_counts(conn) == before and not list(paths.root.glob("tutor.db.broken*"))


def backup_made_elsewhere(tmp_path, paths):
    """A backup with 1 student in paths.backup, taken from a tutor.db that is not at paths.tutor_db."""
    src = tmp_path / "src.db"
    repo.init_db(src, tmp_path / "bk")
    with closing(repo.connect(src)) as c:
        students(c, 1)
    return repo.backup(src, paths.backup)


def test_missing_tutor_db_gets_no_safety_backup(tmp_path, paths):
    b = backup_made_elsewhere(tmp_path, paths)
    assert not paths.tutor_db.exists()  # a new Mac
    out = repo.restore(paths.tutor_db, paths.backup, b.name)
    assert out["safety_backup"] is None and list(paths.backup.iterdir()) == [b]  # no empty "backup" in the list
    assert counts_of(paths.tutor_db)["student"] == 1


def test_missing_tutor_db_failure_leaves_nothing_behind(tmp_path, paths, monkeypatch):
    b = backup_made_elsewhere(tmp_path, paths)

    def boom(*a, **kw):
        raise repo.MigrationError("004.sql: gài lỗi")

    monkeypatch.setattr(repo, "migrate", boom)
    with pytest.raises(repo.NotRestored) as e:  # no data from before exists, so there is no safety file to name
        repo.restore(paths.tutor_db, paths.backup, b.name)
    assert isinstance(e.value.__cause__, repo.MigrationError)
    assert not list(paths.root.glob("tutor.db*")) and list(paths.backup.iterdir()) == [b]


def test_set_aside_writes_the_kept_copies_before_moving_tutor_db(paths, monkeypatch):
    repo.init_db(paths.tutor_db, paths.backup)
    b = repo.backup(paths.tutor_db, paths.backup)
    garbage(paths.tutor_db)
    paths.tutor_db.with_name("tutor.db-wal").write_bytes(b"wal bytes")
    paths.tutor_db.with_name("tutor.db-shm").write_bytes(b"shm bytes")
    real = Path.write_bytes

    def disk_full(self, data):  # the -wal copy is written, the -shm copy is not
        if self.name.endswith("-shm") and ".broken-" in self.name:
            raise OSError(errno.ENOSPC, "No space left on device")
        return real(self, data)

    monkeypatch.setattr(Path, "write_bytes", disk_full)
    with pytest.raises(repo.NotRestored) as e:
        repo.restore(paths.tutor_db, paths.backup, b.name)
    assert isinstance(e.value.__cause__, OSError)
    assert paths.tutor_db.read_bytes() == b"not a database " * 2000  # still where it was
    assert not list(paths.root.glob("tutor.db.broken*")) and list(paths.backup.iterdir()) == [b]


def test_restore_leaves_the_env_file_alone(paths, conn):
    env = paths.root / ".env"
    env.write_bytes(b"OPENAI_API_KEY=sk-test-fake\n\xff\n")
    students(conn, 1)
    b = repo.backup(paths.tutor_db, paths.backup)
    students(conn, 1)
    repo.restore(paths.tutor_db, paths.backup, b.name)
    assert env.read_bytes() == b"OPENAI_API_KEY=sk-test-fake\n\xff\n"
