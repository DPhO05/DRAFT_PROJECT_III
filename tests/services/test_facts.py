"""P7-T02: report facts by period (C-44), checked against hand-written SQL on the assistant world."""

import json
import re
from datetime import date

import pytest

from tests.assistant_fix import SWAP, _problem_of_grade, world
from tests.db.test_profile_repo import commit, start
from tutor.db import repo
from tutor.services import elo, facts
from tutor.services.audit import check_sentence

LATER = date(2026, 11, 3)


def kinds(out, kind):
    return [f for f in out["facts"] if f["kind"] == kind]


def value(out, kind):
    return kinds(out, kind)[0]["value"]


def words(conn, w) -> tuple[str, str]:
    """(error words of SWAP, name of An's skill)."""
    return (
        conn.execute("SELECT description FROM error_code WHERE code = ?", (SWAP,)).fetchone()[0],
        conn.execute("SELECT name FROM kc WHERE id = ?", (w["kc_swap"],)).fetchone()[0],
    )


def test_week_of_sunday():
    assert facts.week_of(date(2026, 11, 1)) == date(2026, 10, 26)


def test_period_rules():
    today = LATER
    with pytest.raises(ValueError, match="thứ Hai"):
        facts.period("week", "2026-10-20", today)
    with pytest.raises(ValueError, match="ngày 1"):
        facts.period("month", "2026-10-02", today)
    with pytest.raises(ValueError):
        facts.period("year", "2026-10-01", today)
    with pytest.raises(ValueError, match="tương lai"):
        facts.period("day", "2026-11-04", today)
    for bad in ("20261012", "2026-13-01", "2026-10-1", "2026-W43-1", ""):
        with pytest.raises(ValueError, match="yyyy-mm-dd"):
            facts.period("day", bad, today)
    assert facts.period("month", "2026-02-01", today)[1] == date(2026, 2, 28)
    assert facts.period("week", "2026-10-26", today) == (date(2026, 10, 26), date(2026, 11, 1))
    assert facts.period("day", "2026-11-03", today) == (LATER, LATER)


def test_period_edges(conn):
    w = world(conn)
    an = w["an"]
    p9, _ = _problem_of_grade(conn, 9)
    for held_on in ("2026-10-31", "2026-11-01", "2026-11-01"):
        commit(conn, start(conn, an, held_on), [(p9, [])])
    repo.commit_session_status(conn, start(conn, an, "2026-11-01"), "awaiting_review")
    run = lambda kind, start_: facts.report_facts(conn, an, kind, start_, today=LATER, low_pass_rate=0.5)  # noqa: E731
    week = run("week", "2026-10-26")
    assert value(week, "sessions") == 3
    kind, kc = words(conn, w)
    assert [f["value"] for f in kinds(week, "resolved")] == [{"kind": kind, "kc": kc}]  # resolved on 01/11
    with pytest.raises(facts.NotReady):
        run("week", "2026-11-02")
    month = run("month", "2026-10-01")
    assert value(month, "sessions") == 3 and kinds(month, "resolved") == []
    assert value(run("month", "2026-11-01"), "previous")["sessions"] == 3  # October
    day = run("day", "2026-11-01")
    assert value(day, "sessions") == 2
    assert value(day, "previous")["sessions"] == 1  # 31/10
    assert len(kinds(day, "session")) == 2  # one fact per committed session, also for a day


def test_session_fact_details(conn):
    w = world(conn)
    err, kc = words(conn, w)
    out = facts.report_facts(conn, w["an"], "month", "2026-10-01", today=LATER, low_pass_rate=0.5)
    s = kinds(out, "session")[0]
    assert s["value"]["problems"] == 1 and s["value"]["kcs"] == [kc]
    assert s["value"]["mistake_kinds"] == [{"kind": facts.short_error(err), "n": 1}]
    assert s["text"] == (
        f"Buổi 07/10: làm 1 bài, đạt 1 trong 2 ý, điểm 5 trên 10, 1 lỗi. "
        f"Đã luyện: “{kc}”. Lỗi: “{facts.short_error(err)}” 1 lần."
    )


def test_session_line_without_mistakes(conn):
    w = world(conn)
    conn.execute("UPDATE mistake SET status = 'rejected'")
    out = facts.report_facts(conn, w["an"], "month", "2026-10-01", today=LATER, low_pass_rate=0.5)
    s = kinds(out, "session")[0]
    assert s["value"]["mistake_kinds"] == [] and "Lỗi:" not in s["text"]


