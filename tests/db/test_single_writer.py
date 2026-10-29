"""P0-T04: write SQL only in tutor/db/repo.py; backup() gives a usable copy."""

import ast
import re
import sqlite3
from contextlib import closing
from pathlib import Path

from tutor.db import repo

ROOT = Path(__file__).resolve().parents[2] / "tutor"
WRITE_SQL = re.compile(r"\b(INSERT\s+(OR\s+\w+\s+)?INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|REPLACE\s+INTO)\b", re.I)


def write_sql_outside_repo(root: Path) -> list[str]:
    hits = []
    for f in sorted(root.rglob("*.py")):
        if f == root / "db" / "repo.py":
            continue
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            v = node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else ""
            # tutor_thread lives in checkpoints.db (runner), not in tutor.db
            if WRITE_SQL.search(v) and "tutor_thread" not in v:
                hits.append(f"{f.relative_to(root.parent)}:{node.lineno}")
    return hits


def test_no_write_sql_outside_repo():
    assert write_sql_outside_repo(ROOT) == []


def test_scanner_catches_write_sql(tmp_path):
    pkg = tmp_path / "tutor" / "api"
    pkg.mkdir(parents=True)
    (pkg / "x.py").write_text('q = 1\nSQL = "update student set name = ?"\n', encoding="utf-8")
    assert write_sql_outside_repo(tmp_path / "tutor") == ["tutor/api/x.py:2"]


def test_backup_is_complete_single_file(paths, conn):
    with repo.write_tx(conn):
        conn.executemany("INSERT INTO student (name) VALUES (?)", [("a",), ("b",)])
    dst = repo.backup(paths.tutor_db, paths.backup)
    assert dst.name.startswith("tutor-") and dst.suffix == ".db"
    with closing(sqlite3.connect(dst)) as b:
        assert repo.row_counts(b) == repo.row_counts(conn)
        assert b.execute("PRAGMA journal_mode").fetchone()[0] == "delete"


def test_backup_same_second_does_not_overwrite(paths, conn):
    a = repo.backup(paths.tutor_db, paths.backup)
    b = repo.backup(paths.tutor_db, paths.backup)
    assert a != b and a.exists() and b.exists()


def test_backup_prunes_to_recent_plus_monthly(paths, conn):
    days = ["2024-12-05", "2024-12-20"] + [f"2025-01-{d:02d}" for d in range(1, 32)] + ["2025-02-01", "2025-02-02"]
    for d in days:
        (paths.backup / f"tutor-{d}-120000.db").write_bytes(b"")
    (paths.backup / "keep-me.txt").write_text("not a backup")
    repo.backup(paths.tutor_db, paths.backup, keep_recent=30)
    left = {p.name[6:16] for p in paths.backup.glob("tutor-*.db")}
    assert len(left) == 31  # newest 30 (incl. the new one) + newest of Dec 2024
    assert "2024-12-20" in left and "2024-12-05" not in left
    assert "2025-01-05" in left and "2025-01-04" not in left
    assert (paths.backup / "keep-me.txt").exists()
