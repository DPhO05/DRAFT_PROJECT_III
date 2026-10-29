"""Reads the 02 · 03 · 04 lanes need (P2-T01..T04)."""

import json

from tutor.db import repo


def bank(conn):
    k1 = repo.add_kc(conn, code="8DS-PT1-01", name="Chuyển vế", description="d", lop=8)
    k2 = repo.add_kc(conn, code="8DS-PT1-02", name="Thu gọn", description="d", lop=8)
    items = [{"item_id": "r1", "text": "Chuyển vế", "points": 1}, {"item_id": "r2", "text": "Đáp số", "points": 2}]
    pid = repo.add_bank_problem(conn, ref="8DS-PT1-001", statement="Giải $4x = 20$.", solution="$x = 5$",
                                source="t", delta=0.0, tags=[(k1, 1, ""), (k2, 2, "")], rubric_items=items)  # fmt: skip
    return pid, k1, k2


def test_problem_detail_has_kcs_and_latest_rubric(conn):
    pid, k1, k2 = bank(conn)
    conn.execute(
        "INSERT INTO rubric (problem_id, version, items_json, max_score, approved_at) VALUES (?, 2, ?, 4, 'x')",
        (pid, json.dumps([{"item_id": "r1", "text": "t", "points": 4}])),
    )
    p = repo.problem_detail(conn, pid)
    assert (p["ref"], p["statement_latex"], p["solution_latex"]) == ("8DS-PT1-001", "Giải $4x = 20$.", "$x = 5$")
    assert [k["id"] for k in p["kcs"]] == [k1, k2] and p["kcs"][0]["code"] == "8DS-PT1-01"
    assert p["rubric"]["version"] == 2 and p["rubric"]["max_score"] == 4 and p["rubric"]["items"][0]["points"] == 4


def test_problem_detail_without_rubric(conn):
    pid, *_ = bank(conn)
    conn.execute("DELETE FROM rubric")
    assert repo.problem_detail(conn, pid)["rubric"] is None


def test_error_codes_active_only(conn):
    conn.execute("UPDATE error_code SET active = 0 WHERE code = 'notational.symbol'")
    all_codes = {c["code"] for c in repo.error_codes(conn)}
    active = {c["code"] for c in repo.error_codes(conn, active_only=True)}
    assert all_codes - active == {"notational.symbol"} and len(all_codes) == 18


def test_recent_mistakes_are_5_latest_approved_of_the_student(conn):
    pid, k1, _ = bank(conn)
    rid = conn.execute("SELECT id FROM rubric").fetchone()[0]
    a = repo.add_student(conn, name="A", grade=8)
    b = repo.add_student(conn, name="B", grade=8)
    for n, (sid, day) in enumerate([(a, "2026-10-01"), (a, "2026-10-08"), (b, "2026-10-09")]):
        s = conn.execute(
            "INSERT INTO session (student_id, held_on, source_path, source_kind, source_sha256, thread_id, status)"
            " VALUES (?, ?, 'p', 'tex', ?, ?, 'committed')", (sid, day, f"h{n}", f"t{n}"),
        ).lastrowid  # fmt: skip
        at = conn.execute(
            "INSERT INTO attempt (session_id, seq, problem_id, rubric_id, solution_latex, steps_json, grade_json,"
            " score, max_score) VALUES (?, 1, ?, ?, 'x', '[]', '[]', 0, 3)", (s, pid, rid),
        ).lastrowid  # fmt: skip
        for i, st in enumerate(["confirmed", "rejected", "edited", "added"]):
            conn.execute(
                "INSERT INTO mistake (attempt_id, step_idx, code, kc_id, description, evidence_latex, status,"
                " llm_json, reviewed_at) VALUES (?, ?, 'other.unclear', ?, ?, 'e', ?, ?, 'x')",
                (at, i, k1, f"{day}-{st}", st, None if st == "added" else "{}"),
            )
    rows = repo.recent_mistakes(conn, a)
    assert [r["description"] for r in rows] == [
        "2026-10-08-added", "2026-10-08-edited", "2026-10-08-confirmed", "2026-10-01-added", "2026-10-01-edited",
    ]  # fmt: skip
    assert rows[0].keys() >= {"code", "kc_id", "description", "held_on"}