def test_short_error():
    assert facts.short_error("Nhầm phép toán hoặc dấu (+/−, ⇒/⇔)") == "nhầm phép toán hoặc dấu"


def test_same_facts_twice(conn):
    w = world(conn)
    args = (conn, w["an"], "month", "2026-10-01")
    assert facts.report_facts(*args, today=w["today"], low_pass_rate=0.5) == facts.report_facts(
        *args, today=w["today"], low_pass_rate=0.5
    )


def test_month_values(conn):
    w = world(conn)
    an = w["an"]
    first = "SELECT min(id) FROM skill_event WHERE student_id = ?"
    conn.execute(f"UPDATE skill_event SET theta_before = 0.6 WHERE id = ({first})", (an,))
    out = facts.report_facts(conn, an, "month", "2026-10-01", today=w["today"], low_pass_rate=0.5)
    one = lambda sql: conn.execute(sql, (an,)).fetchone()[0]  # noqa: E731
    assert (out["code"], out["period_kind"], out["period_start"], out["period_end"]) == (
        "HS-01",
        "month",
        "2026-10-01",
        "2026-10-31",
    )
    assert value(out, "sessions") == 2
    assert value(out, "problems") == one(
        "SELECT count(*) FROM attempt_current a JOIN session s ON s.id = a.session_id WHERE s.student_id = ?"
    )
    assert value(out, "mistake_kind")["n"] == one(
        "SELECT count(*) FROM mistake_current m JOIN attempt_current a ON a.id = m.attempt_id"
        " JOIN session s ON s.id = a.session_id WHERE s.student_id = ?"
    )
    assert len(kinds(out, "session")) == 2
    theta = dict(
        conn.execute(
            "SELECT k.name, t.theta FROM skill_state t JOIN kc k ON k.id = t.kc_id WHERE t.student_id = ?", (an,)
        )
    )
    skills = kinds(out, "skill")
    assert skills and {f["value"]["kc"] for f in skills} == set(theta)
    for f in skills:
        assert f["value"]["after"] == elo.level(theta[f["value"]["kc"]])
    assert skills[0]["value"]["before"] == "vững"  # first event of the period, not the last
    kind, kc = words(conn, w)
    assert out["insights"] == [
        {"text": f"Thay đổi rõ nhất ở “{kc}” (cần ôn).", "facts": ["F06"]},
        {"text": f"Lỗi gặp nhiều nhất: “{kind}”.", "facts": ["F07"]},
    ]
    assert value(out, "repeat")["count"] == 2
    assert [f["fact_id"] for f in out["facts"]] == [f"F{i:02d}" for i in range(1, len(out["facts"]) + 1)]
    assert kinds(out, "previous") == []
    assert out["low"] is False


def test_weak_skill_lists_prereqs(conn):
    w = world(conn)
    kc = w["kc_swap"]
    pre = conn.execute("SELECT id, name FROM kc WHERE id <> ? ORDER BY id", (kc,)).fetchone()
    conn.execute("UPDATE skill_event SET theta_after = -1 WHERE kc_id = ?", (kc,))
    conn.execute("INSERT INTO kc_prereq (kc_id, prereq_id) VALUES (?, ?)", (kc, pre[0]))
    out = facts.report_facts(conn, w["an"], "month", "2026-10-01", today=w["today"], low_pass_rate=0.5)
    weak = [f["value"] for f in kinds(out, "skill") if f["value"]["after"] == "chưa vững"]
    assert weak and weak[0]["prereqs"] == [pre[1]]
    assert all("prereqs" not in f["value"] for f in kinds(out, "skill") if f["value"]["after"] != "chưa vững")


