"""C-17: the 7 kinds of bad data the schema must reject (P0 "xong khi")."""

import sqlite3

import pytest

BASE = """
INSERT INTO student (id, name) VALUES (1, 'A');
INSERT INTO kc (id, code, name, description) VALUES (1, 'K1', 'k1', 'd'), (2, 'K2', 'k2', 'd');
INSERT INTO problem (id, ref, statement_latex, solution_latex) VALUES (1, 'P-001', 's', 's');
INSERT INTO rubric (id, problem_id, version, items_json, max_score, approved_at) VALUES (1, 1, 1, '[]', 1, 't');
INSERT INTO session (id, student_id, held_on, source_path, source_kind, source_sha256, thread_id, status)
  VALUES (1, 1, '2026-10-20', 'inbox/a.tex', 'tex', 'aa', 'g1-a', 'running');
INSERT INTO attempt (id, session_id, seq, problem_id, rubric_id, solution_latex, steps_json, grade_json, score,
  max_score) VALUES (1, 1, 1, 1, 1, 'x', '[]', '[]', 0, 1);
"""

MISTAKE = (
    "INSERT INTO mistake (attempt_id, step_idx, code, description, evidence_latex, status, llm_json, reviewed_at)"
    " VALUES (1, 1, 'other.unclear', 'd', 'e', ?, ?, 't')"
)
ATTEMPT = (
    "INSERT INTO attempt (session_id, seq, problem_id, rubric_id, solution_latex, steps_json, grade_json, score,"
    " max_score) VALUES (?, 2, 1, 1, 'x', '[]', '[]', 0, 1)"
)
SESSION = (
    "INSERT INTO session (student_id, held_on, source_path, source_kind, source_sha256, thread_id, status)"
    " VALUES (1, '2026-10-21', 'inbox/b.tex', 'tex', ?, 'g1-b', 'running')"
)
REPORT = (
    "INSERT INTO report (student_id, period_kind, period_start, facts_json, text_md, audit_json, approved_at)"
    " VALUES (1, ?, ?, '[]', 't', '[]', 't')"
)

# (name, sql, good params, bad params): good proves the row is otherwise valid.
CASES = [
    ("1 fk attempt.session_id", ATTEMPT, (1,), (999,)),
    ("2 kc_prereq self", "INSERT INTO kc_prereq (kc_id, prereq_id) VALUES (1, ?)", (2,), (1,)),
    (
        "3 error_code.category",
        "INSERT INTO error_code (code, category, description) VALUES ('x.y', ?, 'd')",
        ("other",),
        ("style",),
    ),
    ("4 duplicate submission", SESSION, ("bb",), ("aa",)),
    ("5 mistake.status proposed", MISTAKE, ("confirmed", "{}"), ("proposed", "{}")),
    ("6a added with llm_json", MISTAKE, ("added", None), ("added", "{}")),
    ("6b non-added without llm_json", MISTAKE, ("edited", "{}"), ("edited", None)),
    ("7 report.period_kind", REPORT, ("week", "2026-10-19"), ("year", "2026-10-19")),
]


@pytest.fixture
def db(conn):
    conn.executescript(BASE)
    return conn


@pytest.mark.parametrize(("name", "sql", "good", "bad"), CASES, ids=[c[0] for c in CASES])
def test_schema_rejects_bad_row(db, name, sql, good, bad):
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(sql, bad)
    db.execute(sql, good)
