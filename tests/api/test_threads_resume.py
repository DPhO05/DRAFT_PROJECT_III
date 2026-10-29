"""MONO-P2-01: save decisions, resume G1 at confirm_match, rerun after failure."""

from contextlib import closing

from tests.api.test_sessions import W, poll
from tests.bankfix import P1, add_bank
from tests.fakes import FakeLLM, lane_handlers
from tutor import llm
from tutor.agents import ingest
from tutor.db import repo

NO_ID = "\\begin{problem}\nGiải $4x - 20 = 0$.\n$x = 5$\n\\end{problem}\n"


def start(paths, client, handlers):
    fake = FakeLLM(handlers)
    llm.set_backend(fake)
    with closing(repo.connect(paths.tutor_db)) as conn:
        add_bank(conn)
    sid = client.post("/api/students", json={"name": "An", "grade": 8}, headers=W).json()["id"]
    (paths.inbox / "a.tex").write_text(NO_ID, encoding="utf-8")
    tid = client.post("/api/sessions", json={"student_id": sid, "held_on": "2026-10-20", "path": "a.tex"},
                      headers=W).json()["thread_id"]  # fmt: skip
    return tid, poll(client, tid), fake


def test_confirm_match_then_review_gate(paths, client):
    h = lane_handlers() | {"01": ingest.MatchResult(candidates=[ingest.Candidate(ref=P1[0], score=0.5)])}
    tid, t, fake = start(paths, client, h)
    assert (t["status"], t["node"]) == ("awaiting_review", "gate_confirm_match")
    r = client.post(f"/api/threads/{tid}/resume", headers=W)
    assert r.status_code == 409 and r.json()["error"]["code"] == "undecided_items"
    assert r.json()["error"]["detail"] == {"n": 1}
    r = client.put(f"/api/threads/{tid}/decisions", json={"1": {"problem_ref": "NO"}}, headers=W)
    assert r.json() == {"saved": True, "pending": 1}
    r = client.put(f"/api/threads/{tid}/decisions", json={"1": {"problem_ref": P1[0]}}, headers=W)
    assert r.json() == {"saved": True, "pending": 0}
    r = client.post(f"/api/threads/{tid}/resume", headers=W)
    assert r.status_code == 202 and r.json() == {"thread_id": tid, "status": "running"}
    t = poll(client, tid, until=("awaiting_review", "failed"))
    assert (t["status"], t["node"]) == ("awaiting_review", "gate_review")
    state = client.get(f"/api/threads/{tid}?include=state").json()["state"]
    assert len(state["proposals"]) == 1 and state["proposals"][0]["verifier"]["verdict"] == "agree"
    r = client.post(f"/api/threads/{tid}/resume", headers=W)
    assert r.status_code == 409 and r.json()["error"] == {"code": "undecided_items", "message": "Còn 1 mục chưa xử lý",
                                                          "detail": {"n": 1}}  # fmt: skip
    assert fake.count == {"01": 1, "02": 1, "03": 1, "04": 1}


def test_failed_thread_reruns_from_checkpoint(paths, client):
    failed = []

    def once(user):
        if not failed:
            failed.append(1)
            return RuntimeError("gài lỗi 03")
        return None

    h = lane_handlers(fail_03=once) | {"01": ingest.MatchResult(candidates=[ingest.Candidate(ref=P1[0], score=0.9)])}
    tid, t, fake = start(paths, client, h)
    assert t["status"] == "failed" and "gài lỗi 03" in t["error"]
    assert client.post(f"/api/threads/{tid}/resume", headers=W).status_code == 202
    t = poll(client, tid, until=("awaiting_review", "failed"))
    assert t["node"] == "gate_review" and fake.count == {"01": 1, "02": 1, "03": 2, "04": 1}


def test_unknown_thread_404(client):
    assert client.put("/api/threads/nope/decisions", json={}, headers=W).status_code == 404
    assert client.post("/api/threads/nope/resume", headers=W).status_code == 404
