"""P7-T08: student reads behind the Học sinh tab (api-v3 §4), checked against hand-written SQL."""

import json
import re

from tests.assistant_fix import CALC, SWAP, _problem_of_grade, world
from tests.db.test_profile_repo import commit, mk, start
from tests.services.test_student_reads import set_theta
from tutor.db import repo
from tutor.services import elo, students

SWAP_WORDS = "Nhầm phép toán hoặc dấu (+/−, ⇒/⇔)"
EMPTY = {"dates": [], "all": [], "skills": {}}
LEVELS = ["vững", "đang hình thành", "chưa vững"]
CODE = re.compile(r"\b(computational|conceptual|notational|presentation|other)\.\w+")


def pos(theta):
    return max(0, min(100, round((theta + 1.5) / 3 * 100)))


def sql(conn, query, *args):
    return conn.execute(query, args).fetchall()


def test_skill_levels_match_state(conn):
    w = world(conn)
    an, kc = w["an"], w["kc_swap"]
    lo, hi = (r[0] for r in sql(conn, "SELECT id FROM kc WHERE id <> ? ORDER BY id LIMIT 2", kc))
    set_theta(conn, an, hi, 0.8)
    set_theta(conn, an, lo, -0.8, n=7)
    got = students.skills(conn, an)
    state = dict(sql(conn, "SELECT kc_id, theta FROM skill_state WHERE student_id = ?", an))
    assert {s["kc_id"]: s["level"] for s in got} == {k: elo.level(t) for k, t in state.items()}
    assert {s["level"] for s in got} == set(LEVELS)
    name, topic = sql(
        conn,
        "SELECT k.name, p.name FROM kc k JOIN kc p ON p.id = k.parent_id WHERE k.id = ?",
        kc,
    )[0]
    swap = next(s for s in got if s["kc_id"] == kc)
    assert swap == {
        "kc_id": kc, "kc": name, "topic": topic, "level": "đang hình thành",
        "trend": "cần ôn", "last_seen": "2026-10-14", "n_attempts": 2,
    }  # fmt: skip
    # set by hand, no skill_event: the arrow stays flat
    assert {s["trend"] for s in got if s["kc_id"] in (lo, hi)} == {"giữ"}


def test_trend_latest_session(conn):
    w = world(conn)
    an, kc = w["an"], w["kc_swap"]
    p9, _ = _problem_of_grade(conn, 9)
    assert students.skills(conn, an)[0]["trend"] == "cần ôn"  # missed in both saved sessions
    commit(conn, start(conn, an, "2026-10-21"), [(p9, [])])  # right this time
    [s] = students.skills(conn, an)
    # the arrow follows the newest session only: all three summed would still be a fall
    assert (s["kc_id"], s["trend"], s["last_seen"], s["n_attempts"]) == (kc, "tiến bộ", "2026-10-21", 3)
    total = sql(
        conn, "SELECT sum(theta_after - theta_before) FROM skill_event WHERE student_id = ? AND kc_id = ?", an, kc
    )
    assert elo.trend(total[0][0]) == "cần ôn"


def test_trend_sums_the_session(conn):
    w = world(conn)
    an, kc = w["an"], w["kc_swap"]
    p9, _ = _problem_of_grade(conn, 9)
    commit(conn, start(conn, an, "2026-10-21"), [(p9, [mk(SWAP, kc)]), (p9, [])])  # a fall, then a smaller rise
    last = sql(conn, "SELECT theta_after - theta_before FROM skill_event WHERE kc_id = ? ORDER BY id DESC", kc)[0][0]
    assert elo.trend(last) == "tiến bộ"
    assert students.skills(conn, an)[0]["trend"] == "cần ôn"  # the two attempts together are a fall


def test_progress_matches_derive(conn):
    w = world(conn)
    binh, new = w["binh"], w["kc_swap"]
    p9, _ = _problem_of_grade(conn, 9)
    commit(conn, start(conn, binh, "2026-10-21"), [(p9, [])])  # a skill Bình had not met on 14/10
    out = students.progress(conn, binh)
    assert out["dates"] == ["2026-10-14", "2026-10-21"]
    ev = sql(
        conn,
        "SELECT s.held_on, e.kc_id, e.theta_after FROM skill_event e JOIN attempt a ON a.id = e.attempt_id"
        " JOIN session s ON s.id = a.session_id WHERE e.student_id = ? ORDER BY s.held_on, e.id",
        binh,
    )
    theta, want_all, want = {}, [], {}
    for day in out["dates"]:
        theta |= {k: t for d, k, t in ev if d == day}
        mean = sum(theta.values()) / len(theta)
        want_all.append({"level": elo.level(mean), "pos": pos(mean)})
        for k, t in theta.items():
            want.setdefault(k, [None] * (len(want_all) - 1)).append({"level": elo.level(t), "pos": pos(t)})
    assert out["all"] == want_all and out["skills"] == want
    assert len(out["all"]) == 2 and set(out["skills"]) == set(theta) and len(theta) == 3
    assert out["skills"][new][0] is None and out["skills"][new][1] is not None
    final = dict(sql(conn, "SELECT kc_id, theta FROM skill_state WHERE student_id = ?", binh))
    assert theta == final  # the last point of every line is the level the profile shows


def test_progress_counts_saved_sessions_only(conn):
    w = world(conn)
    sid = sql(conn, "SELECT id FROM session WHERE student_id = ?", w["binh"])[0][0]
    conn.execute("UPDATE session SET status = 'running' WHERE id = ?", (sid,))  # sent back to review
    assert students.progress(conn, w["binh"]) == EMPTY


