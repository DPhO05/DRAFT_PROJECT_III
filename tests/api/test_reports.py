"""/api/reports, the G5 teacher card and the G5 reminders (P7-T07 backend, api-v3 §3.3, §5)."""

import json
import re
import time
from contextlib import closing

import pytest

from tests.agents.test_orchestrator import text, tool
from tests.api.test_review_api import submit
from tests.api.test_sessions import W
from tests.assistant_fix import SWAP, _problem_of_grade, world
from tests.db import test_profile_repo as prof
from tests.fakes import FakeLLM, lane_handlers
from tests.graphs.test_report import writer
from tutor import llm
from tutor.api import assistant
from tutor.db import repo
from tutor.graphs import report
from tutor.services import facts

WEEK = {"period_kind": "week", "period_start": "2026-10-12"}  # An: 14/10 session; Bình: 14/10 too
# tests/ui/check_v3.py FORBIDDEN, copied: that module needs playwright
FORBIDDEN = re.compile(
    r"θ|δ|\[F\d\d\]|thread|checkpoint|token|computational\.|conceptual\.|notational\.|presentation\.|other\.unclear"
    r"|g[1-5]-hs|\bnode\b|\b\d[A-Z]{2}-[A-Z0-9]+-\d\d\b"
)


@pytest.fixture
def env(paths, client):
    """(client, the dummy world's ids); 09 writes from the fact lines."""
    with closing(repo.connect(paths.tutor_db)) as conn:
        w = world(conn)
    llm.set_backend(FakeLLM({"09": writer}))
    return client, w


def card(client, tid, stage):
    for _ in range(200):
        c = client.get(f"/api/threads/{tid}?view=teacher").json()["card"]
        if c["stage"] == stage:
            return c
        time.sleep(0.05)
    raise AssertionError(c)


def start(client, sid, **period):
    r = client.post("/api/reports", json={"student_id": sid} | (period or WEEK), headers=W)
    return r, r.json().get("thread_id")


def put(client, tid, sentences):
    return client.put(f"/api/threads/{tid}/decisions", json={"sentences": sentences}, headers=W)


def approve(client, tid):
    assert client.post(f"/api/threads/{tid}/resume", headers=W).status_code == 202
    return card(client, tid, "saved")


def test_create_poll_edit_approve(env):
    client, w = env
    r, tid = start(client, w["an"])
    assert (r.status_code, r.json()) == (202, {"thread_id": "g5-hs01w-20261012", "status": "running"})
    c = card(client, tid, "draft")
    assert (c["kind"], c["student_id"], c["period_kind"], c["period_start"]) == (
        "report",
        w["an"],
        "week",
        "2026-10-12",
    )
    assert (c["n_flagged"], c["report_id"]) == (0, None)
    assert c["sentences"] and all(s["flag"] is None and s["facts"] for s in c["sentences"])
    got = put(client, tid, [{"text": "Em làm 45 bài.", "facts": []}])
    assert got.json() == {
        "saved": True,
        "pending": 0,
        "audit": [{"i": 0, "flag": "number", "why": "Số “45” không có trong dữ liệu đã duyệt."}],
    }
    assert card(client, tid, "draft")["n_flagged"] == 1  # Review Focus 1: flagged, approval still allowed
    done = approve(client, tid)
    assert done["report_id"] and done["sentences"] == [] and done["n_flagged"] == 0
    rep = client.get(f"/api/reports/{done['report_id']}").json()
    assert rep == {"id": done["report_id"], "student_id": w["an"], "approved_at": rep["approved_at"], **WEEK,
                   "sentences": ["Em làm 45 bài."], "file": "baocao-HS-01-week-2026-10-12.md"}  # fmt: skip


def test_post_conflicts(env):
    client, w = env
    _, tid = start(client, w["an"])
    card(client, tid, "draft")
    again, _ = start(client, w["an"])
    assert (again.status_code, again.json()) == (200, {"thread_id": tid, "status": "awaiting_review",
                                                       "existing": True})  # fmt: skip
    done = approve(client, tid)
    r, _ = start(client, w["an"])
    err = r.json()["error"]
    assert (r.status_code, err["code"]) == (409, "already_committed")
    assert err["detail"]["report_id"] == done["report_id"] and err["detail"]["approved_at"]
    r, _ = start(client, w["an"], period_kind="week", period_start="2026-10-19")
    err = r.json()["error"]
    assert (r.status_code, err["code"]) == (409, "not_ready")
    assert err["detail"] == {"reason": "no_committed_session", "previous_start": "2026-10-12", "pending": []}
    assert "no_committed_session" not in err["message"]  # the app words it; no code string in a message
    r, _ = start(client, w["an"], period_kind="week", period_start="2026-10-20")
    assert (r.status_code, r.json()["error"]["code"]) == (422, "validation_error")
    r, _ = start(client, 99)
    assert (r.status_code, r.json()["error"]["code"]) == (404, "not_found")
    assert client.post("/api/reports", json={"student_id": 1} | WEEK).status_code == 403  # no X-Tutor


