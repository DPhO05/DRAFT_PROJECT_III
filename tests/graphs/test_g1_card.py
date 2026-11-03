"""P6-T11 (Task 10): the G1 grading card for the chat (api-v3 §3.4), its reminder (§3.3), lane progress (R24)."""

import json
import re

import pytest

from tests.bankfix import P1, P2, P9
from tests.fakes import lane_handlers
from tests.graphs.g1 import THREE, approve, prob
from tests.graphs.test_review import full, kc_id
from tutor.agents.a01_ingest import ingest
from tutor.agents.a03_diagnoser import diagnoser
from tutor.agents.a04_verifier import verifier
from tutor.db import repo
from tutor.graphs import session, threads

MATCH = {"01": ingest.MatchResult(candidates=[ingest.Candidate(ref=P1[0], score=0.5),
                                              ingest.Candidate(ref=P9[0], score=0.3)])}  # fmt: skip
# tests/ui/check_v3.py:27-30 (that module needs playwright)
FORBIDDEN = re.compile(
    r"θ|δ|\[F\d\d\]|thread|checkpoint|token|computational\.|conceptual\.|notational\.|presentation\.|other\.unclear"
    r"|g[1-5]-hs|\bnode\b|\b\d[A-Z]{2}-[A-Z0-9]+-\d\d\b"
)
TAIL = "Bài làm vẫn còn nguyên, chưa có gì được lưu."


def row_of(r, tid) -> dict:
    return next(t for t in threads.annotate(r.list_threads()) if t["thread_id"] == tid)


def card_of(r, tid, **row_over) -> dict:
    return session.card(r._paths_for_test, row_of(r, tid) | row_over, r.state(tid), r.done_count(tid, "lane"))


def reminder_of(r, tid) -> dict:
    return session.reminder(r._paths_for_test, row_of(r, tid), r.state(tid))


def keys(node) -> set:
    if isinstance(node, dict):
        return set(node) | {k for v in node.values() for k in keys(v)}
    return {k for v in node for k in keys(v)} if isinstance(node, list) else set()


def scrub(node):
    """The card without the values the app only sends back: codes, thread ids."""
    if isinstance(node, dict):
        return {k: scrub(v) for k, v in node.items() if k not in ("code", "suggested_code", "thread_id", "blocked_by")}
    return [scrub(v) for v in node] if isinstance(node, list) else node


def test_stages(env):
    go, conn, r = env
    out, _, _ = go(THREE)
    tid = out["thread_id"]
    c = card_of(r, tid)
    assert (c["kind"], c["stage"], c["student_id"], c["held_on"], c["file"]) == (
        "grading",
        "review",
        1,
        "2026-10-20",
        "a.tex",
    )
    assert (c["progress"], c["score"], c["max_score"], c["decided"]) == (
        {"done": 3, "total": 3}, 3, 3, {"done": 0, "total": 3})  # fmt: skip
    assert (c["confirm"], c["preview"], c["preview_sig"], c["lock"], c["error_words"], c["receipt"]) == (
        [], None, None, None, None, None)  # fmt: skip
    rows = [(a["seq"], a["ref"], a["score"], a["max_score"], a["skipped"], a["rubric_draft"]) for a in c["attempts"]]
    assert rows == [
        (1, P1[0], 1, 1, False, False), (2, P9[0], 1, 1, False, False), (3, P1[0], 1, 1, False, False)]  # fmt: skip
    a = c["attempts"][0]
    assert a["statement_latex"] == P1[1] and a["kcs"] == [{"id": kc_id(conn), "name": "Chuyển vế"}]
    assert a["steps"][0]["idx"] == 1 and "LANE1" in a["steps"][0]["latex"] and set(a["steps"][0]) == {"idx", "latex"}
    unclear = next(c["description"] for c in repo.error_codes(conn) if c["code"] == "other.unclear")
    assert a["mistakes"] == [{
        "pid": "p1", "step_idx": 1, "code": "other.unclear", "kind": unclear, "kc": None, "description": "lỗi 0",
        "evidence_latex": "x", "unsure": True, "suggested_code": None, "check": None,
    }]  # fmt: skip

    assert r.save_decisions(tid, full(conn)) == 0
    before = repo.row_counts(conn)
    c = card_of(r, tid)
    assert repo.row_counts(conn) == before
    assert c["decided"] == {"done": 3, "total": 3} and c["preview"]["kcs"][0]["kc"] == "Chuyển vế"
    assert "writes" not in c["preview"] and c["preview_sig"] == session.sig(c["preview"])

    r.resume(tid)
    assert r.wait(tid)["node"] == "gate_confirm_commit"
    p = card_of(r, tid)
    assert (p["stage"], p["progress"], p["decided"]) == ("preview", None, None)
    assert (p["preview"], p["preview_sig"]) == (c["preview"], c["preview_sig"])  # the review preview is node 05's

    r.resume(tid)
    assert r.wait(tid)["status"] == "committed"
    s = card_of(r, tid)
    assert s["stage"] == "saved" and s["preview"] is None
    assert s["receipt"] == {"score": 3, "max_score": 3, "n_mistakes": 3, "backed_up": True}  # 4 cards, 1 rejected