def test_previous_and_insights(conn):
    w = world(conn)
    out = facts.report_facts(conn, w["an"], "week", "2026-10-12", today=w["today"], low_pass_rate=0.5)
    prev = kinds(out, "previous")
    assert len(prev) == 1 and prev[0]["value"]["sessions"] == 1 and "05/10–11/10" in prev[0]["text"]  # holds 07/10
    ids = {f["fact_id"] for f in out["facts"]}
    assert 1 <= len(out["insights"]) <= 3
    assert all(i["facts"] and set(i["facts"]) <= ids for i in out["insights"])
    _, kc = words(conn, w)
    trend = {"text": "Kết quả giữ như kỳ trước.", "facts": [kinds(out, "score")[0]["fact_id"], prev[0]["fact_id"]]}
    skill = {"text": f"Thay đổi rõ nhất ở “{kc}” (cần ôn).", "facts": [kinds(out, "skill")[0]["fact_id"]]}
    assert out["insights"] == [trend, skill]  # no majority: the mistake is seen once this week
    assert out["low"] is False  # 1 of 2 points, not below 0.5
    assert facts.report_facts(conn, w["an"], "week", "2026-10-12", today=w["today"], low_pass_rate=0.6)["low"]
    last = "SELECT max(a.id) FROM attempt a JOIN session s ON s.id = a.session_id WHERE s.student_id = ?"
    conn.execute(f"UPDATE skill_event SET theta_after = theta_before + 0.01 WHERE attempt_id = ({last})", (w["an"],))
    out = facts.report_facts(conn, w["an"], "week", "2026-10-12", today=w["today"], low_pass_rate=0.5)
    assert value(out, "skill")["trend"] == "giữ" and out["insights"] == [trend]


@pytest.mark.parametrize(("score", "word"), [(1.1, "tốt hơn"), (1.0, "giữ như"), (0.9, "kém hơn")])
def test_trend_word(conn, score, word):
    """R11: pass rate 0.5 last week; ±0.05 is the edge."""
    w = world(conn)
    conn.execute("UPDATE attempt SET score = ? WHERE session_id = (SELECT max(id) FROM session WHERE student_id = ?)",
                 (score, w["an"]))  # fmt: skip
    out = facts.report_facts(conn, w["an"], "week", "2026-10-12", today=w["today"], low_pass_rate=0.5)
    assert out["insights"][0]["text"] == f"Kết quả {word} kỳ trước."


def test_previous_is_the_adjacent_week(conn):
    """H2: a week compares with the week just before only; a day with the last day that has a session."""
    w = world(conn)
    an = w["an"]
    p9, _ = _problem_of_grade(conn, 9)
    run = lambda kind, start_: facts.report_facts(conn, an, kind, start_, today=LATER, low_pass_rate=0.5)  # noqa: E731
    with pytest.raises(facts.NotReady) as e:
        run("week", "2026-10-26")
    assert e.value.detail["previous_start"] == "2026-10-12"  # skips the empty week of 19/10
    commit(conn, start(conn, an, "2026-10-28"), [(p9, [])])
    out = run("week", "2026-10-26")
    assert kinds(out, "previous") == []
    assert not any("kỳ trước" in i["text"] for i in out["insights"])
    assert "07/10" in kinds(run("day", "2026-10-14"), "previous")[0]["text"]


def test_dates(conn):
    """H5: period bounds, the period's session days, and the previous span only when there is a `previous` fact."""
    w = world(conn)
    run = lambda kind, start_: facts.report_facts(conn, w["an"], kind, start_, today=w["today"], low_pass_rate=0.5)  # noqa: E731
    assert run("week", "2026-10-12")["dates"] == ["2026-10-05", "2026-10-11", "2026-10-12", "2026-10-14", "2026-10-18"]
    assert run("month", "2026-10-01")["dates"] == ["2026-10-01", "2026-10-07", "2026-10-14", "2026-10-31"]
    assert run("day", "2026-10-14")["dates"] == ["2026-10-07", "2026-10-14"]


def test_not_ready(conn):
    w = world(conn)
    with pytest.raises(facts.NotReady) as e:
        facts.report_facts(conn, w["an"], "week", "2026-10-19", today=w["today"], low_pass_rate=0.5)
    assert e.value.detail == {"reason": "no_committed_session", "previous_start": "2026-10-12"}
    with pytest.raises(facts.NotReady) as e:
        facts.report_facts(conn, w["an"], "week", "2026-09-28", today=w["today"], low_pass_rate=0.5)
    assert e.value.detail["previous_start"] is None


def test_no_tech_text(conn):
    w = world(conn)
    out = facts.report_facts(conn, w["an"], "month", "2026-10-01", today=w["today"], low_pass_rate=0.5)
    text = json.dumps(out, ensure_ascii=False)  # ensure_ascii would hide θ and names as \u escapes
    assert not re.search(r"θ|%|\"(theta|delta)|(computational|conceptual|notational|presentation|other)\.", text)
    assert not re.search("Nguyễn Văn An|Trần Thị Bình|Lê Văn Cường", text)


