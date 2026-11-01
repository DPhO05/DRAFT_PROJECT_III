"""P6-T03: read-only student queries behind the assistant tools, checked against hand-written SQL."""

import pytest

from tests.assistant_fix import CALC, SWAP, world
from tests.db.test_profile_repo import commit, mk, start
from tutor.db import repo
from tutor.services import students

SWAP_WORDS = "Nhầm phép toán hoặc dấu (+/−, ⇒/⇔)"


def rows(conn, sql, *args):
    return conn.execute(sql, args).fetchall()


def set_theta(conn, sid, kc, theta, n=3):
    conn.execute(
        "INSERT OR REPLACE INTO skill_state"
        " (student_id, kc_id, theta, n_attempts, correct_streak, last_seen, updated_at)"
        " VALUES (?, ?, ?, ?, 0, '2026-10-14', '2026-10-14T00:00:00Z')",
        (sid, kc, theta, n),
    )


def test_profile_numbers_match_sql(conn):
    w = world(conn)
    an = w["an"]
    other = rows(conn, "SELECT id FROM kc WHERE id <> ? ORDER BY id LIMIT 2", w["kc_swap"])
    set_theta(conn, an, other[0][0], 0.8)
    set_theta(conn, an, other[1][0], -0.8, n=7)
    p = students.profile(conn, an)
    assert (p["code"], p["grade"]) == ("HS-01", 9)
    count = lambda cond: rows(conn, f"SELECT count(*) FROM skill_state WHERE student_id = ? AND {cond}", an)[0][0]  # noqa: E731
    assert p["counts"] == {
        "vững": count("theta > 0.5"),
        "đang hình thành": count("theta BETWEEN -0.5 AND 0.5"),
        "chưa vững": count("theta < -0.5"),
    }
    assert sum(p["counts"].values()) == len(p["skills"]) == 3
    assert {(s["kc_id"], s["n_attempts"]) for s in p["skills"]} == set(
        rows(conn, "SELECT kc_id, n_attempts FROM skill_state WHERE student_id = ?", an)
    )
    assert {s["kc_id"]: s["level"] for s in p["skills"]} == {
        w["kc_swap"]: "đang hình thành", other[0][0]: "vững", other[1][0]: "chưa vững"
    }  # fmt: skip
    assert [(r["kind"], r["kc_id"], r["kc"], r["count"], r["last_seen"]) for r in p["repeats"]] == rows(
        conn,
        "SELECT e.description, l.kc_id, k.name, l.count, l.last_seen FROM misconception_log l"
        " JOIN error_code e ON e.code = l.code JOIN kc k ON k.id = l.kc_id"
        " WHERE l.student_id = ? AND l.resolved_at IS NULL",
        an,
    )
    assert p["repeats"][0]["kind"] == SWAP_WORDS and p["repeats"][0]["count"] == 2
    assert [(s["held_on"], s["score"], s["max_score"], s["score_10"], s["n_mistakes"]) for s in p["sessions"]] == [
        ("2026-10-14", 1.0, 2.0, 5.0, 1),
        ("2026-10-07", 1.0, 2.0, 5.0, 1),
    ]
    assert rows(conn, "SELECT sum(score), sum(max_score) FROM attempt_current a JOIN session s ON s.id = a.session_id"
                " WHERE s.student_id = ?", an) == [(2.0, 4.0)]  # fmt: skip


def test_profile_keeps_five_latest_sessions(conn):
    w = world(conn)
    p8 = rows(conn, "SELECT problem_id FROM attempt WHERE session_id = 3")[0][0]
    for d in range(15, 21):
        commit(conn, start(conn, w["binh"], f"2026-10-{d}"), [(p8, [])])
    got = students.profile(conn, w["binh"])["sessions"]
    assert [s["held_on"] for s in got] == [f"2026-10-{d}" for d in range(20, 15, -1)]
    assert all(s["n_mistakes"] == 0 for s in got)


def test_mistakes_total_and_filters(conn):
    w = world(conn)
    an, kc = w["an"], w["kc_swap"]
    m = students.mistakes(conn, an)
    assert (m["code"], m["since"], m["total"]) == ("HS-01", None, 2)
    assert m["by_kind"] == [{"kind": SWAP_WORDS, "n": 2}]
    assert [(i["held_on"], i["kind"], i["description"]) for i in m["items"]] == [
        ("2026-10-14", SWAP_WORDS, "d"),
        ("2026-10-07", SWAP_WORDS, "d"),
    ]
    assert set(m["items"][0]) == {"held_on", "ref", "kind", "kc", "description"}
    assert m["items"][0]["kc"] == rows(conn, "SELECT name FROM kc WHERE id = ?", kc)[0][0]
    assert students.mistakes(conn, an, kind=SWAP)["total"] == 2
    assert students.mistakes(conn, an, kind=CALC)["total"] == 0
    assert students.mistakes(conn, an, kc=kc)["total"] == 2
    assert students.mistakes(conn, an, kc=rows(conn, "SELECT kc_id FROM misconception_log WHERE student_id = 2")[0][0])[
        "total"
    ] == 0  # fmt: skip
    since = students.mistakes(conn, an, since="2026-10-10")
    assert (since["since"], since["total"], [i["held_on"] for i in since["items"]]) == (
        "2026-10-10", 1, ["2026-10-14"]
    )  # fmt: skip
    assert students.mistakes(conn, an, since="20261010")["since"] == "2026-10-10"
    capped = students.mistakes(conn, an, limit=1)
    assert (capped["total"], len(capped["items"]), capped["by_kind"][0]["n"]) == (2, 1, 2)