def test_saved_decisions_come_back(env):
    go, conn, r = env
    out, _, _ = go(prob(None, "LANE1 $x = 1$") + prob(None, "LANE2 $x = 2$"), handlers=lane_handlers() | MATCH)
    tid = out["thread_id"]
    assert card_of(r, tid)["saved"] is None
    part = {"1": {"problem_ref": P1[0], "note": "đúng bài"}}
    assert r.save_decisions(tid, part) == 1
    c = card_of(r, tid)
    assert c["saved"] == part and [f["seq"] for f in c["confirm"]] == [1, 2]  # confirm[] is not trimmed
    assert r.save_decisions(tid, part | {"2": {"skip": True}}) == 0
    r.resume(tid)
    r.wait(tid)
    # the confirm answers stay stored until the first review PUT replaces them
    assert card_of(r, tid)["saved"] == part | {"2": {"skip": True}}

    add = {"action": "add", "attempt_seq": 1, "step_idx": 1, "code": "notational.symbol", "description": "sót"}
    review = {"cards": {"p1": {"action": "edit", "code": "notational.symbol", "description": "sửa"}, "n1": add},
              "review_seconds": 40}  # fmt: skip
    assert r.save_decisions(tid, review) == 0
    assert card_of(r, tid)["saved"] == review
    r.resume(tid)
    assert r.wait(tid)["node"] == "gate_confirm_commit"
    assert card_of(r, tid)["saved"] == review  # same at the preview step


def test_confirm_low_match(env):
    go, conn, r = env
    out, _, _ = go(prob(P1[0], "LANE1 $4x = 20$") + prob(None, "LANE2 $x = 2$"), handlers=lane_handlers() | MATCH)
    tid = out["thread_id"]
    c = card_of(r, tid)
    assert (c["stage"], c["progress"], c["score"], c["decided"], c["preview"]) == (
        "confirm",
        {"done": 0, "total": 2},
        None,
        None,
        None,
    )
    assert c["confirm"] == [{
        "seq": 2, "type": "low_match", "first_step_latex": "LANE2 $x = 2$",
        "candidates": [{"ref": P1[0], "statement_latex": P1[1], "best": True},
                       {"ref": P9[0], "statement_latex": P9[1], "best": False}],
    }]  # fmt: skip
    assert [(a["seq"], a["ref"], a["statement_latex"], a["kcs"], a["score"]) for a in c["attempts"]][1] == (
        2,
        None,
        None,
        [],
        None,
    )

    assert r.save_decisions(tid, {"2": {"skip": True}}) == 0
    r.resume(tid)
    r.wait(tid)
    c = card_of(r, tid)
    assert (c["stage"], c["confirm"], c["progress"]) == ("review", [], {"done": 1, "total": 1})
    assert [(a["seq"], a["skipped"]) for a in c["attempts"]] == [(1, False), (2, True)]