NO_NEW = "Chưa tìm được kỹ năng nào cần ôn hay học tiếp có bài trong ngân hàng."
BANKED = "EXISTS (SELECT 1 FROM problem_kc pk JOIN rubric r ON r.problem_id = pk.problem_id WHERE pk.kc_id = kc.id)"


def set_theta(conn, sid, kc, theta):
    conn.execute(
        "INSERT INTO skill_state (student_id, kc_id, theta, last_seen, updated_at)"
        " VALUES (?, ?, ?, '2026-10-01', '2026-10-01')",
        (sid, kc, theta),
    )


def plan_items(conn, sid, after=LATER):
    return [i for f in facts.plan(conn, sid, after, first_id=1)["facts"] for i in f["value"]["items"]]


def test_plan_weeks_and_title(conn):
    w = world(conn)
    p = facts.plan(conn, w["an"], date(2026, 11, 15), first_id=9)
    assert p["title"] == "Lộ trình 4 tuần tới (16/11–13/12)"
    assert p["facts"][0]["fact_id"] == "F09" and p["facts"][0]["kind"] == "plan"
    assert p["facts"][0]["text"].startswith("Tuần 16/11–22/11: ")
    assert {"2026-11-16", "2026-11-22"} <= set(p["dates"])
    assert [f["fact_id"] for f in p["facts"]] == [f"F{i:02d}" for i in range(9, 9 + len(p["facts"]))]
    assert (p["facts"][1]["value"]["from"], p["facts"][1]["value"]["to"]) == ("2026-11-23", "2026-11-29")


def test_plan_repeat_first_with_prereqs(conn):
    w = world(conn)
    an, kc_id = w["an"], w["kc_swap"]
    err, kc = words(conn, w)
    a, b, c = [
        r[0] for r in conn.execute("SELECT id FROM kc WHERE lop = 8 AND parent_id IS NOT NULL ORDER BY id LIMIT 3")
    ]
    for pre in (c, a, b):
        conn.execute("INSERT INTO kc_prereq (kc_id, prereq_id) VALUES (?, ?)", (kc_id, pre))
    set_theta(conn, an, b, 1.0)  # vững: not a prereq to review
    set_theta(conn, an, c, -1.0)  # chưa vững; a has no state, which counts as 0
    expect = [  # hand-written: unmastered direct prereqs of the repeat skill, by prereq id
        n
        for (n,) in conn.execute(
            "SELECT k.name FROM kc_prereq p JOIN kc k ON k.id = p.prereq_id"
            " LEFT JOIN skill_state t ON t.student_id = ? AND t.kc_id = p.prereq_id"
            " WHERE p.kc_id = ? AND COALESCE(t.theta, 0) <= 0.5 ORDER BY p.prereq_id",
            (an, kc_id),
        )
    ]
    assert len(expect) == 2
    items = plan_items(conn, an)
    rep = next(k for k, i in enumerate(items) if i["why"] == "repeat")
    assert items[rep] == {"kc": kc, "why": "repeat", "error": facts.short_error(err), "n": 2}
    assert items[:rep] == [{"kc": n, "why": "prereq", "for": kc} for n in expect]
    assert len({i["kc"] for i in items}) == len(items)  # c is weak too, but it is listed once


def test_plan_two_per_week_max_eight(conn):
    world(conn)
    sid = repo.add_student(conn, name="Em Mới", grade=None)
    for (kc,) in conn.execute(f"SELECT id FROM kc WHERE {BANKED} ORDER BY id LIMIT 10").fetchall():
        set_theta(conn, sid, kc, -1.0)
    p = facts.plan(conn, sid, LATER, first_id=1)
    assert [len(f["value"]["items"]) for f in p["facts"]] == [2, 2, 2, 2]


