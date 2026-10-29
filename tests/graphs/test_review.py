"""P3-T01 / P3-T02: review decisions at gate_review → commit ② (contract §7 mapping, one transaction)."""

import json
import sqlite3
from contextlib import closing

import pytest

from tests.graphs.g1 import THREE, status
from tutor.db import repo
from tutor.graphs import runner as rmod


def kc_id(conn):
    return conn.execute("SELECT id FROM kc WHERE code = '8DS-PT1-01'").fetchone()[0]


def mistakes(conn):
    cur = conn.execute("SELECT m.*, a.seq FROM mistake m JOIN attempt a ON a.id = m.attempt_id ORDER BY m.id")
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def full(conn):
    return {"cards": {
        "p1": {"action": "accept"},
        "p2": {"action": "edit", "code": "computational.final_answer", "kc_id": kc_id(conn), "description": "sửa lại",
               "teacher_note": "đúng hơn"},
        "p3": {"action": "reject", "teacher_note": "không phải lỗi"},
        "n1": {"action": "add", "attempt_seq": 1, "step_idx": 2, "code": "notational.symbol", "description": "sót"},
    }, "review_seconds": 95}  # fmt: skip


def test_decisions_map_to_mistake_rows_and_commit(env):
    go, conn, r = env
    out, row, _ = go(THREE)
    tid = out["thread_id"]
    props = {p["pid"]: p for p in r.state(tid)["proposals"]}
    assert r.save_decisions(tid, full(conn)) == 0
    before = repo.row_counts(conn)
    r.resume(tid)
    row = r.wait(tid)
    assert (row["status"], row["error"]) == ("committed", None)
    assert status(conn, out["session_id"]) == "committed"
    ms = {(m["seq"], m["status"]): m for m in mistakes(conn)}
    assert sorted(ms) == [(1, "added"), (1, "confirmed"), (2, "edited"), (3, "rejected")]
    p1, ok = props["p1"], ms[(1, "confirmed")]
    assert (ok["code"], ok["description"], ok["confidence"]) == (p1["code"], p1["description"], p1["confidence"])
    assert (ok["verifier_verdict"], ok["verifier_reason"]) == ("agree", "đúng")
    assert json.loads(ok["llm_json"]) == {k: v for k, v in p1.items() if k != "verifier"}
    ed = ms[(2, "edited")]
    assert (ed["code"], ed["kc_id"], ed["description"], ed["teacher_note"]) == (
        "computational.final_answer", kc_id(conn), "sửa lại", "đúng hơn")  # fmt: skip
    assert ed["step_idx"] == props["p2"]["step_idx"] and json.loads(ed["llm_json"])["code"] == "other.unclear"
    assert ms[(3, "rejected")]["teacher_note"] == "không phải lỗi"
    add = ms[(1, "added")]
    assert add["llm_json"] is None and add["confidence"] is None and add["verifier_verdict"] is None
    assert (add["step_idx"], add["code"], add["evidence_latex"]) == (2, "notational.symbol", "$x = 1$")
    assert all(m["reviewed_at"] for m in ms.values())
    s = conn.execute("SELECT review_seconds, transcript_latex, committed_at FROM session").fetchone()
    assert s[0] == 95 and s[1] == THREE and s[2]
    # receipt = the rows really added (P3-T06)
    after = repo.row_counts(conn)
    receipt = r.state(tid)["receipt"]
    assert {k: after[k] - before[k] for k in after if after[k] != before[k]} == {"attempt": 3, "mistake": 4}
    assert (receipt["attempt"], receipt["mistake"], receipt["rubric"]) == (3, 4, 0)
    assert receipt["by_status"] == {"confirmed": 1, "edited": 1, "rejected": 1, "added": 1}
    att = conn.execute("SELECT seq, score, max_score, grade_json, steps_json FROM attempt ORDER BY seq").fetchall()
    assert [a[0] for a in att] == [1, 2, 3] and att[0][1] == att[0][2] == 1
    assert json.loads(att[0][3])[0]["item_id"] == "r1" and json.loads(att[0][4])[0]["idx"] == 1


def test_backup_is_taken_before_commit(env):
    go, conn, r = env
    out, _, _ = go(THREE)
    before = repo.row_counts(conn)
    r.save_decisions(out["thread_id"], full(conn))
    r.resume(out["thread_id"])
    assert r.wait(out["thread_id"])["status"] == "committed"
    name = r.state(out["thread_id"])["receipt"]["backup"]
    with closing(sqlite3.connect(r._paths_for_test.backup / name)) as b:
        assert repo.row_counts(b) == before


def test_pause_keeps_decisions_and_undecided_blocks_commit(env):
    go, conn, r = env
    out, _, _ = go(THREE)
    tid = out["thread_id"]
    part = {"cards": {"p1": {"action": "accept"}}, "review_seconds": 30}
    assert r.save_decisions(tid, part) == 2
    assert json.loads(r.get(tid)["decisions_json"]) == part  # reopen later: same answers
    before = repo.row_counts(conn)
    with pytest.raises(rmod.UndecidedItems) as e:
        r.resume(tid)
    assert e.value.n == 2 and repo.row_counts(conn) == before