def test_rubric_draft_in_confirm(env):
    go, conn, r = env
    out, _, _ = go(prob(P1[0], "LANE1 $4x = 20$") + prob(P2[0], "LANE2 $m = -4$"))
    tid = out["thread_id"]
    c = card_of(r, tid)
    assert c["stage"] == "confirm" and len(c["confirm"]) == 1
    assert c["confirm"][0] == {"seq": 2, "type": "no_rubric", "ref": P2[0],
                               "rubric_draft": [{"item_id": "r1", "text": "Đáp số đúng", "points": 2}]}  # fmt: skip
    items = [{"item_id": "r1", "text": "Thay x = 3", "points": 2}]
    assert r.save_decisions(tid, {"2": {"rubric_items": items}}) == 0
    r.resume(tid)
    r.wait(tid)
    c = card_of(r, tid)
    assert (c["stage"], c["confirm"]) == ("review", [])
    assert [(a["seq"], a["rubric_draft"], a["max_score"]) for a in c["attempts"]] == [(1, False, 1), (2, True, 2)]


def test_progress_counts_lanes(env):
    go, conn, r = env
    out, _, _ = go(THREE)
    tid = out["thread_id"]
    assert r.done_count(tid, "lane") == 3 and r.done_count(tid, "queue") == 1 and r.done_count(tid, "nope") == 0
    assert r.done_count("no-such-thread", "lane") is None
    r.save_decisions(tid, full(conn))
    r.resume(tid)
    r.wait(tid)
    assert r.done_count(tid, "lane") == 0  # counts restart at every submit
    row = row_of(r, tid)
    assert session.card(r._paths_for_test, row, r.state(tid), None)["progress"] is None  # not counted in this process


def test_progress_after_failed_lane_rerun(env):
    go, conn, r = env
    failed = []

    def once(user):
        if "LANE2" in user and not failed:
            failed.append(1)
            return RuntimeError("gài lỗi")
        return None

    out, row, _ = go(THREE, handlers=lane_handlers(fail_03=once))
    tid = out["thread_id"]
    assert row["status"] == "failed"
    r.resume(tid)
    assert r.wait(tid)["node"] == "gate_review"
    assert card_of(r, tid)["progress"] == {"done": 3, "total": 3}


def test_failed_stage_names_the_lane(env):
    go, conn, r = env
    out, _, _ = go(THREE, handlers=lane_handlers(fail_03=lambda u: RuntimeError("gài lỗi") if "LANE2" in u else None))
    c = card_of(r, out["thread_id"])
    assert c["stage"] == "failed" and c["progress"] is None
    assert c["error_words"] == f"Gặp lỗi không lường trước khi đang chấm bài 2. {TAIL}"
    assert "gài lỗi" not in json.dumps(c, ensure_ascii=False)


@pytest.mark.parametrize(("error", "node", "reason", "step"), [
    ("LLMUnavailable: 03: Connection error.", "ingest", "Mất kết nối", "đọc bài"),
    ("LLMUnavailable: 01: Request timed out.", "prepare", "Mất kết nối", "đọc bài"),
    ("LLMUnavailable: 04: Error code: 429 - {'type': 'error'}", "lane", "Dịch vụ trợ lý đang quá tải", "chấm bài"),
    ("LLMUnavailable: 02: Error code: 529 - overloaded", "profile", "Dịch vụ trợ lý đang quá tải", "tính tiến bộ"),
    ("Tiến trình dừng giữa chừng (tắt app / máy ngủ); bấm Chạy lại", "commit", "App bị tắt", "lưu kết quả"),
    ("KeyError: 'x'", "commit", "Gặp lỗi không lường trước", "lưu kết quả"),
])  # fmt: skip
def test_error_words(env, error, node, reason, step):
    go, conn, r = env
    out, _, _ = go(THREE)
    c = card_of(r, out["thread_id"], status="failed", node=node, error=error)
    assert (c["stage"], c["error_words"]) == ("failed", f"{reason} khi đang {step}. {TAIL}")