def test_plan_order_and_text(conn):
    w = world(conn)
    an = w["an"]
    err, kc = words(conn, w)
    conn.execute("DELETE FROM kc_prereq")
    weak, forming = [
        r[0] for r in conn.execute("SELECT id FROM kc WHERE lop = 8 AND parent_id IS NOT NULL ORDER BY id LIMIT 2")
    ]
    set_theta(conn, an, forming, 0.2)
    set_theta(conn, an, weak, -1.0)
    name = lambda k: conn.execute("SELECT name FROM kc WHERE id = ?", (k,)).fetchone()[0]  # noqa: E731
    new = conn.execute(
        "SELECT name FROM kc WHERE lop = 9 AND parent_id IS NOT NULL AND id NOT IN (SELECT kc_id FROM skill_state"
        f" WHERE student_id = ?) AND {BANKED} ORDER BY id LIMIT 5",
        (an,),
    ).fetchall()
    p = facts.plan(conn, an, date(2026, 11, 15), first_id=1)
    assert [f["text"] for f in p["facts"]] == [
        f"Tuần 16/11–22/11: sửa lỗi “{facts.short_error(err)}” ở “{kc}” (đã gặp 2 lần);"
        f" củng cố “{name(weak)}” (đang chưa vững).",
        f"Tuần 23/11–29/11: luyện thêm “{name(forming)}” (đang hình thành); học tiếp “{new[0][0]}”.",
        f"Tuần 30/11–06/12: học tiếp “{new[1][0]}”; học tiếp “{new[2][0]}”.",
        f"Tuần 07/12–13/12: học tiếp “{new[3][0]}”; học tiếp “{new[4][0]}”.",
    ]


def test_plan_new_skills_need_grade(conn):
    world(conn)
    sid = repo.add_student(conn, name="Em Mới", grade=None)
    assert plan_items(conn, sid) == []  # no grade, no state: nothing to plan
    conn.execute("UPDATE student SET grade = 8 WHERE id = ?", (sid,))
    conn.execute("DELETE FROM kc_prereq")
    held = conn.execute("SELECT id FROM kc WHERE lop = 8 AND parent_id IS NOT NULL ORDER BY id").fetchone()[0]
    weak = conn.execute("SELECT id FROM kc WHERE lop = 9 AND parent_id IS NOT NULL ORDER BY id").fetchone()[0]
    conn.execute("INSERT INTO kc_prereq (kc_id, prereq_id) VALUES (?, ?)", (held, weak))  # needs a weak prereq
    set_theta(conn, sid, weak, -1.0)
    expect = [  # hand-written: grade 8, a child skill, no state, every direct prereq at theta >= 0 (missing = 0)
        n
        for (n,) in conn.execute(
            "SELECT name FROM kc WHERE lop = 8 AND parent_id IS NOT NULL AND id <> ? ORDER BY id", (held,)
        )
    ]
    items = plan_items(conn, sid)
    assert [i["why"] for i in items] == ["weak"] + ["new"] * 7
    assert [i["kc"] for i in items[1:]] == expect[:7]
    conn.execute("UPDATE student SET grade = NULL WHERE id = ?", (sid,))
    assert [i["why"] for i in plan_items(conn, sid)] == ["weak"]


def test_plan_fallback_line(conn):
    w = world(conn)
    sid = repo.add_student(conn, name="Em Mới", grade=None)
    for (kc,) in conn.execute("SELECT id FROM kc").fetchall():
        set_theta(conn, sid, kc, 1.0)
    p = facts.plan(conn, sid, LATER, first_id=1)
    assert [f["text"] for f in p["facts"]] == [NO_NEW]
    assert p["facts"][0]["value"] == {"items": []} and p["facts"][0]["kind"] == "plan"
    assert p["dates"] == []
    conn.execute("DELETE FROM problem_kc")  # An has a repeat and a grade, but no skill has a graded problem
    p = facts.plan(conn, w["an"], LATER, first_id=3)
    assert [(f["fact_id"], f["text"]) for f in p["facts"]] == [("F03", NO_NEW)]


def test_plan_lines_pass_audit(conn):
    w = world(conn)
    p = facts.plan(conn, w["an"], LATER, first_id=1)
    days = [date.fromisoformat(d) for d in p["dates"]]
    assert all(check_sentence(f["text"], [f], low=False, need_fact=True, dates=days) is None for f in p["facts"])


def test_plan_dates_cross_year(conn):
    w = world(conn)
    p = facts.plan(conn, w["an"], date(2026, 12, 20), first_id=1)
    assert p["title"] == "Lộ trình 4 tuần tới (21/12–17/01)"
    assert p["facts"][3]["text"].startswith("Tuần 11/01–17/01: ")
    days = [date.fromisoformat(d) for d in p["dates"]]
    assert all(check_sentence(f["text"], [f], low=False, need_fact=True, dates=days) is None for f in p["facts"])
