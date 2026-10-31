"""Submission texts shared by G1 graph tests."""

from tests.bankfix import P1, P9
from tutor.graphs import threads


def prob(ref, body):
    head = f"[{ref}]" if ref else ""
    return f"\\begin{{problem}}{head}\n{body}\n$x = 1$\n\\end{{problem}}\n"


THREE = prob(P1[0], "LANE1 $4x = 20$") + prob(P9[0], "LANE2 $x^2 = 1$") + prob(P1[0], "LANE3 $5x = 3x - 4$")


def status(conn, session_id):
    return conn.execute("SELECT status FROM session WHERE id = ?", (session_id,)).fetchone()[0]


def approve(r, tid) -> dict:
    """Two resumes: gate_review → 05 stops at gate_confirm_commit → commit ②; returns the final thread row."""
    threads.resume(r, tid)
    row = r.wait(tid)
    assert (row["status"], row["node"]) == ("awaiting_review", "gate_confirm_commit"), row
    threads.resume(r, tid)
    return r.wait(tid)
