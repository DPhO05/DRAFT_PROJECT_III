"""P1-T05: dummy bank for dev/test (C-32)."""

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
