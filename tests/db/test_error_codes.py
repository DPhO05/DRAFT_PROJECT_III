"""P2-T07: teacher edits the error_code taxonomy (03 Diagnoser reads the active codes + example)."""

import csv
import io

import pytest

from tutor.db import repo


def test_add_error_code(conn):
    e = repo.add_error_code(conn, code="computational.sign_rule", category="computational",
                            description=" Sai quy tắc dấu ", example="$-(x - 3) = -x - 3$")  # fmt: skip
    assert e == {"code": "computational.sign_rule", "category": "computational", "description": "Sai quy tắc dấu",
                 "example": "$-(x - 3) = -x - 3$", "active": 1}  # fmt: skip
    assert "computational.sign_rule" in {c["code"] for c in repo.error_codes(conn, active_only=True)}


@pytest.mark.parametrize(
    "code, category, description",
    [
        ("conceptual.sign_rule", "computational", "d"),  # prefix is not the category
        ("computational.Sign", "computational", "d"),
        ("computational.", "computational", "d"),
        ("computational.a.b", "computational", "d"),
        ("algebra.sign", "algebra", "d"),  # not one of the 5 groups
        ("computational.sign", "computational", " "),
    ],
)
def test_add_error_code_invalid(conn, code, category, description):
    with pytest.raises(ValueError):
        repo.add_error_code(conn, code=code, category=category, description=description)
    assert len(repo.error_codes(conn)) == 18


def test_add_error_code_duplicate(conn):
    with pytest.raises(ValueError, match="đã có"):
        repo.add_error_code(conn, code="other.unclear", category="other", description="d")


def test_update_error_code(conn):
    e = repo.update_error_code(conn, "notational.symbol", description="Ký hiệu sai", example="$x^2 = x.2$")
    assert (e["description"], e["example"], e["active"]) == ("Ký hiệu sai", "$x^2 = x.2$", 1)
    e = repo.update_error_code(conn, "notational.symbol", example="", active=False)
    assert (e["description"], e["example"], e["active"]) == ("Ký hiệu sai", None, 0)
    assert "notational.symbol" not in {c["code"] for c in repo.error_codes(conn, active_only=True)}
    assert repo.update_error_code(conn, "notational.symbol", active=True)["active"] == 1


def test_update_error_code_rules(conn):
    with pytest.raises(repo.NotFound):
        repo.update_error_code(conn, "other.nope", description="d")
    with pytest.raises(ValueError, match="other.unclear khoá"):
        repo.update_error_code(conn, "other.unclear", active=False)
    with pytest.raises(ValueError):
        repo.update_error_code(conn, "other.unclear", description=" ")
    assert repo.update_error_code(conn, "other.unclear", example="$?$")["active"] == 1


def test_error_code_mistakes(conn):
    kc = repo.add_kc(conn, code="K", name="k", description="d", lop=8)
    items = [{"item_id": "r1", "text": "t", "points": 1}]
    pid = repo.add_bank_problem(conn, ref="8DS-001", statement="s", solution="x", source="t", delta=0.0,
                                tags=[(kc, 1, "")], rubric_items=items)  # fmt: skip
    rid = conn.execute("SELECT id FROM rubric").fetchone()[0]
    sid = repo.add_student(conn, name="A", grade=8)
    for n, day in enumerate(["2026-10-01", "2026-10-08"]):
        s = conn.execute(
            "INSERT INTO session (student_id, held_on, source_path, source_kind, source_sha256, thread_id, status)"
            " VALUES (?, ?, 'p', 'tex', ?, ?, 'committed')", (sid, day, f"h{n}", f"t{n}"),
        ).lastrowid  # fmt: skip
        at = conn.execute(
            "INSERT INTO attempt (session_id, seq, problem_id, rubric_id, solution_latex, steps_json, grade_json,"
            " score, max_score) VALUES (?, 1, ?, ?, 'x', '[]', '[]', 0, 1)", (s, pid, rid),
        ).lastrowid  # fmt: skip
        for i, (code, st) in enumerate([("notational.symbol", "confirmed"), ("notational.symbol", "rejected"),
                                        ("other.unclear", "added")]):  # fmt: skip
            conn.execute(
                "INSERT INTO mistake (attempt_id, step_idx, code, kc_id, description, evidence_latex, status,"
                " llm_json, reviewed_at) VALUES (?, ?, ?, ?, ?, 'e', ?, ?, 'x')",
                (at, i + 1, code, kc, f"{day}-{st}", st, None if st == "added" else "{}"),
            )
    rows = repo.error_code_mistakes(conn, "notational.symbol")
    assert [r["description"] for r in rows] == ["2026-10-08-confirmed", "2026-10-01-confirmed"]
    r = rows[0]
    assert (r["student_code"], r["held_on"], r["ref"], r["step_idx"], r["status"], r["thread_id"]) == (
        "HS-01", "2026-10-08", "8DS-001", 1, "confirmed", "t1",
    )  # fmt: skip
    assert repo.error_code_mistakes(conn, "presentation.units") == []
    with pytest.raises(repo.NotFound):
        repo.error_code_mistakes(conn, "other.nope")


def test_export_error_codes(conn):
    repo.update_error_code(conn, "notational.symbol", example="$a, b$", active=False)
    rows = list(csv.DictReader(io.StringIO(repo.export_error_codes(conn))))
    assert len(rows) == 18 and list(rows[0]) == ["code", "category", "description", "example", "active"]
    sym = next(r for r in rows if r["code"] == "notational.symbol")
    assert (sym["example"], sym["active"]) == ("$a, b$", "0")