def test_locked_stage(env):
    go, conn, r = env
    first, _, _ = go(THREE, day="2026-10-17")
    later, _, _ = go(THREE.replace("LANE", "LAN"), name="b.tex", day="2026-10-20")
    c = card_of(r, later["thread_id"])
    assert c["stage"] == "locked"
    assert c["lock"] == {"blocked_by": {"thread_id": first["thread_id"], "held_on": "2026-10-17"},
                         "why": "earlier_pending"}  # fmt: skip
    assert card_of(r, first["thread_id"])["lock"] is None
    assert reminder_of(r, later["thread_id"])["words"] == "chờ duyệt buổi 17/10 trước"


@pytest.mark.parametrize(("status", "why"), [("awaiting_review", "earlier_pending"), ("failed", "earlier_failed"),
                                             ("running", "earlier_running")])  # fmt: skip
def test_lock_why(env, status, why):
    go, conn, r = env
    out, _, _ = go(THREE)
    over = {"locked": True, "blocking_thread_id": "x", "blocking_held_on": "2026-10-17", "blocking_status": status}
    assert card_of(r, out["thread_id"], **over)["lock"]["why"] == why


def test_running_stages(env):
    go, conn, r = env
    out, _, _ = go(THREE)
    tid = out["thread_id"]
    for node, stage in [
        (None, "reading"),
        ("ingest", "reading"),
        ("mark_waiting", "reading"),
        ("prepare", "grading"),
        ("apply_match", "grading"),
        ("lane", "grading"),
        ("queue", "grading"),
        ("mark_waiting_review", "grading"),
        ("gate_review", "saving"),
        ("profile", "saving"),
        ("mark_waiting_confirm", "saving"),
        ("gate_confirm_commit", "saving"),
        ("commit", "saving"),
    ]:
        assert card_of(r, tid, status="running", node=node)["stage"] == stage, node
    c = session.card(r._paths_for_test, row_of(r, tid) | {"status": "running", "node": None}, {}, None)
    assert (c["stage"], c["attempts"], c["progress"], c["score"]) == ("reading", [], None, None)


def test_prepare_with_open_flag_is_still_reading(env):
    go, conn, r = env
    out, _, _ = go(prob(P2[0], "LANE1 $m = -4$"))
    assert card_of(r, out["thread_id"], status="running", node="prepare")["stage"] == "reading"


def test_card_has_no_tech_text(env):
    go, conn, r = env

    def g03(user, system):
        m = diagnoser.MistakeOut(step_idx=1, code="other.unclear", kc_id=kc_id(conn), confidence=0.9,
                                 evidence_latex="x", description="Dùng sai other.unclear ở bước này")  # fmt: skip
        return diagnoser.DiagnosisOut(corrected_latex="", mistakes=[m])

    def g04(user, system):
        if "LANE1" in user:
            return verifier.VerdictOut(verdict="wrong_code", reason="mã khác", suggested_code="notational.symbol")
        if "LANE2" in user:
            return verifier.VerdictOut(verdict="disagree", reason="Bước đúng, không phải other.unclear")
        return verifier.VerdictOut(verdict="agree", reason="đúng")

    out, _, _ = go(THREE, handlers=lane_handlers() | {"03": g03, "04": g04})
    tid = out["thread_id"]
    c = card_of(r, tid)
    m = [a["mistakes"][0] for a in c["attempts"]]
    sym = next(x["description"] for x in repo.error_codes(conn) if x["code"] == "notational.symbol")
    assert (
        m[0]["check"] == f"Kiểm tra lại thấy có thể là loại “{sym}”." and m[0]["suggested_code"] == "notational.symbol"
    )
    assert m[1]["check"].startswith("Kiểm tra lại thấy có thể không phải lỗi: Bước đúng, không phải ")
    assert m[2]["check"] is None and m[2]["unsure"] is False and m[2]["kc"] == {"id": kc_id(conn), "name": "Chuyển vế"}
    assert "other.unclear" not in m[0]["description"] and m[0]["description"].startswith("Dùng sai ")
    cards = [c]
    r.save_decisions(tid, full(conn))
    cards.append(card_of(r, tid))
    r.resume(tid)
    r.wait(tid)
    cards.append(card_of(r, tid))
    r.resume(tid)
    r.wait(tid)
    cards.append(card_of(r, tid))
    assert [x["stage"] for x in cards] == ["review", "review", "preview", "saved"]
    assert cards[1]["preview"] and cards[2]["preview"]
    for x in cards:
        assert not FORBIDDEN.search(json.dumps(scrub(x), ensure_ascii=False))
        assert not keys(x) & {"theta", "delta", "confidence", "node", "tech"}


