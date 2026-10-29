"""Tiny approved bank for agent / graph tests (2 problems, one without rubric)."""

from tutor.db import repo

P1 = ("8DS-PT1-001", "Giải các phương trình sau: a) $4x - 20 = 0$; b) $5x + 8 = 3x - 4$.")
P2 = ("8DS-PT1-002", "Tìm $m$ để phương trình $2x + m = 5 - x$ nhận $x = 3$ làm nghiệm.")
P9 = ("9DS-PT2-001", "Giải phương trình $x^2 - 5x + 6 = 0$.")


def add_bank(conn) -> None:
    k = repo.add_kc(conn, code="8DS-PT1-01", name="Chuyển vế", description="d", lop=8)
    for ref, st in (P1, P2, P9):
        repo.add_bank_problem(
            conn, ref=ref, statement=st, solution="...", source="test", delta=0.0, tags=[(k, 0, "")],
            rubric_items=[{"item_id": "r1", "text": "t", "points": 1}],
        )  # fmt: skip
    # P2 has no approved rubric: drop it the way a teacher never approved one
    conn.execute("DELETE FROM rubric WHERE problem_id = (SELECT id FROM problem WHERE ref = ?)", (P2[0],))
