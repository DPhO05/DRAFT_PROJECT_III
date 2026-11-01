"""P5-T04: view and edit a problem's skills, level and rubric; history stays, changes apply from now on."""

import pytest

from tests.bankfix import P1, P9, add_bank
from tests.db.test_profile_repo import WRONG, commit, mk, start
from tutor.db import repo
from tutor.services import search

NEW_RUBRIC = [{"text": "a", "points": 2}, {"text": "b", "points": 1.5}]


@pytest.fixture
def made(conn):
    """P1 attempted by one student in a committed session; k2 is a second skill nobody tagged yet."""
    add_bank(conn)
    ids = {r: i for i, r in conn.execute("SELECT id, ref FROM problem")}
    k1 = conn.execute("SELECT id FROM kc").fetchone()[0]
    k2 = repo.add_kc(conn, code="8DS-PT1-02", name="Hoán vị", description="d", lop=8)
    commit(conn, start(conn, repo.add_student(conn, name="A"), "2026-11-01"), [(ids[P1[0]], [mk(WRONG, k1)])])
    return {"k1": k1, "k2": k2, "p1": ids[P1[0]], "p9": ids[P9[0]]}


def snapshot(conn):
    return [
        conn.execute(f"SELECT * FROM {t} ORDER BY 1, 2").fetchall()
        for t in ("problem", "problem_kc", "rubric", "attempt", "skill_event")
    ]


def test_level_change_keeps_history(conn, made):
    events = conn.execute("SELECT * FROM skill_event ORDER BY id").fetchall()
    assert events
    repo.update_problem_labels(conn, made["p1"], level="khó")
    assert conn.execute("SELECT delta FROM problem WHERE id = ?", (made["p1"],)).fetchone()[0] == 0.6
    assert repo.problem_view(conn, made["p1"])["level"] == "khó"
    assert conn.execute("SELECT * FROM skill_event ORDER BY id").fetchall() == events
    repo.update_problem_labels(conn, made["p1"], level=None)
    assert conn.execute("SELECT delta, difficulty_approved_at FROM problem WHERE id = ?", (made["p1"],)).fetchone() == (
        None,
        None,
    )
    assert repo.problem_view(conn, made["p1"])["level"] is None


def test_rubric_edit_new_version(conn, made):
    repo.update_problem_labels(conn, made["p1"], rubric_items=NEW_RUBRIC)
    rub = repo.problem_detail(conn, made["p1"])["rubric"]
    assert (rub["version"], rub["max_score"]) == (2, 3.5)
    assert [i["item_id"] for i in rub["items"]] == ["r1", "r2"]
    old = conn.execute("SELECT r.version FROM attempt a JOIN rubric r ON r.id = a.rubric_id").fetchall()
    assert old == [(1,)]


def test_kc_change_replaces_tags_and_fts(conn, made):
    assert search.search_problems(conn, "Hoán vị") == []
    repo.update_problem_labels(conn, made["p1"], kc_ids=[made["k2"]])
    assert conn.execute("SELECT kc_id, step_idx FROM problem_kc WHERE problem_id = ?", (made["p1"],)).fetchall() == [
        (made["k2"], 0)
    ]
    assert [p["id"] for p in search.search_problems(conn, "Hoán vị")] == [made["p1"]]


@pytest.mark.parametrize(
    "fields",
    [
        {"kc_ids": []},
        {"kc_ids": [9999]},
        {"kc_ids": None},
        {"level": "trung bình"},
        {"rubric_items": []},
        {"rubric_items": [{"text": "a", "points": 0}]},
        {"foo": 1},
        {"level": "khó", "kc_ids": [9999]},
    ],
)
def test_bad_fields(conn, made, fields):
    before = snapshot(conn)
    with pytest.raises(ValueError):
        repo.update_problem_labels(conn, made["p1"], **fields)
    assert snapshot(conn) == before


def test_unknown_problem(conn, made):
    with pytest.raises(repo.NotFound):
        repo.update_problem_labels(conn, 9999, level="dễ")
    with pytest.raises(repo.NotFound):
        repo.problem_view(conn, 9999)


def test_problem_view_superset(conn, made):
    conn.execute("UPDATE problem SET solution_latex = 'a\n\nb' WHERE id = ?", (made["p1"],))
    view = repo.problem_view(conn, made["p1"])
    detail = repo.problem_detail(conn, made["p1"])
    assert all(view[k] == v for k, v in detail.items())
    assert (view["grade"], view["level"], view["has_attempts"], view["solution_steps"]) == (8, "vừa", True, ["a", "b"])
    assert view["topic"]["id"] == made["k1"] and view["source"] == "test" and view["is_new"] is True
    assert repo.problem_view(conn, made["p9"])["has_attempts"] is False


def test_problem_tech(conn, made):
    assert repo.problem_tech(conn, made["p1"]) == {
        "delta": 0.0,
        "difficulty_approved_at": conn.execute("SELECT difficulty_approved_at FROM problem").fetchone()[0],
        "replay_hint": ["tutor replay HS-01"],
    }
    assert repo.problem_tech(conn, made["p9"])["replay_hint"] == []
