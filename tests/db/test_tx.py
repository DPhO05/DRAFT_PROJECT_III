"""MONO-P0-03: every write runs in BEGIN IMMEDIATE."""

import sqlite3
import threading
import time
from contextlib import closing

import pytest

from tutor.db import repo


def test_second_writer_waits_then_sees_first_commit(paths, conn):
    locked = threading.Event()

    def first():
        with closing(repo.connect(paths.tutor_db)) as a, repo.write_tx(a):
            a.execute("INSERT INTO student (name) VALUES ('A')")
            locked.set()
            time.sleep(0.5)

    t = threading.Thread(target=first)
    t.start()
    locked.wait(2)
    t0 = time.monotonic()
    # read-then-write inside the tx: a deferred tx would get SQLITE_BUSY here instead of waiting
    with repo.write_tx(conn):
        n = conn.execute("SELECT count(*) FROM student").fetchone()[0]
        conn.execute("INSERT INTO student (name) VALUES (?)", (f"B{n}",))
    waited = time.monotonic() - t0
    t.join()
    assert waited >= 0.3
    assert [r[0] for r in conn.execute("SELECT name FROM student ORDER BY id")] == ["A", "B1"]


def test_error_rolls_back(conn):
    with pytest.raises(ValueError), repo.write_tx(conn):
        conn.execute("INSERT INTO student (name) VALUES ('x')")
        raise ValueError
    assert conn.execute("SELECT count(*) FROM student").fetchone()[0] == 0
    assert not conn.in_transaction


def test_failed_migration_keeps_version_and_leaves_backup(tmp_path):
    db, mig, bk = tmp_path / "t.db", tmp_path / "mig", tmp_path / "bk"
    mig.mkdir()
    (mig / "001.sql").write_text("CREATE TABLE extra (x);\nINSERT INTO nope VALUES (1);", encoding="utf-8")
    with closing(repo.connect(db)) as c:
        repo.create_schema(c)
    with pytest.raises(repo.MigrationError, match="001.sql"):
        repo.migrate(db, bk, mig)
    with closing(repo.connect(db)) as c:
        assert repo.schema_version(c) == 0
        assert c.execute("SELECT 1 FROM sqlite_master WHERE name = 'extra'").fetchone() is None
    assert len(list(bk.glob("tutor-*.db"))) == 1


def test_deferred_transaction_would_fail(paths, conn):
    """Documents why write_tx exists: the same read-then-write with plain BEGIN errors at once."""
    locked = threading.Event()
    release = threading.Event()

    def first():
        with closing(repo.connect(paths.tutor_db)) as a, repo.write_tx(a):
            a.execute("INSERT INTO student (name) VALUES ('A')")
            locked.set()
            release.wait(2)

    t = threading.Thread(target=first)
    t.start()
    locked.wait(2)
    conn.execute("BEGIN")
    conn.execute("SELECT count(*) FROM student").fetchone()
    release.set()
    t.join()
    with pytest.raises(sqlite3.OperationalError, match="locked|busy"):
        conn.execute("INSERT INTO student (name) VALUES ('B')")
    conn.execute("ROLLBACK")