def test_resume_refused_after_new_session(paths, env):
    """H13: a session approved in the period after the draft was written: 409, nothing saved."""
    client, w = env
    _, tid = start(client, w["an"])
    card(client, tid, "draft")
    with closing(repo.connect(paths.tutor_db)) as conn:
        p9, kc = _problem_of_grade(conn, 9)
        prof.commit(conn, prof.start(conn, w["an"], "2026-10-16"), [(p9, [prof.mk(SWAP, kc)])])
    r = client.post(f"/api/threads/{tid}/resume", headers=W)
    err = r.json()["error"]
    assert (r.status_code, err["code"]) == (409, "not_ready")
    assert err["message"] == "Có buổi mới được duyệt trong kỳ này. Bỏ bản nháp rồi tạo lại."
    assert card(client, tid, "draft")["stage"] == "draft" and client.get("/api/reports").json()["approved"] == []


def test_put_refusals(env):
    client, w = env
    _, tid = start(client, w["an"])
    shown = card(client, tid, "draft")["sentences"]
    for bad in ([{"text": " · ", "facts": []}], [{"text": 5}], "x"):  # wordless, wrong type, not a list
        r = put(client, tid, bad)
        assert (r.status_code, r.json()["error"]["code"]) == (422, "validation_error")
    assert card(client, tid, "draft")["sentences"] == shown  # a refused answer is not stored
    assert put(client, tid, []).json() == {"saved": True, "pending": 1, "audit": []}  # nothing left to approve
    assert client.post(f"/api/threads/{tid}/resume", headers=W).json()["error"]["code"] == "undecided_items"
    assert put(client, tid, [{"text": "Em cố gắng.", "facts": []}]).json()["pending"] == 0
    approve(client, tid)
    r = put(client, tid, [{"text": "Em cố gắng hơn.", "facts": []}])  # approved: nothing to edit
    assert (r.status_code, r.json()["error"]["code"]) == (409, "not_ready")


def test_lists(env):
    client, w = env
    _, a = start(client, w["an"])
    _, b = start(client, w["binh"])
    for tid in (a, b):
        card(client, tid, "draft")
    done = approve(client, a)
    put(client, b, [{"text": "Em làm 45 bài.", "facts": []}])
    llm.set_backend(FakeLLM({"09": RuntimeError("boom")}))
    _, bad = start(client, w["an"], period_kind="month", period_start="2026-10-01")
    card(client, bad, "failed")
    got = client.get("/api/reports").json()
    drafts = {d["thread_id"]: d for d in got["drafts"]}  # R21: at the gate or failed
    assert sorted((d["thread_id"], d["student_id"], d["period_kind"], d["period_start"], d["n_flagged"])
                  for d in got["drafts"]) == sorted([(b, w["binh"], "week", "2026-10-12", 1),
                                                     (bad, w["an"], "month", "2026-10-01", 0)])  # fmt: skip
    assert all(d["created_at"] for d in got["drafts"])
    [ok] = got["approved"]
    assert ok == {"id": done["report_id"], "student_id": w["an"], **WEEK, "approved_at": ok["approved_at"]}
    assert client.get(f"/api/reports?student={w['an']}").json() == {"drafts": [drafts[bad]], "approved": [ok]}
    assert client.get(f"/api/reports?student={w['binh']}").json() == {"drafts": [drafts[b]], "approved": []}
    assert client.get("/api/reports/999").status_code == 404
    text = client.get(f"/api/reports/{done['report_id']}").json()["sentences"]
    assert text and not any(re.search(r"\[?\bF\d\d\b", t) for t in text)  # C-44: no fact id after approval


def test_card_no_tech_text(env):
    client, w = env
    _, tid = start(client, w["an"])
    fresh = card(client, tid, "draft")
    put(client, tid, [{"text": "Em làm 45 bài.", "facts": []}, {"text": "Em làm đúng 80%.", "facts": []}])
    edited = card(client, tid, "draft")
    assert [s["flag"] for s in edited["sentences"]] == ["number", "percent"]
    for c in (fresh, edited):
        shown = {k: v for k, v in c.items() if k != "sentences"} | {
            "sentences": [{k: v for k, v in s.items() if k != "facts"} for s in c["sentences"]]
        }
        assert not FORBIDDEN.search(json.dumps(shown, ensure_ascii=False)), shown
        assert not re.search(r"\bF\d\d\b", json.dumps(shown["sentences"], ensure_ascii=False))


