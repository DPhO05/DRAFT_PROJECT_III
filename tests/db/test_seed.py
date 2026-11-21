"""P1-T05: dummy bank for dev/test (C-32)."""

import hashlib
from pathlib import Path

from tutor.db import repo, seed_dummy

BANK = Path(__file__).resolve().parents[2] / "data" / "dummy" / "bank"


def test_seed_loads_bank_with_tags_rubrics_delta(conn):
    seed_dummy.seed(conn, BANK)
    n = repo.row_counts(conn)
    assert (n["problem"], n["rubric"], n["kc"]) == (310, 310, 74)
    q = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
    assert q("SELECT count(*) FROM problem WHERE delta IS NOT NULL AND difficulty_approved_at IS NOT NULL") == 310
    assert q("SELECT count(*) FROM problem WHERE id NOT IN (SELECT problem_id FROM problem_kc)") == 0
    assert q("SELECT delta FROM problem WHERE ref = '8DS-PT1-001'") == -1.2  # (1 - 3) * 0.6
    items = conn.execute("SELECT items_json, max_score FROM rubric r JOIN problem p ON p.id = r.problem_id "
                         "WHERE p.ref = '8DS-PT1-001'").fetchone()  # fmt: skip
    assert items[1] == 5 and "Đáp số" in items[0]  # 6 paragraphs, Đáp số merged into the last item
    seed_dummy.seed(conn, BANK)
    assert repo.row_counts(conn)["problem"] == 310  # idempotent


def test_extended_bank_is_valid_labeled_and_new(conn):
    """bank-mo-rong: 20 new problems per topic file, imported through Ngân hàng (G2) on top of the dummy bank."""
    from tutor.services import bank

    seed_dummy.seed(conn, BANK)
    kc_id = {k["code"]: k["id"] for k in repo.list_kc(conn)}
    have = {r[0] for r in conn.execute("SELECT ref FROM problem")}
    files = sorted((BANK.parent / "bank-mo-rong").glob("*.tex"))
    items = [i for f in files for i in bank.read_bank(f.read_text(encoding="utf-8"), kc_id)]
    assert len(files) == 10 and len(items) == 200
    assert [i.ref for i in items if i.invalid or i.needs or i.unknown_label] == []
    refs = [i.ref for i in items]
    assert len(set(refs)) == 200 and not set(refs) & have


SNAPSHOT = {
    "kc": "918107634027b8c280ae6f32ac2b00131553e73b78b63a3d6bc34d742b6aa038",
    "kc_prereq": "e5b135c78d684a9b1aa613d40549bec382ee61f599b2cf40c693efb8c60513ab",
    "problem": "25084097932f13b2f9ff547ee316d0f6c42abec6bdfa767ff904eea258e816ce",
    "problem_kc": "f896cc6d76b106107f7a3a2523b2a7c88b1b58612220b64d84fd21a3ab13bc8f",
    "rubric": "7cb646a8c391f6588663f0d18f033e45cd26ba9d101defbaaad9593754a065c7",
}
_TIME_COLS = {"created_at", "approved_at", "difficulty_approved_at"}


def test_seed_snapshot_unchanged(conn):
    seed_dummy.seed(conn, BANK)
    got = {}
    for table in ("kc", "kc_prereq", "problem", "problem_kc", "rubric"):
        info = conn.execute(f"PRAGMA table_info({table})").fetchall()
        cols = ", ".join(f"{c[1]} IS NULL AS {c[1]}" if c[1] in _TIME_COLS else c[1] for c in info)
        pk = ", ".join(c[1] for c in sorted((c for c in info if c[5]), key=lambda c: c[5]))
        rows = [tuple(r) for r in conn.execute(f"SELECT {cols} FROM {table} ORDER BY {pk}")]
        got[table] = hashlib.sha256(repr(rows).encode()).hexdigest()
    assert got == SNAPSHOT
