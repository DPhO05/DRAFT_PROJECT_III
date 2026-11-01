"""P6-T04: rank_problems — review / zpd / challenge picks for a worksheet."""

import itertools
import re
from datetime import timedelta

import pytest

from tests.assistant_fix import world
from tests.services.test_student_reads import set_theta
from tutor import config
from tutor.db import repo
from tutor.services import select

RECO = config.defaults()["reco"]
RATIOS = RECO["ratios"]
# same pattern as tests/ui/check_v3.py FORBIDDEN (that module needs playwright to import)
FORBIDDEN = re.compile(
    r"θ|δ|\[F\d\d\]|thread|checkpoint|token|computational\.|conceptual\.|notational\.|presentation\.|other\.unclear"
    r"|g[1-5]-hs|\bnode\b|\b\d[A-Z]{2}-[A-Z0-9]+-\d\d\b"
)
MAIN = "(SELECT kc_id FROM problem_kc WHERE problem_id = p.id ORDER BY step_idx, kc_id LIMIT 1)"
KEYS = {"problem_id", "ref", "kc_id", "bucket", "reason", "level", "kcs", "statement_latex"}
_n = itertools.count()


def rank(conn, w, who="an", n=6, **kw):
    return select.rank_problems(conn, w[who], n, reco=RECO, today=w["today"], **kw)


def by_kc(conn, kc):
    """Ids of the bank problems whose main skill is `kc`, by ref."""
    return [r[0] for r in conn.execute(f"SELECT p.id FROM problem p WHERE {MAIN} = ? ORDER BY p.ref", (kc,))]


def only(conn, ids, delta=None):
    """Bank = these problems: every other problem loses its skill tags, so it cannot be picked."""
    marks = ", ".join("?" * len(ids))
    conn.execute(f"DELETE FROM problem_kc WHERE problem_id NOT IN ({marks})", ids)
    if delta is not None:
        conn.execute(f"UPDATE problem SET delta = ? WHERE id IN ({marks})", [delta, *ids])


def did(conn, sid, pid, held_on):
    """A saved session of `sid` held on `held_on` with one attempt on problem `pid`."""
    k = next(_n)
    session = conn.execute(
        "INSERT INTO session (student_id, held_on, source_path, source_kind, source_sha256, thread_id, status)"
        " VALUES (?, ?, 'x', 'tex', ?, ?, 'committed')",
        (sid, held_on.isoformat(), f"sha-{k}", f"t-{k}"),
    ).lastrowid
    rubric = conn.execute("SELECT id FROM rubric WHERE problem_id = ?", (pid,)).fetchone()[0]
    conn.execute(
        "INSERT INTO attempt (session_id, seq, problem_id, rubric_id, solution_latex, steps_json, grade_json,"
        " score, max_score) VALUES (?, 1, ?, ?, 's', '[]', '[]', 1, 2)",
        (session, pid, rubric),
    )


def kc_name(conn, kc):
    return conn.execute("SELECT name FROM kc WHERE id = ?", (kc,)).fetchone()[0]


def test_split():
    assert select.split(6, RATIOS) == {"review": 2, "zpd": 3, "challenge": 1}
    assert select.split(10, RATIOS) == {"review": 4, "zpd": 5, "challenge": 1}
    assert select.split(6, {"review": 0, "zpd": 1, "challenge": 0}) == {"review": 0, "zpd": 6, "challenge": 0}
    assert select.split(3, {"review": 0.5, "zpd": 0.5, "challenge": 0}) == {"review": 2, "zpd": 1, "challenge": 0}


@pytest.mark.parametrize(
    "ratios",
    [
        {"review": 0, "zpd": 0, "challenge": 0},
        {"review": -1, "zpd": 1, "challenge": 0},
        {"review": 2, "zpd": 1, "challenge": 0},
        {"review": 1, "zpd": 1},
        {"review": 1, "zpd": 1, "challenge": 1, "x": 1},
    ],
)
def test_split_rejects_bad_ratios(ratios):
    with pytest.raises(ValueError, match="Tỉ lệ"):
        select.split(6, ratios)


def test_six_is_two_three_one(conn):
    w = world(conn)
    r = rank(conn, w)
    assert r["counts"] == {"review": 2, "zpd": 3, "challenge": 1} and r["warnings"] == []
    assert [i["bucket"] for i in r["items"]] == ["review"] * 2 + ["zpd"] * 3 + ["challenge"]
    ids = [i["problem_id"] for i in r["items"]]
    assert len(set(ids)) == 6 and all(set(i) == KEYS for i in r["items"])
    have = {r[0] for r in conn.execute("SELECT problem_id FROM rubric")}
    assert set(ids) <= have
    assert {i["kc_id"] for i in r["items"] if i["bucket"] == "review"} == {w["kc_swap"]}
    first = r["items"][0]
    assert first["kcs"][0] == kc_name(conn, w["kc_swap"]) and first["statement_latex"]


