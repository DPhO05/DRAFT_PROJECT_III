"""MONO-P2-01: save decisions, resume G1 at confirm_match, rerun after failure."""

from contextlib import closing

from tests.api.test_bank import import_mix
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
    sid = client.post("/api/students", json={"name": "Lê An", "grade": 8}, headers=W).json()["id"]
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


def keys(node):
    """Every dict key anywhere in a JSON value."""
    if isinstance(node, dict):
        return set(node) | {k for v in node.values() for k in keys(v)}
    return {k for v in node for k in keys(v)} if isinstance(node, list) else set()


def test_teacher_view_g2_card(paths, client):
    tid = import_mix(paths, client)
    poll(client, tid, until=("awaiting_review", "failed"))
    got = client.get(f"/api/threads/{tid}?view=teacher").json()
    assert set(got) == {"thread_id", "graph", "status", "updated_at", "card"}
    assert (got["graph"], got["status"]) == ("G2", "awaiting_review")
    c = got["card"]
    assert (c["kind"], c["stage"], c["file"], c["receipt"]) == ("bank_import", "preview", "mix.tex", None)
    assert (c["n_total"], c["n_ready"], c["n_need"], c["n_existing"], c["n_invalid"]) == (5, 1, 3, 1, 3)
    assert c["topic"]["name"] == "Hàm số bậc nhất"
    assert "delta" not in keys(got)
    by = {i["ref"]: i for i in reversed(c["items"])}  # the file's first 8DS-NEW-001 wins over its invalid copy
    assert len(c["items"]) == 8 and None in by  # the problem with no ref is listed as invalid
    assert (by["8DS-NEW-001"]["level"], by["8DS-NEW-001"]["needs"], len(by["8DS-NEW-001"]["kcs"])) == ("dễ", [], 1)
    assert set(by["8DS-NEW-001"]["kcs"][0]) == {"id", "name"} and by["8DS-NEW-001"]["rubric_items"]
    assert (by["8DS-NEW-002"]["level"], by["8DS-NEW-002"]["needs"]) == (None, ["kc", "level"])
    assert (by["8DS-NEW-003"]["level"], by["8DS-NEW-003"]["needs"], by["8DS-NEW-003"]["unknown_label"]) == (
        "khó", ["kc"], True)  # fmt: skip
    assert by["8DS-NEW-004"]["needs"] == ["level"] and by["8DS-PT1-001"]["existing"] is True
    assert by[None]["invalid"] and by["8DS-NEW-005"]["invalid"] and by["8DS-NEW-005"]["needs"] == []


def test_teacher_view_card_applies_saved_decisions(paths, client):
    tid = import_mix(paths, client)
    poll(client, tid, until=("awaiting_review", "failed"))
    kc = {k["code"]: k["id"] for k in client.get("/api/catalog/kc").json()}
    answer = {"items": {"8DS-NEW-002": {"kc_ids": [kc["8DS-HSBN-02"]], "level": "vừa"},
                        "8DS-NEW-004": {"level": None}}}  # fmt: skip
    assert client.put(f"/api/threads/{tid}/decisions", json=answer, headers=W).json()["pending"] == 1
    c = client.get(f"/api/threads/{tid}?view=teacher").json()["card"]
    by = {i["ref"]: i for i in reversed(c["items"])}
    assert (by["8DS-NEW-002"]["level"], by["8DS-NEW-002"]["needs"]) == ("vừa", [])
    assert [k["id"] for k in by["8DS-NEW-002"]["kcs"]] == [kc["8DS-HSBN-02"]]
    assert by["8DS-NEW-004"]["needs"] == []  # null level is an answer: left empty on purpose
    assert (c["n_ready"], c["n_need"]) == (3, 1)


def test_teacher_view_g1_card(paths, client):
    h = lane_handlers() | {"01": ingest.MatchResult(candidates=[ingest.Candidate(ref=P1[0], score=0.5)])}
    tid, _, _ = start(paths, client, h)
    got = client.get(f"/api/threads/{tid}?view=teacher").json()
    assert set(got) == {"thread_id", "graph", "status", "updated_at", "card"}
    assert (got["graph"], got["status"]) == ("G1", "awaiting_review")
    c = got["card"]
    assert (c["kind"], c["stage"], c["file"], c["held_on"], c["progress"]) == (
        "grading", "confirm", "a.tex", "2026-10-20", {"done": 0, "total": 1})  # fmt: skip
    assert [(f["seq"], f["type"], [x["ref"] for x in f["candidates"]]) for f in c["confirm"]] == [
        (1, "low_match", [P1[0]])
    ]
    assert c["lock"] is None and c["preview"] is None and c["error_words"] is None and c["receipt"] is None
    assert not keys(got) & {"node", "theta", "delta", "confidence", "tech"}
    assert "node" in client.get(f"/api/threads/{tid}").json()
    assert client.get("/api/threads/nope?view=teacher").status_code == 404
    assert c["saved"] is None
    client.put(f"/api/threads/{tid}/decisions", json={"1": {"problem_ref": P1[0]}}, headers=W)
    assert client.get(f"/api/threads/{tid}?view=teacher").json()["card"]["saved"] == {"1": {"problem_ref": P1[0]}}
    client.post(f"/api/threads/{tid}/resume", headers=W)
    poll(client, tid, until=("awaiting_review", "failed"))
    c = client.get(f"/api/threads/{tid}?view=teacher").json()["card"]
    assert (c["stage"], c["progress"], c["decided"], c["score"], c["max_score"]) == (
        "review", {"done": 1, "total": 1}, {"done": 0, "total": 1}, 1, 1)  # fmt: skip
    assert c["attempts"][0]["mistakes"][0]["pid"] == "p1" and c["preview"] is None
