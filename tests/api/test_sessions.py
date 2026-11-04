"""MONO-P1-03: inbox, submit (S1), threads polling."""

import time
from contextlib import closing

from tests.bankfix import P2, add_bank
from tests.fakes import FakeLLM, lane_handlers
from tutor import llm
from tutor.agents.a01_ingest import ingest
from tutor.db import repo

W = {"X-Tutor": "1"}
TEX = "\\begin{problem}[8DS-PT1-001]\n$4x = 20$\n$x = 5$\n\\end{problem}\n"


def add_student(client):
    llm.set_backend(FakeLLM(lane_handlers()))
    with closing(repo.connect(client.app.state.paths.tutor_db)) as conn:
        add_bank(conn)
    return client.post("/api/students", json={"name": "Lê An", "grade": 8}, headers=W).json()["id"]


def poll(client, tid, until=("done", "awaiting_review", "failed", "committed")):
    for _ in range(100):
        t = client.get(f"/api/threads/{tid}").json()
        if t["status"] in until:
            return t
        time.sleep(0.05)
    raise AssertionError(t)


def test_inbox_lists_files_with_sha_and_submitted(paths, client):
    (paths.inbox / "a.tex").write_text(TEX, encoding="utf-8")
    sid = add_student(client)
    [f] = client.get("/api/sessions/inbox").json()
    assert f["path"] == "a.tex" and len(f["sha256"]) == 64 and f["submitted_by"] == []
    client.post("/api/sessions", json={"student_id": sid, "held_on": "2026-10-20", "path": "a.tex"}, headers=W)
    assert client.get("/api/sessions/inbox").json()[0]["submitted_by"] == [sid]


def test_inbox_guess(paths, client):
    sid = add_student(client)
    gone = client.post("/api/students", json={"name": "Trần Bình", "grade": 8}, headers=W).json()["id"]
    with closing(repo.connect(paths.tutor_db)) as conn:
        repo.archive_student(conn, gone)
    names = ["hs01-2026-10-21.tex", "hs09-2026-10-21.tex", "bai-lam-moi.tex", f"hs{gone:02d}-2026-10-21.tex",
             "hs01-2026-13-40.tex"]  # fmt: skip
    for n in names:
        (paths.inbox / n).write_text(TEX, encoding="utf-8")
    got = {f["path"]: f["guess"] for f in client.get("/api/sessions/inbox").json()}
    assert got == {"hs01-2026-10-21.tex": {"student_id": sid, "held_on": "2026-10-21"}} | {
        n: None for n in names[1:]}  # fmt: skip


def test_submit_202_then_poll_thread(paths, client):
    (paths.inbox / "a.tex").write_text(TEX, encoding="utf-8")
    sid = add_student(client)
    r = client.post("/api/sessions", json={"student_id": sid, "held_on": "2026-10-20", "path": "a.tex"}, headers=W)
    assert r.status_code == 202
    body = r.json()
    assert body == {"thread_id": "g1-hs01-20261020", "session_id": body["session_id"], "status": "running"}
    t = poll(client, body["thread_id"])
    assert t["graph"] == "G1" and t["subject"] == "HS-01 · buổi 20/10/2026" and t["error"] is None
    full = client.get(f"/api/threads/{body['thread_id']}?include=state").json()
    assert full["state"]["transcript"] == TEX and full["state"]["ingest"]["attempts"][0]["ref"] == "8DS-PT1-001"
    assert [s["thread_id"] for s in client.get("/api/sessions").json()] == [body["thread_id"]]
    assert [t["thread_id"] for t in client.get("/api/threads?graph=G1").json()] == [body["thread_id"]]


def test_submit_errors(paths, client):
    (paths.inbox / "a.tex").write_text(TEX, encoding="utf-8")
    sid = add_student(client)
    ok = {"student_id": sid, "held_on": "2026-10-20", "path": "a.tex"}
    client.post("/api/sessions", json=ok, headers=W)
    r = client.post("/api/sessions", json=ok | {"held_on": "2026-10-27"}, headers=W)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "duplicate_submission")
    r = client.post("/api/sessions", json=ok | {"path": "../settings.json"}, headers=W)
    assert (r.status_code, r.json()["error"]["code"]) == (422, "validation_error")
    assert client.get("/api/threads/nope").status_code == 404


NO_ID = "\\begin{problem}\nTìm m để $2x + m = 5 - x$ nhận $x = 3$.\n$m = -4$\n\\end{problem}\n"


def submit(client, sid, held_on, name, text):
    (client.app.state.paths.inbox / name).write_text(text, encoding="utf-8")
    body = {"student_id": sid, "held_on": held_on, "path": name}
    return poll(client, client.post("/api/sessions", json=body, headers=W).json()["thread_id"])["thread_id"]


def test_threads_show_gate_and_failure_with_checkpoints(client):
    sid = add_student(client)
    llm.set_backend(FakeLLM({"01": ingest.MatchResult(candidates=[ingest.Candidate(ref=P2[0], score=0.5)])}))
    gate = submit(client, sid, "2026-10-20", "gate.tex", NO_ID)
    llm.set_backend(FakeLLM({"01": RuntimeError("gài lỗi 01")}))
    bad = submit(client, sid, "2026-10-27", "bad.tex", NO_ID + "% lần 2\n")
    rows = {t["thread_id"]: t for t in client.get("/api/threads").json()}
    assert (rows[gate]["status"], rows[gate]["node"]) == ("awaiting_review", "gate_confirm_match")
    assert rows[bad]["status"] == "failed" and "gài lỗi 01" in rows[bad]["error"]
    assert rows[gate]["checkpoints"] > 0 and rows[bad]["checkpoints"] > 0
    state = client.get(f"/api/threads/{gate}?include=state").json()["state"]
    assert {"session_id", "student_id", "held_on", "source_path", "source_kind", "transcript", "ingest"} <= set(state)


def test_submit_file_without_a_problem_is_422_with_words(paths, client):
    (paths.inbox / "empty.tex").write_text("Chưa có bài nào.\n", encoding="utf-8")
    sid = add_student(client)
    r = client.post("/api/sessions", json={"student_id": sid, "held_on": "2026-10-20", "path": "empty.tex"}, headers=W)
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    assert r.json()["error"]["message"].startswith("File không có \\begin{problem} nào")
    assert client.get("/api/sessions").json() == []