def test_empty_student(conn):
    world(conn)
    new = repo.add_student(conn, name="Phạm Thu Trang", grade=9)
    assert students.skills(conn, new) == [] and students.recurring(conn, new) == []
    assert students.progress(conn, new) == EMPTY
    assert students.session_rows(conn, student_id=new, status="committed") == []
    since = sql(conn, "SELECT substr(created_at, 1, 10) FROM student WHERE id = ?", new)[0][0]
    assert students.overview(conn)[new] == {
        "since": since, "last_session": None, "level_counts": [{"level": lv, "n": 0} for lv in LEVELS]
    }  # fmt: skip


def test_recurring_words_and_order(conn):
    w = world(conn)
    an, kc = w["an"], w["kc_swap"]
    name = sql(conn, "SELECT name FROM kc WHERE id = ?", kc)[0][0]
    [open_] = students.recurring(conn, an)
    assert open_ == {
        "kind": SWAP_WORDS, "kc_id": kc, "kc": name, "count": 2,
        "first_seen": "2026-10-07", "last_seen": "2026-10-14", "resolved_at": None,
    }  # fmt: skip
    conn.execute(  # fixed ones stay in the list, with the day they were fixed
        "INSERT INTO misconception_log (student_id, code, kc_id, first_seen, last_seen, count, resolved_at)"
        " VALUES (?, ?, ?, '2026-09-01', '2026-09-08', 1, '2026-09-22')",
        (an, CALC, kc),
    )
    got = students.recurring(conn, an)
    assert [(r["count"], r["resolved_at"]) for r in got] == [(2, None), (1, "2026-09-22")]
    assert all("code" not in r for r in got)


def test_overview_and_session_rows(conn):
    w = world(conn)
    an, binh, cuong = w["an"], w["binh"], w["cuong"]
    start(conn, an, "2026-10-28")  # waiting for review: not a saved session
    saved = "SELECT id FROM session WHERE student_id = ? AND status = 'committed' ORDER BY held_on DESC"
    s14, s07 = (r[0] for r in sql(conn, saved, an))
    ov = students.overview(conn)
    assert set(ov) == {an, binh, cuong}  # archived students too
    assert ov[an]["last_session"] == {"session_id": s14, "held_on": "2026-10-14", "score": 1.0, "max_score": 2.0}
    assert ov[an]["level_counts"] == [{"level": lv, "n": int(lv == "đang hình thành")} for lv in LEVELS]
    assert ov[binh]["level_counts"] == [{"level": lv, "n": int(lv == "đang hình thành") * 2} for lv in LEVELS]
    assert ov[cuong]["last_session"] is None
    one = {"student_id": an, "n_attempts": 1, "score": 1.0, "max_score": 2.0, "n_mistakes": 1}
    assert students.session_rows(conn, student_id=an, status="committed") == [
        {"id": s14, "held_on": "2026-10-14"} | one,
        {"id": s07, "held_on": "2026-10-07"} | one,
    ]
    assert [r["held_on"] for r in students.session_rows(conn, student_id=an, status=None)][0] == "2026-10-28"
    assert [r["held_on"] for r in students.session_rows(conn, status="committed", month="2026-10")] == [
        "2026-10-14", "2026-10-14", "2026-10-07"
    ]  # fmt: skip
    assert students.session_rows(conn, student_id=an, month="2026-09") == []


def test_session_view_words(conn):
    w = world(conn)
    an, kc = w["an"], w["kc_swap"]
    p9, _ = _problem_of_grade(conn, 9)
    rejected = mk(CALC, kc, status="rejected")
    general = mk("presentation.logic_gap", None) | {"step_idx": 1}  # no skill: shown without one
    commit(conn, start(conn, an, "2026-10-21"), [(p9, [mk(SWAP, kc), rejected, general])])
    sid = sql(conn, "SELECT id FROM session WHERE student_id = ? AND held_on = '2026-10-21'", an)[0][0]
    conn.execute(
        "UPDATE attempt SET steps_json = ? WHERE session_id = ?", ('[{"idx": 1, "latex": "x = 1", "pos": 0}]', sid)
    )
    out = students.session_view(conn, sid)
    assert (out["id"], out["student_id"], out["held_on"], out["score"], out["max_score"]) == (
        sid,
        an,
        "2026-10-21",
        1.0,
        2.0,
    )
    assert out["n_mistakes"] == 2 and len(out["attempts"]) == 1  # the rejected row is not counted
    [a] = out["attempts"]
    ref, statement = sql(conn, "SELECT ref, statement_latex FROM problem WHERE id = ?", p9)[0]
    assert (a["seq"], a["ref"], a["statement_latex"], a["score"], a["max_score"]) == (1, ref, statement, 1.0, 2.0)
    assert a["steps"] == [{"idx": 1, "latex": "x = 1"}]
    swap, gap = a["mistakes"]
    assert (
        sql(
            conn, "SELECT count(*) FROM mistake WHERE attempt_id IN (SELECT id FROM attempt WHERE session_id = ?)", sid
        )[0][0]
        == 3
    )
    assert swap["kind"] == SWAP_WORDS and swap["code"] == SWAP and swap["status"] == "confirmed"
    assert swap["kc"] == {"id": kc, "name": sql(conn, "SELECT name FROM kc WHERE id = ?", kc)[0][0]}
    assert (swap["description"], swap["evidence_latex"], swap["teacher_note"]) == ("d", "e", None)
    assert gap["kc"] is None and gap["step_idx"] == 1
    shown = json.dumps(
        [{k: v for k, v in m.items() if k != "code"} for m in a["mistakes"]], ensure_ascii=False
    )  # the code is only sent back, never shown
    assert not CODE.search(shown)
    assert students.session_rows(conn, student_id=an, month="2026-10")[0]["n_mistakes"] == 2  # same count in the list
    assert students.session_view(conn, 999) is None