@pytest.mark.parametrize(
    "card",
    [
        {"action": "edit", "code": "no.such"},
        {"action": "edit", "kc_id": 999},
        {"action": "edit", "step_idx": 9},
        {"action": "edit", "description": " "},
        {"action": "add"},
        {"action": "maybe"},
        "accept",
    ],
)
def test_invalid_card_counts_as_undecided(env, card):
    go, conn, r = env
    out, _, _ = go(THREE)
    d = full(conn)
    d["cards"]["p2"] = card
    assert r.save_decisions(out["thread_id"], d) == 1


@pytest.mark.parametrize(
    "add",
    [
        {"action": "add", "attempt_seq": 7, "step_idx": 1, "code": "other.unclear", "description": "x"},
        {"action": "add", "attempt_seq": 1, "step_idx": 1, "code": "other.unclear", "description": ""},
        {"action": "accept"},
    ],
)
def test_invalid_added_mistake_counts_as_undecided(env, add):
    go, conn, r = env
    out, _, _ = go(THREE)
    d = full(conn)
    d["cards"]["n1"] = add
    assert r.save_decisions(out["thread_id"], d) == 1


def test_inactive_code_cannot_be_chosen_in_edit(env):
    go, conn, r = env
    out, _, _ = go(THREE)
    repo.update_error_code(conn, "computational.final_answer", active=False)
    assert r.save_decisions(out["thread_id"], full(conn)) == 1


def test_failure_inside_commit_writes_nothing_and_rerun_commits(env, monkeypatch):
    go, conn, r = env
    out, _, _ = go(THREE)
    tid = out["thread_id"]
    r.save_decisions(tid, full(conn))
    before = repo.row_counts(conn)
    real = repo._insert_mistake

    def boom(c, attempt_id, m):
        if m["status"] == "rejected":
            raise sqlite3.IntegrityError("gài lỗi giữa transaction")
        return real(c, attempt_id, m)

    monkeypatch.setattr(repo, "_insert_mistake", boom)
    r.resume(tid)
    row = r.wait(tid)
    assert row["status"] == "failed" and "gài lỗi" in row["error"]
    assert repo.row_counts(conn) == before and status(conn, out["session_id"]) == "failed"
    monkeypatch.setattr(repo, "_insert_mistake", real)
    r.resume(tid)  # reruns only the commit node; decisions are already in state
    assert r.wait(tid)["status"] == "committed"
    assert repo.row_counts(conn)["mistake"] == before["mistake"] + 4


def test_commit_twice_returns_the_first_receipt(env):
    go, conn, r = env
    out, _, _ = go(THREE)
    r.save_decisions(out["thread_id"], full(conn))
    r.resume(out["thread_id"])
    r.wait(out["thread_id"])
    first = r.state(out["thread_id"])["receipt"]
    again = repo.commit_session(conn, out["session_id"], transcript="x", review_seconds=1, attempts=[])
    assert {k: again[k] for k in ("attempt", "mistake", "rubric", "by_status")} == {
        k: first[k] for k in ("attempt", "mistake", "rubric", "by_status")}  # fmt: skip
    assert repo.row_counts(conn)["attempt"] == 3


def test_rubric_approved_at_step_3_is_written_in_commit(env):
    from tests.bankfix import P2
    from tests.graphs.g1 import prob

    go, conn, r = env
    out, _, _ = go(prob(P2[0], "LANE1 $m = -4$"))
    tid = out["thread_id"]
    items = [{"item_id": "r1", "text": "Thay x = 3", "points": 1}, {"item_id": "r2", "text": "m = -4", "points": 3}]
    r.save_decisions(tid, {"1": {"rubric_items": items}})
    r.resume(tid)
    assert r.wait(tid)["node"] == "gate_review"
    assert repo.row_counts(conn)["rubric"] == 2  # C-16: nothing before commit ②
    r.save_decisions(tid, {"cards": {"p1": {"action": "accept"}}})
    r.resume(tid)
    assert r.wait(tid)["status"] == "committed"
    rub = conn.execute(
        "SELECT r.id, r.version, r.items_json, r.max_score FROM rubric r JOIN problem p ON p.id = r.problem_id"
        " WHERE p.ref = ?", (P2[0],)).fetchall()  # fmt: skip
    assert [(v, json.loads(i), m) for _, v, i, m in rub] == [(1, items, 4)]
    assert conn.execute("SELECT rubric_id, max_score FROM attempt").fetchone() == (rub[0][0], 4)
    assert r.state(tid)["receipt"]["rubric"] == 1


def test_next_session_03_context_has_committed_mistakes(env):
    go, conn, r = env
    out, _, _ = go(THREE)
    r.save_decisions(out["thread_id"], full(conn))
    r.resume(out["thread_id"])
    r.wait(out["thread_id"])
    out2, _, _ = go(THREE.replace("LANE", "LAN"), name="b.tex", day="2026-10-21")
    ctx = r.state(out2["thread_id"])["lanes"][0]["diagnosis"]["context"]
    assert sorted(m["code"] for m in ctx) == ["computational.final_answer", "notational.symbol", "other.unclear"]