def test_card_stages(env):
    client, w = env
    llm.set_backend(FakeLLM({"09": RuntimeError("boom")}))
    _, tid = start(client, w["an"])
    c = card(client, tid, "failed")  # no draft yet: words only
    assert (c["report_id"], c["sentences"], c["n_flagged"]) == (None, [], 0)
    assert (c["student_id"], c["period_kind"], c["period_start"]) == (w["an"], "week", "2026-10-12")
    assert "boom" not in json.dumps(c)


@pytest.mark.parametrize(
    ("status", "draft", "stage"),
    [("running", False, "writing"), ("running", True, "saving"), ("awaiting_review", True, "draft"),
     ("committed", True, "saved"), ("failed", False, "failed"), ("failed", True, "failed")],
)  # fmt: skip
def test_card_stage_map(status, draft, stage):
    """R2: `writing` until 09 has a draft; the report id shows only once the thread is committed."""
    row = {"status": status, "student_id": 1, "decisions_json": None}
    state = {"period_kind": "week", "period_start": "2026-10-12", "receipt": {"report_id": 7}}
    if draft:
        state["draft"] = {"facts": [], "dates": [], "low": False, "sentences": [], "audit": []}
    got = report.card(row, state)
    assert got["stage"] == stage
    assert got["report_id"] == (7 if stage == "saved" else None)


def test_pending_reports(env):
    client, w = env
    _, tid = start(client, w["an"])
    card(client, tid, "draft")
    got = client.get("/api/assistant/pending").json()
    assert got["counts"] == {"assistant": 0, "reports": 1}
    assert got["items"] == [{"kind": "report", "thread_id": tid, "student_id": w["an"], **WEEK, "words": "nháp"}]
    llm.set_backend(FakeLLM({"09": RuntimeError("boom")}))
    _, bad = start(client, w["binh"])
    card(client, bad, "failed")
    got = client.get("/api/assistant/pending").json()
    assert got["counts"] == {"assistant": 0, "reports": 2}
    assert [(i["kind"], i["words"]) for i in got["items"]] == [("report", "nháp"), ("report", "chưa làm xong")]
    approve(client, tid)
    assert client.get("/api/assistant/pending").json()["counts"]["reports"] == 1


def ask(client, w, *turns, said="Làm báo cáo tuần cho @HS-01"):
    """One chat message to 00 scripted with `turns`; 09 writes from the fact lines. (events, fake)"""
    llm.set_backend(fake := FakeLLM({"09": writer, "00": list(turns)}))
    body = {"conversation_id": None, "text": said, "mentions": [w["an"]]}
    r = client.post("/api/assistant/messages", json=body, headers=W)
    assert r.status_code == 200, r.text
    return [json.loads(x) for x in r.text.splitlines()], fake


def sent_back(fake):
    """What 00 got as the tool result on its second turn."""
    return fake.calls[1]["messages"][-1]["content"][0]["content"]


def test_start_report_in_chat(paths, env):
    """P7-T09: the chat tool starts the G5 draft and shows its card; tutor.db is untouched until approval."""
    client, w = env
    with closing(repo.connect(paths.tutor_db)) as conn:
        before = repo.row_counts(conn)
    evs, fake = ask(client, w, [tool("start_report", code="HS-01", period_kind="week", period_start="2026-10-12")],
                    [text("Mình đã bắt đầu.")])  # fmt: skip
    assert [e["card"] for e in evs if e["type"] == "card"] == [{"kind": "report", "thread_id": "g5-hs01w-20261012"}]
    assert [e["state"] for e in evs if e["type"] == "tool"] == ["start", "done"]
    assert [e["items"] for e in evs if e["type"] == "source"] == [["báo cáo của HS-01"]]
    assert json.loads(sent_back(fake)) == {"code": "HS-01", "period_kind": "week", "period_start": "2026-10-12",
                                           "status": "running", "existing": False}  # fmt: skip
    assert [t["thread_id"] for t in client.app.state.runner.list_threads(graph="G5")] == ["g5-hs01w-20261012"]
    card(client, "g5-hs01w-20261012", "draft")
    with closing(repo.connect(paths.tutor_db)) as conn:
        assert repo.row_counts(conn) == before  # C-39: only Duyệt báo cáo writes


