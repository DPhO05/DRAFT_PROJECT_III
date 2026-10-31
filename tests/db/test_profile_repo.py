"""P4-T02/T04: profiler inputs, skill_* written inside commit ②, replay == incremental."""

import itertools
import sqlite3

import pytest

from tests.bankfix import P1, P9, add_bank
from tutor.db import repo
from tutor.services import elo

D1, D2, D3 = "2026-11-01", "2026-11-02", "2026-11-03"
WRONG = "computational.final_answer"
GAP = "presentation.logic_gap"
_n = itertools.count()


def mk(code, kc_id, status="confirmed"):
    return {
        "step_idx": 0, "code": code, "kc_id": kc_id, "description": "d", "evidence_latex": "e",
        "confidence": 0.9, "verifier_verdict": None, "verifier_reason": None, "status": status,
        "llm_json": {}, "teacher_note": None, "reviewed_at": None,
    }  # fmt: skip


@pytest.fixture
def bank(conn):
    """P1 -> k1, P9 -> k1 + k2; deltas -0.5 / 0.8."""
    add_bank(conn)
    ids = {r: i for i, r in conn.execute("SELECT id, ref FROM problem")}
    k1 = conn.execute("SELECT id FROM kc").fetchone()[0]
    k2 = repo.add_kc(conn, code="8DS-PT1-02", name="Rút gọn", description="d", lop=8)
    conn.execute(
        "INSERT INTO problem_kc (problem_id, kc_id, approved_at) VALUES (?, ?, ?)", (ids[P9[0]], k2, repo.now())
    )
    conn.execute("UPDATE problem SET delta = -0.5 WHERE id = ?", (ids[P1[0]],))
    conn.execute("UPDATE problem SET delta = 0.8 WHERE id = ?", (ids[P9[0]],))
    return {"k1": k1, "k2": k2, "p1": ids[P1[0]], "p9": ids[P9[0]]}


def start(conn, sid, held_on):
    n = next(_n)
    return repo.commit_session_start(
        conn, student_id=sid, held_on=held_on, source_path=f"inbox/{n}.tex", source_kind="tex",
        sha256=f"sha{n}", thread_id=f"t{n}",
    )  # fmt: skip


def build(conn, session_id, work):
    """work: [(problem_id, [mistake row])] -> (attempt rows, elo.profile over the stored prior)."""
    sid, held_on = conn.execute("SELECT student_id, held_on FROM session WHERE id = ?", (session_id,)).fetchone()
    probs = repo.profile_problems(conn, [p for p, _ in work])
    attempts, rows = [], []
    for seq, (pid, ms) in enumerate(work, 1):
        attempts.append({
            "seq": seq, "delta": probs[pid]["delta"], "kcs": probs[pid]["kcs"],
            "mistakes": [{"code": m["code"], "kc_id": m["kc_id"]} for m in ms if m["status"] != "rejected"],
        })  # fmt: skip
        rows.append({
            "seq": seq, "problem_id": pid, "rubric_id": conn.execute(
                "SELECT id FROM rubric WHERE problem_id = ?", (pid,)).fetchone()[0],
            "rubric": None, "solution_latex": "s", "steps": [], "flags": [], "grade_items": [], "score": 1.0,
            "max_score": 2.0, "mistakes": ms,
        })  # fmt: skip
    return rows, elo.profile(repo.profile_prior(conn, sid), attempts, held_on)


def commit(conn, session_id, work, *, profiled=True):
    """prior -> elo.profile -> commit_session(profile=...). Returns (receipt, profile)."""
    rows, prof = build(conn, session_id, work)
    receipt = repo.commit_session(conn, session_id, transcript="t", review_seconds=1, attempts=rows,
                                  profile=prof if profiled else None)  # fmt: skip
    return receipt, prof