@pytest.mark.parametrize("bad", [{"since": "10/10/2026"}, {"kind": "x.y"}, {"kc": 99999}])
def test_mistakes_bad_filter_is_value_error(conn, bad):
    w = world(conn)
    with pytest.raises(ValueError):
        students.mistakes(conn, w["an"], **bad)


def test_compare_open_repeats(conn):
    world(conn)
    got = students.compare(conn, "open_repeats", kind=SWAP)
    assert got["rows"] == [{"code": "HS-01", "value": 2, "last_seen": "2026-10-14"}]
    assert (got["metric"], got["kind"], got["n_students"], got["total"]) == ("open_repeats", SWAP_WORDS, 2, 2)
    everyone = students.compare(conn, "open_repeats")
    assert [(r["code"], r["value"]) for r in everyone["rows"]] == [("HS-01", 2), ("HS-02", 1)]
    assert everyone["total"] == 3 and everyone["kind"] is None


def test_compare_mistakes_skips_archived(conn):
    w = world(conn)
    p9 = rows(conn, "SELECT problem_id FROM attempt WHERE session_id = 1")[0][0]
    conn.execute("UPDATE student SET archived_at = NULL WHERE id = ?", (w["cuong"],))
    commit(conn, start(conn, w["cuong"], "2026-10-12"), [(p9, [mk(SWAP, w["kc_swap"])] * 3)])
    repo.archive_student(conn, w["cuong"])
    got = students.compare(conn, "mistakes")
    assert [(r["code"], r["value"]) for r in got["rows"]] == [("HS-01", 2), ("HS-02", 1)]
    assert (got["n_students"], got["total"]) == (2, 3)
    assert students.compare(conn, "mistakes", kind=CALC)["rows"] == [
        {"code": "HS-02", "value": 1, "last_seen": "2026-10-14"}
    ]


def test_compare_level_sorted_best_first(conn):
    w = world(conn)
    set_theta(conn, w["binh"], w["kc_swap"], 0.9)
    set_theta(conn, w["an"], w["kc_swap"], -0.9)
    got = students.compare(conn, "level", kc=w["kc_swap"])
    assert [(r["code"], r["value"]) for r in got["rows"]] == [("HS-02", "vững"), ("HS-01", "chưa vững")]
    assert got["n_students"] == 2 and got["total"] is None


@pytest.mark.parametrize("args", [("nope", {}), ("level", {}), ("mistakes", {"kind": "x.y"})])
def test_compare_bad_args_is_value_error(conn, args):
    world(conn)
    with pytest.raises(ValueError):
        students.compare(conn, args[0], **args[1])


@pytest.mark.parametrize("code", ["HS-99", "HS-03", "An", "hs-01 ", ""])
def test_unknown_code(conn, code):
    world(conn)
    with pytest.raises(ValueError, match="Không có học sinh"):
        students.student_id(conn, code)


def test_student_id_of_active(conn):
    w = world(conn)
    assert students.student_id(conn, "HS-01") == w["an"]
    assert students.student_id(conn, "HS-02") == w["binh"]


def test_list_students(conn):
    w = world(conn)
    new = repo.add_student(conn, name="Phạm Thị Dung", grade=7)
    got = students.list_students(conn)
    assert [(s["code"], s["grade"], s["n_sessions"]) for s in got] == [
        ("HS-01", 9, 2), ("HS-02", 8, 1), (f"HS-{new:02d}", 7, 0)
    ]  # fmt: skip
    assert got[0]["last"] == {"held_on": "2026-10-14", "score": 1.0, "max_score": 2.0, "score_10": 5.0}
    assert got[2]["last"] is None
    assert w["cuong"] not in [int(s["code"][3:]) for s in got]


def test_score_10():
    assert students.score_10(13, 20) == 6.5
    assert students.score_10(14, 16) == 9.0
    assert students.score_10(33, 40) == 8.5  # 8.25 rounds half up, not to even
    assert students.score_10(0, 0) == 0