def test_start_report_not_ready_words(env):
    """An's week of 19/10 has no approved session; the week before has one (H11: the words carry that)."""
    client, w = env
    evs, fake = ask(client, w, [tool("start_report", code="HS-01", period_kind="week", period_start="2026-10-19")],
                    [text("Tuần này chưa làm được.")])  # fmt: skip
    assert [e["state"] for e in evs if e["type"] == "tool"] == ["start", "error"]
    assert not [e for e in evs if e["type"] == "card"]
    assert json.loads(sent_back(fake)) == {
        "error": "Kỳ này chưa có buổi nào đã duyệt. Kỳ gần nhất có dữ liệu bắt đầu 12/10."
    }
    assert client.app.state.runner.list_threads(graph="G5") == []


G1_TEX = "\\begin{problem}[9DS-BPT-001]\n$4x = 20$\n$x = 5$\n\\end{problem}\n"
NOT_READY = "Kỳ này chưa có buổi nào đã duyệt."


def waiting(client, w, day):
    """A G1 session of An left at its review gate: not approved, so not in any report period."""
    llm.set_backend(FakeLLM({"09": writer} | lane_handlers()))
    _, _, t = submit(client, w["an"], day, tex=G1_TEX)
    assert t["status"] == "awaiting_review"


def test_start_report_names_the_session_waiting(env):
    client, w = env
    waiting(client, w, "2026-10-20")
    _, fake = ask(client, w, [tool("start_report", code="HS-01", period_kind="week", period_start="2026-10-19")],
                  [text("Chưa làm được.")])  # fmt: skip
    assert json.loads(sent_back(fake)) == {
        "error": f"{NOT_READY} Buổi 20/10 còn chờ duyệt. Kỳ gần nhất có dữ liệu bắt đầu 12/10."
    }


def test_start_report_not_ready_numbers_are_known(env):
    """C-41: dates in a failed tool result count as known, so repeating them gets no warning; others still do."""
    client, w = env
    waiting(client, w, "2026-10-20")
    call = [tool("start_report", code="HS-01", period_kind="week", period_start="2026-10-19")]
    said = "Buổi 20/10 còn chờ duyệt, kỳ gần nhất có dữ liệu bắt đầu 12/10."
    evs, _ = ask(client, w, call, [text(said)])
    assert [e for e in evs if e["type"] == "warning"] == []
    evs, _ = ask(client, w, call, [text("Buổi 23/10 còn chờ duyệt.")])
    assert [e["numbers"] for e in evs if e["type"] == "warning"] == [["23/10"]]


@pytest.mark.parametrize(
    ("detail", "words"),
    [
        ({"previous_start": None, "pending": []}, NOT_READY),
        ({"previous_start": "2026-10-05", "pending": []}, f"{NOT_READY} Kỳ gần nhất có dữ liệu bắt đầu 05/10."),
        (
            {"previous_start": None, "pending": [{"held_on": "2026-10-08"}, {"held_on": "2026-10-06"}]},
            f"{NOT_READY} Buổi 06/10 còn chờ duyệt. Buổi 08/10 còn chờ duyệt.",
        ),
        (
            {"previous_start": "2026-09-28", "pending": [{"held_on": d} for d in ("2026-10-09", "2026-10-07",
                                                                                 "2026-10-08", "2026-10-06")]},
            f"{NOT_READY} Buổi 06/10 còn chờ duyệt. Buổi 07/10 còn chờ duyệt. Buổi 08/10 còn chờ duyệt."
            " Kỳ gần nhất có dữ liệu bắt đầu 28/09.",
        ),
    ],
)  # fmt: skip
def test_not_ready_words_by_detail(monkeypatch, detail, words):
    """Pending sessions: oldest first, at most 3, dd/mm; the previous-period line only when one exists."""

    def refuse(*a, **k):
        raise facts.NotReady({"reason": "no_committed_session"} | detail)

    monkeypatch.setattr(assistant.report, "start", refuse)
    with pytest.raises(ValueError) as e:
        assistant.make_starters(None, None).start_report(1, "week", "2026-10-05")
    assert str(e.value) == words


def test_start_report_approved_words(env):
    client, w = env
    _, tid = start(client, w["an"])
    card(client, tid, "draft")
    done = approve(client, tid)
    day = client.get(f"/api/reports/{done['report_id']}").json()["approved_at"][:10]
    _, fake = ask(client, w, [tool("start_report", code="HS-01", period_kind="week", period_start="2026-10-12")],
                  [text("Kỳ này đã duyệt rồi.")])  # fmt: skip
    d, m, y = day[8:], day[5:7], day[:4]
    assert json.loads(sent_back(fake)) == {
        "error": f"Báo cáo kỳ này đã duyệt ngày {d}/{m}/{y}. Mỗi kỳ chỉ duyệt một lần."
    }
