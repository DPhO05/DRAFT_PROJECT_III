"""World for assistant tests (P6): dummy bank, 3 students, saved sessions with repeated mistakes."""

from datetime import date
from pathlib import Path

from tests.db.test_profile_repo import commit, mk, start
from tutor.db import repo, seed_dummy

BANK = Path(__file__).resolve().parents[1] / "data" / "dummy" / "bank"
SWAP = "notational.operator_swap"
CALC = "computational.intermediate_calc"


def _problem_of_grade(conn, lop: int) -> tuple[int, int]:
    """(problem_id, kc_id) of the first bank problem tagged with a grade-`lop` skill."""
    return conn.execute(
        "SELECT pk.problem_id, pk.kc_id FROM problem_kc pk JOIN kc k ON k.id = pk.kc_id"
        " JOIN problem p ON p.id = pk.problem_id WHERE k.lop = ? ORDER BY p.ref, pk.step_idx LIMIT 1",
        (lop,),
    ).fetchone()


def world(conn) -> dict:
    """An (HS-01, grade 9): 2 sessions, same open repeat twice. Bình (HS-02): 1 session. Cường (HS-03): archived."""
    seed_dummy.seed(conn, BANK)
    an = repo.add_student(conn, name="Nguyễn Văn An", grade=9)
    binh = repo.add_student(conn, name="Trần Thị Bình", grade=8)
    cuong = repo.add_student(conn, name="Lê Văn Cường", grade=9)
    repo.archive_student(conn, cuong)
    p9, kc_swap = _problem_of_grade(conn, 9)
    p8, kc_calc = _problem_of_grade(conn, 8)
    for held_on in ("2026-10-07", "2026-10-14"):
        commit(conn, start(conn, an, held_on), [(p9, [mk(SWAP, kc_swap)])])
    commit(conn, start(conn, binh, "2026-10-14"), [(p8, [mk(CALC, kc_calc)])])
    return {"an": an, "binh": binh, "cuong": cuong, "kc_swap": kc_swap, "today": date(2026, 10, 21)}