def skill_rows(conn) -> dict:
    """skill_* tables without id / created_at / updated_at, floats to 9 digits, sorted: comparable across replay."""
    drop = {"id", "created_at", "updated_at"}

    def rows(table, order):
        cur = conn.execute(f"SELECT * FROM {table} ORDER BY {order}")
        cols = [c[0] for c in cur.description]
        return [
            {c: round(v, 9) if isinstance(v, float) else v for c, v in zip(cols, r, strict=True) if c not in drop}
            for r in cur
        ]

    return {
        "event": rows("skill_event", "student_id, attempt_id, kc_id"),
        "state": rows("skill_state", "student_id, kc_id"),
        "miscon": rows("misconception_log", "student_id, code, kc_id"),
    }


def three_sessions(conn, sid, b):
    k1, k2, p1, p9 = b["k1"], b["k2"], b["p1"], b["p9"]
    plan = [
        (D1, [(p1, [mk(WRONG, k1)]), (p9, [])]),
        (D2, [(p1, []), (p9, [mk(GAP, None), mk(WRONG, k2, "rejected")])]),  # k1 streak 2 -> resolved
        (D3, [(p9, [mk(WRONG, k1), mk(WRONG, k2)])]),  # k1 reappears after resolve
    ]  # fmt: skip
    for held_on, work in plan:
        commit(conn, start(conn, sid, held_on), work)


def test_incremental_commits_equal_replay(conn, bank):
    s1, s2 = repo.add_student(conn, name="A"), repo.add_student(conn, name="B")
    three_sessions(conn, s1, bank)
    three_sessions(conn, s2, bank)
    before = skill_rows(conn)
    assert before["event"] and before["state"] and before["miscon"]
    assert any(m["resolved_at"] is None and m["count"] == 2 for m in before["miscon"])  # reappeared after resolve
    repo.replay_student(conn, s1)
    repo.replay_student(conn, s2)
    assert skill_rows(conn) == before


def test_replay_deletes_only_that_student(conn, bank):
    s1, s2 = repo.add_student(conn, name="A"), repo.add_student(conn, name="B")
    three_sessions(conn, s1, bank)
    three_sessions(conn, s2, bank)
    conn.execute("DELETE FROM skill_state WHERE student_id = ?", (s1,))
    repo.replay_student(conn, s1)
    assert conn.execute("SELECT count(*) FROM skill_state WHERE student_id = ?", (s1,)).fetchone()[0] == 2
    assert {r[0] for r in conn.execute("SELECT DISTINCT student_id FROM skill_event")} == {s1, s2}


def test_replay_reports_level_changes(conn, bank):
    s = repo.add_student(conn, name="A")
    three_sessions(conn, s, bank)
    good = skill_rows(conn)
    conn.execute("UPDATE skill_state SET theta = 5 WHERE kc_id = ?", (bank["k1"],))
    out = repo.replay_student(conn, s)
    k1_theta = next(r["theta"] for r in good["state"] if r["kc_id"] == bank["k1"])
    assert out["events"] == len(good["event"])
    assert out["level_changes"] == [{"kc_id": bank["k1"], "before": "vững", "after": elo.level(k1_theta)}]
    assert skill_rows(conn) == good


def test_same_day_sessions_replay_in_commit_order(conn, bank, monkeypatch):
    """Same held_on, larger id commits first: replay must follow committed_at, not id."""
    ticks = itertools.count(1)
    monkeypatch.setattr(repo, "now", lambda: f"2026-11-02T10:00:{next(ticks):02d}Z")
    s = repo.add_student(conn, name="A")
    a, b = start(conn, s, D2), start(conn, s, D2)
    commit(conn, b, [(bank["p1"], [mk(WRONG, bank["k1"])])])
    commit(conn, a, [(bank["p1"], []), (bank["p1"], [])])
    before = skill_rows(conn)
    repo.replay_student(conn, s)
    assert skill_rows(conn) == before


def test_null_delta_counts_as_zero(conn, bank):
    ids = [bank["p1"], bank["p9"]]
    conn.execute("UPDATE problem SET delta = NULL")
    probs = repo.profile_problems(conn, ids)
    assert all(p["delta"] == 0 for p in probs.values())
    assert probs[bank["p9"]]["kcs"] == sorted([bank["k1"], bank["k2"]])
    assert repo.profile_problems(conn, []) == {}