def test_preview_only_when_decided(env):
    go, conn, r = env
    out, _, _ = go(THREE)
    tid = out["thread_id"]
    undecided = {"cards": {"p1": {"action": "accept"}}}
    assert r.save_decisions(tid, undecided) == 2
    before = repo.row_counts(conn)
    c = card_of(r, tid)
    assert (c["stage"], c["decided"], c["preview"], c["preview_sig"]) == ("review", {"done": 1, "total": 3}, None, None)
    assert r.save_decisions(tid, full(conn)) == 0
    c = card_of(r, tid)
    assert c["preview"] and re.fullmatch(r"[0-9a-f]{16}", c["preview_sig"])
    assert repo.row_counts(conn) == before


def test_added_mistake_not_valid_blocks_preview(env):
    go, conn, r = env
    out, _, _ = go(THREE)
    tid = out["thread_id"]
    d = full(conn)
    d["cards"]["n1"] = {
        "action": "add",
        "attempt_seq": 1,
        "step_idx": 99,
        "code": "notational.symbol",
        "description": "x",
    }
    assert r.save_decisions(tid, d) == 1
    c = card_of(r, tid)
    assert c["decided"] == {"done": 3, "total": 3} and c["preview"] is None  # the add is not valid yet


def test_reminder_words(env):
    go, conn, r = env
    out, _, _ = go(THREE)
    tid = out["thread_id"]
    want = {"kind": "grading", "thread_id": tid, "student_id": 1, "date": "2026-10-20"}
    assert reminder_of(r, tid) == want | {"state": "review", "words": "3 lỗi cần xem"}
    r.save_decisions(tid, {"cards": {"p1": {"action": "accept"}}})
    assert reminder_of(r, tid)["words"] == "2 lỗi cần xem"
    r.save_decisions(tid, full(conn))
    assert reminder_of(r, tid)["words"] == "chờ lưu kết quả"
    r.resume(tid)
    r.wait(tid)
    assert reminder_of(r, tid) == want | {"state": "preview", "words": "chờ lưu kết quả"}


def test_reminder_confirm_and_failed(env):
    go, conn, r = env
    out, _, _ = go(prob(None, "LANE1 $x = 1$") + prob(None, "LANE2 $x = 2$"), handlers=lane_handlers() | MATCH)
    assert reminder_of(r, out["thread_id"]) == {"kind": "grading", "thread_id": out["thread_id"], "student_id": 1,
                                                     "date": "2026-10-20", "state": "confirm",
                                                     "words": "cần xác nhận 2 bài"}  # fmt: skip
    bad, _, _ = go(THREE, name="b.tex", day="2026-10-25", handlers=lane_handlers(fail_03=lambda u: RuntimeError("x")))
    assert reminder_of(r, bad["thread_id"]) == {"kind": "grading", "thread_id": bad["thread_id"], "student_id": 1,
                                                      "date": "2026-10-25", "state": "failed",
                                                      "words": "chấm chưa xong"}  # fmt: skip


def test_no_mistakes_no_put_two_resumes_commit(env):
    go, conn, r = env
    out, _, _ = go(THREE, handlers=lane_handlers(mistakes=0))
    tid = out["thread_id"]
    c = card_of(r, tid)
    assert (c["stage"], c["decided"]) == ("review", {"done": 0, "total": 0}) and c["preview_sig"]
    assert reminder_of(r, tid)["words"] == "chờ lưu kết quả"
    row = approve(r, tid)  # nothing was ever saved: the gate takes {}
    assert (row["status"], row["error"]) == ("committed", None)
    assert repo.row_counts(conn)["attempt"] == 3 and repo.row_counts(conn)["mistake"] == 0