def test_ratios_override(conn):
    w = world(conn)
    r = rank(conn, w, ratios={"review": 0.5, "zpd": 0.5, "challenge": 0})
    assert r["counts"] == {"review": 3, "zpd": 3, "challenge": 0}


def test_no_repeat_window(conn):
    w = world(conn)
    a, b, c, d = by_kc(conn, 3)[:4]
    only(conn, [a, b, c, d], delta=0)
    for pid, days in ((a, 29), (b, 30), (c, 31)):
        did(conn, w["an"], pid, w["today"] - timedelta(days=days))
    picked = {i["problem_id"] for i in rank(conn, w, n=12)["items"]}
    assert picked == {c, d}


def test_rubric_required(conn):
    w = world(conn)
    a, b = by_kc(conn, 3)[:2]
    bare = conn.execute(
        "INSERT INTO problem (ref, statement_latex, solution_latex, delta) VALUES ('X-1', 's', 'l', 0)"
    ).lastrowid
    conn.execute("INSERT INTO problem_kc (problem_id, kc_id, approved_at) VALUES (?, 3, ?)", (bare, repo.now()))
    only(conn, [a, b, bare], delta=0)
    assert {i["problem_id"] for i in rank(conn, w, n=12)["items"]} == {a, b}


def test_kc_mix(conn):
    w = world(conn)
    r = rank(conn, w)
    assert len({i["kc_id"] for i in r["items"]}) >= 3 and r["warnings"] == []
    pool = by_kc(conn, w["kc_swap"]) + by_kc(conn, 2)
    only(conn, pool, delta=0)
    r = rank(conn, w)
    assert len(r["items"]) == 6 and {i["kc_id"] for i in r["items"]} == {w["kc_swap"], 2}
    assert r["warnings"] == ["Phiếu chỉ có 2 kỹ năng"]


def test_short_bank_warns(conn):
    w = world(conn)
    only(conn, by_kc(conn, 3)[:2], delta=0)
    r = rank(conn, w)
    assert len(r["items"]) == 2 and "Chỉ tìm được 2 bài hợp" in r["warnings"]


def test_new_student(conn):
    w = world(conn)
    w["dung"] = repo.add_student(conn, name="Phạm Thị Dung", grade=9)
    assert conn.execute("SELECT count(*) FROM skill_state WHERE student_id = ?", (w["dung"],)).fetchone()[0] == 0
    r = rank(conn, w, who="dung")
    assert len(r["items"]) == 6 and r["counts"] == {"review": 0, "zpd": 5, "challenge": 1}


def test_challenge_fallback(conn):
    w = world(conn)
    ids = by_kc(conn, 3)
    only(conn, ids, delta=0)
    conn.execute("UPDATE problem SET delta = 0.5 WHERE id = ?", (ids[-1],))
    (ch,) = [i for i in rank(conn, w)["items"] if i["bucket"] == "challenge"]
    assert ch["problem_id"] == ids[-1] and "bài khó nhất còn lại" in ch["reason"]


def test_challenge_needs_prerequisites(conn):
    w = world(conn)
    only(conn, by_kc(conn, 3), delta=1.2)
    conn.execute("INSERT OR IGNORE INTO kc_prereq (kc_id, prereq_id) VALUES (3, 4)")
    set_theta(conn, w["an"], 4, -0.3)
    assert rank(conn, w)["items"] == []
    set_theta(conn, w["an"], 4, 0.2)
    r = rank(conn, w)
    assert r["counts"]["challenge"] >= 1 and "đã vững phần nền" in r["items"][0]["reason"]


def test_reason_words(conn):
    w = world(conn)
    name = kc_name(conn, w["kc_swap"])
    r = rank(conn, w)
    by = {b: [i["reason"] for i in r["items"] if i["bucket"] == b] for b in ("review", "zpd", "challenge")}
    assert set(by["review"]) == {f"Ôn lại “{name}”: còn nhầm phép toán hoặc dấu (2 lần)."}
    assert all(re.fullmatch(r"Vừa sức: luyện “.+” \((chưa vững|đang hình thành|vững)\)\.", s) for s in by["zpd"])
    assert re.fullmatch(r"Thử thách: “.+” — đã vững phần nền\.", by["challenge"][0])
    conn.execute(
        "INSERT INTO misconception_log (student_id, code, kc_id, first_seen, last_seen, count)"
        " VALUES (?, 'computational.intermediate_calc', ?, '2026-10-14', '2026-10-14', 1)",
        (w["an"], w["kc_swap"]),
    )
    again = rank(conn, w)
    assert again["items"][0]["reason"] == f"Ôn lại “{name}”: còn nhầm phép toán hoặc dấu (2 lần), cả kỹ năng 3 lần."
    assert not [i["reason"] for i in r["items"] + again["items"] if FORBIDDEN.search(i["reason"])]
