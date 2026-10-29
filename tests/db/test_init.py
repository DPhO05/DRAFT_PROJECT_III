import sqlite3

from tutor.db import repo

TABLES = {
    "kc",
    "kc_prereq",
    "error_code",
    "problem",
    "problem_kc",
    "rubric",
    "problem_pair",
    "student",
    "session",
    "attempt",
    "mistake",
    "skill_event",
    "skill_state",
    "misconception_log",
    "recommendation",
    "report",
}


def names(conn, kind):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = ?", (kind,))}


def test_new_db_has_schema_seed_and_latest_version(conn):
    assert names(conn, "table") == TABLES
    assert names(conn, "view") == {"attempt_current", "mistake_current"}
    assert conn.execute("SELECT count(*) FROM error_code").fetchone()[0] == 18
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert repo.schema_version(conn) == repo.latest_version()


def test_init_twice_is_harmless(paths, conn):
    repo.init_db(paths.tutor_db, paths.backup)
    assert conn.execute("SELECT count(*) FROM error_code").fetchone()[0] == 18
    assert list(paths.backup.iterdir()) == []


def baseline(path):
    with repo.connect(path) as c:
        repo.create_schema(c)


def test_migration_raises_user_version(tmp_path):
    db, mig = tmp_path / "t.db", tmp_path / "mig"
    mig.mkdir()
    (mig / "001.sql").write_text("CREATE TABLE extra (x INTEGER);", encoding="utf-8")
    baseline(db)
    assert repo.migrate(db, tmp_path / "bk", mig) == 1
    with repo.connect(db) as c:
        assert repo.schema_version(c) == 1
        assert "extra" in names(c, "table")


def test_migration_001_adds_columns_and_keeps_rows(tmp_path):
    db = tmp_path / "t.db"
    baseline(db)
    with repo.connect(db) as c, repo.write_tx(c):
        c.execute("INSERT INTO kc (code, name, description) VALUES ('K', 'k', 'd')")
    repo.migrate(db, tmp_path / "bk")
    with repo.connect(db) as c:
        assert c.execute("SELECT code, lop FROM kc").fetchall() == [("K", None)]
        cols = {r[1] for r in c.execute("PRAGMA table_info(session)")}
        assert "review_seconds" in cols
    # existing DB with pending migrations is backed up first
    assert len(list((tmp_path / "bk").glob("tutor-*.db"))) == 1


def test_readonly_connection_cannot_write(paths, conn):
    ro = repo.connect(paths.tutor_db, readonly=True)
    try:
        ro.execute("INSERT INTO student (name) VALUES ('x')")
        raise AssertionError("write succeeded")
    except sqlite3.OperationalError:
        pass
    finally:
        ro.close()
