"""P7-T02: report facts by period (C-44), checked against hand-written SQL on the assistant world."""

import json
import re
from datetime import date

import pytest

from tests.assistant_fix import SWAP, _problem_of_grade, world
from tests.db.test_profile_repo import commit, start
from tutor.db import repo
from tutor.services import elo, facts

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
    assert kinds(day, "session") == []


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
