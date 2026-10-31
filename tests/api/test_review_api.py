"""MONO-P3-01 review → commit ② over HTTP; MONO-P3-02 queue lock, cancel, cleanup, backup now."""

import sqlite3
from contextlib import closing

from tests.api.test_sessions import TEX, W, add_student, poll
from tutor.db import repo

ACCEPT = {"cards": {"p1": {"action": "accept"}}, "review_seconds": 12}


def submit(client, sid, day="2026-10-20", name="a.tex", tex=TEX):
    (client.app.state.paths.inbox / name).write_text(tex, encoding="utf-8")
    r = client.post("/api/sessions", json={"student_id": sid, "held_on": day, "path": name}, headers=W).json()
    return r["thread_id"], r["session_id"], poll(client, r["thread_id"])


def approve(client, tid):
    """gate_review → resume → stop at the preview (gate_confirm_commit) → resume → commit ②; returns the thread."""
    for until in ("awaiting_review", "committed"):
        assert client.post(f"/api/threads/{tid}/resume", headers=W).status_code == 202
        t = poll(client, tid, until=(until, "failed"))
    return t


def test_review_then_commit_receipt_and_session_view(client):
    sid = add_student(client)
    tid, session_id, t = submit(client, sid)
    assert t["node"] == "gate_review"
    r = client.put(f"/api/threads/{tid}/decisions", json={"cards": {}}, headers=W)
    assert r.json() == {"saved": True, "pending": 1}
    r = client.post(f"/api/threads/{tid}/resume", headers=W)
    assert r.status_code == 409 and r.json()["error"]["detail"] == {"n": 1}
    assert client.put(f"/api/threads/{tid}/decisions", json=ACCEPT, headers=W).json()["pending"] == 0
    before = client.get("/api/backup").json()
    assert client.post(f"/api/threads/{tid}/resume", headers=W).status_code == 202
    t = poll(client, tid, until=("awaiting_review", "failed"))
    assert (t["status"], t["node"]) == ("awaiting_review", "gate_confirm_commit")
    r = client.put(f"/api/threads/{tid}/decisions", json=ACCEPT, headers=W)  # decisions are final at the preview
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_ready"
    assert client.post(f"/api/threads/{tid}/resume", headers=W).status_code == 202
    t = poll(client, tid, until=("committed", "failed"))
    assert t["status"] == "committed" and t["error"] is None
    after = client.get("/api/backup").json()
    rec = t["receipt"]
    assert (rec["attempt"], rec["mistake"], rec["rubric"]) == (1, 1, 0) and rec["backup"] in [
        b["name"] for b in after["backups"]]  # fmt: skip
    assert after["total"] - before["total"] == rec["attempt"] + rec["mistake"] + rec["rubric"] + rec[
        "skill_event"] + 1  # + the one KC's skill_state row  # fmt: skip
    s = client.get(f"/api/sessions/{session_id}").json()
    assert (s["status"], s["review_seconds"], s["student_code"]) == ("committed", 12, "HS-01")
    [a] = s["attempts"]
    assert (a["ref"], a["score"], a["max_score"]) == ("8DS-PT1-001", 1, 1)
    assert a["steps"][0]["idx"] == 1 and a["grade"][0]["item_id"] == "r1" and a["rubric"]["items"][0]["item_id"] == "r1"
    [m] = a["mistakes"]
    assert m["status"] == "confirmed" and m["llm_json"]["pid"] == "p1" and m["verifier_verdict"] == "agree"
    assert client.post(f"/api/threads/{tid}/resume", headers=W).json()["error"]["code"] == "already_committed"
    assert client.get("/api/sessions/999").status_code == 404


def test_later_session_locked_until_earlier_commits(client):
    sid = add_student(client)
    first, _, _ = submit(client, sid, day="2026-10-17")
    later, _, _ = submit(client, sid, day="2026-10-20", name="b.tex", tex=TEX.replace("4x", "3x"))
    q = client.get("/api/threads?status=awaiting_review").json()
    assert [(t["thread_id"], t["locked"], t["blocking_thread_id"]) for t in q] == [
        (first, False, None), (later, True, first)]  # fmt: skip
    assert "17/10" in q[1]["lock_reason"]
    client.put(f"/api/threads/{later}/decisions", json=ACCEPT, headers=W)
    r = client.post(f"/api/threads/{later}/resume", headers=W)
    assert r.status_code == 409 and r.json()["error"]["code"] == "date_order_locked"
    assert r.json()["error"]["detail"] == {"blocking_thread_id": first}
    assert client.get(f"/api/threads/{later}").json()["locked"] is True


def test_cancel_and_cleanup(client):
    sid = add_student(client)
    tid, session_id, _ = submit(client, sid)
    r = client.post(f"/api/threads/{tid}/cancel", headers=W)
    assert r.status_code == 200 and r.json() == {"cancelled": tid, "session_deleted": 1}
    assert client.get(f"/api/threads/{tid}").status_code == 404
    assert client.get("/api/sessions").json() == []
    tid, _, _ = submit(client, sid)  # same file again: C-15
    client.put(f"/api/threads/{tid}/decisions", json=ACCEPT, headers=W)
    approve(client, tid)
    r = client.post(f"/api/threads/{tid}/cancel", headers=W)
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_committed"
    assert client.post("/api/threads/cleanup", headers=W).json() == {"removed": [tid]}
    assert client.get("/api/threads").json() == []
    assert client.get("/api/sessions").json()[0]["status"] == "committed"  # tutor.db keeps the result


def test_backup_now(client):
    r = client.post("/api/backup", headers=W)
    assert r.status_code == 200
    body = r.json()
    path = client.app.state.paths.backup / body["path"]
    with closing(sqlite3.connect(path)) as c:
        assert sum(repo.row_counts(c).values()) == body["rows"]