def test_commit_failure_writes_no_skill_rows(conn, bank):
    s = repo.add_student(conn, name="A")
    sess = start(conn, s, D1)
    rows, prof = build(conn, sess, [(bank["p1"], [mk(WRONG, bank["k1"])])])
    counts = repo.row_counts(conn)
    good = prof["skills"][0]["kc_id"]
    prof["skills"][0] = prof["skills"][0] | {"kc_id": 999}  # events insert fine, skill_state insert hits the FK
    with pytest.raises(sqlite3.IntegrityError):
        repo.commit_session(conn, sess, transcript="t", review_seconds=1, attempts=rows, profile=prof)
    assert repo.row_counts(conn) == counts
    assert conn.execute("SELECT status FROM session WHERE id = ?", (sess,)).fetchone()[0] == "running"
    prof["skills"][0] = prof["skills"][0] | {"kc_id": good}
    repo.commit_session(conn, sess, transcript="t", review_seconds=1, attempts=rows, profile=prof)
    after = skill_rows(conn)
    repo.replay_student(conn, s)
    assert skill_rows(conn) == after
    assert len(after["event"]) == 1


def test_stale_prior_raises_and_writes_nothing(conn, bank):
    s = repo.add_student(conn, name="A")
    a, b = start(conn, s, D1), start(conn, s, D1)
    work = [(bank["p1"], [mk(WRONG, bank["k1"])])]
    rows_b, prof_b = build(conn, b, work)
    prior_b = repo.profile_prior(conn, s)
    commit(conn, a, work)  # the other session commits between B's preview and B's commit
    counts = repo.row_counts(conn)
    with pytest.raises(repo.StaleProfile):
        repo.commit_session(conn, b, transcript="t", review_seconds=1, attempts=rows_b, profile=prof_b, prior=prior_b)
    assert repo.row_counts(conn) == counts
    assert conn.execute("SELECT status FROM session WHERE id = ?", (b,)).fetchone()[0] == "running"
    rows_b, prof_b = build(conn, b, work)  # recomputed over the new prior
    repo.commit_session(conn, b, transcript="t", review_seconds=1, attempts=rows_b, profile=prof_b,
                        prior=repo.profile_prior(conn, s))  # fmt: skip
    after = skill_rows(conn)
    repo.replay_student(conn, s)
    assert skill_rows(conn) == after and len(after["event"]) == 2


def test_receipt_counts_skill_events(conn, bank):
    s = repo.add_student(conn, name="A")
    receipt, prof = commit(conn, start(conn, s, D1), [(bank["p9"], [mk(WRONG, bank["k1"])])])
    assert receipt["skill_event"] == len(prof["events"]) == 2
    again = repo.commit_session(
        conn, receipt["session_id"], transcript="x", review_seconds=1, attempts=[], profile=prof
    )
    assert again == receipt
    assert conn.execute("SELECT count(*) FROM skill_event").fetchone()[0] == 2
    plain, _ = commit(conn, start(conn, s, D2), [(bank["p1"], [])], profiled=False)
    assert plain["skill_event"] == 0


def test_profile_prior_reads_state_and_latest_session_codes(conn, bank):
    s = repo.add_student(conn, name="A")
    assert repo.profile_prior(conn, s) == elo.empty_prior()
    commit(
        conn,
        start(conn, s, D2),
        [(bank["p9"], [mk(WRONG, bank["k1"]), mk(GAP, None), mk(WRONG, bank["k2"], "rejected")])],
    )
    _, prof = commit(conn, start(conn, s, D3), [(bank["p1"], [mk(GAP, None)]), (bank["p1"], [mk(GAP, None)])])
    prior = repo.profile_prior(conn, s)
    assert prior["prev_codes"] == [GAP]  # latest session only; rejected / earlier codes excluded
    assert prior == prof["after"]
    commit(conn, start(conn, s, "2026-11-04"), [])
    assert repo.profile_prior(conn, s)["prev_codes"] == []  # empty latest session still counts
