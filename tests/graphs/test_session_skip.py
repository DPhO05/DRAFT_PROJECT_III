"""P6-T11: G1 skip decision at confirm_match (R22) and the read-only preview at gate_review (R23)."""

import re

from tests.bankfix import P1, P2
from tests.fakes import lane_handlers
from tests.graphs.g1 import THREE, approve, prob, status
from tests.graphs.test_review import full, kc_id
from tutor.agents import diagnoser, ingest
from tutor.db import repo
from tutor.graphs import session

MATCH = {"01": ingest.MatchResult(candidates=[ingest.Candidate(ref=P1[0], score=0.5)])}


def no_writes(preview: dict) -> dict:
    return {k: v for k, v in preview.items() if k != "writes"}


def lane_calls(fake) -> list[str]:
    return [c["user"] for c in fake.calls if c["agent"] in ("02", "03", "04")]


def test_skip_low_match(env):
    go, conn, r = env
    out, row, fake = go(prob(P1[0], "LANE1 $4x = 20$") + prob(None, "LANE2 $x = 2$"), handlers=lane_handlers() | MATCH)
    tid = out["thread_id"]
    assert row["node"] == "gate_confirm_match"
    assert r.save_decisions(tid, {"2": {"skip": True}}) == 0
    r.resume(tid)
    assert r.wait(tid)["node"] == "gate_review"
    st = r.state(tid)
    assert [lane["seq"] for lane in st["lanes"]] == [1] and st["ingest"]["attempts"][1]["skipped"] is True
    assert [(f["seq"], f["resolved"], f["decision"]) for f in st["ingest"]["flags"]] == [(2, True, {"skip": True})]
    assert fake.count == {"01": 1, "02": 1, "03": 1, "04": 1}
    assert all("LANE1" in u and "LANE2" not in u for u in lane_calls(fake))
    add = {"action": "add", "attempt_seq": 2, "step_idx": 1, "code": "other.unclear", "description": "x"}
    assert r.save_decisions(tid, {"cards": {"p1": {"action": "accept"}, "n1": add}}) == 1  # no mistake on a skipped one
    assert r.save_decisions(tid, {"cards": {"p1": {"action": "accept"}}}) == 0
    assert approve(r, tid)["status"] == "committed"
    assert conn.execute("SELECT seq FROM attempt").fetchall() == [(1,)]


def test_skip_no_rubric_not_reflagged(env):
    go, conn, r = env
    out, row, _ = go(prob(P1[0], "LANE1 $4x = 20$") + prob(P2[0], "LANE2 $m = -4$"))
    tid = out["thread_id"]
    assert row["node"] == "gate_confirm_match"
    assert r.save_decisions(tid, {"2": {"skip": True}}) == 0
    r.resume(tid)
    assert r.wait(tid)["node"] == "gate_review"
    st = r.state(tid)
    assert [lane["seq"] for lane in st["lanes"]] == [1]
    assert [f["type"] for f in st["ingest"]["flags"] if f["seq"] == 2] == ["no_rubric"]


def test_skip_all_commits_empty_session(env):
    go, conn, r = env
    out, row, fake = go(prob(P2[0], "LANE1 $m = -4$") + prob(None, "LANE2 $x = 2$"), handlers=lane_handlers() | MATCH)
    tid = out["thread_id"]
    assert row["node"] == "gate_confirm_match"
    assert r.save_decisions(tid, {"1": {"skip": True}, "2": {"skip": True}}) == 0
    r.resume(tid)
    assert r.wait(tid)["node"] == "gate_review"
    st = r.state(tid)
    assert st["proposals"] == [] and st.get("lanes", []) == []
    assert fake.count == {"01": 1, "02": 1}  # only 02's rubric draft, before the skip
    assert approve(r, tid)["status"] == "committed"
    assert status(conn, out["session_id"]) == "committed"
    assert repo.row_counts(conn)["attempt"] == 0 and r.state(tid)["preview"]["writes"]["attempt"] == 0


def test_preview_at_review_equals_node(env):
    go, conn, r = env
    out, _, _ = go(THREE)
    tid = out["thread_id"]
    r.save_decisions(tid, full(conn))
    before = repo.row_counts(conn)
    prof, prior, pv = session.preview_of(r._paths_for_test, r.state(tid), full(conn))
    assert repo.row_counts(conn) == before
    r.resume(tid)
    assert r.wait(tid)["node"] == "gate_confirm_commit"
    st = r.state(tid)
    assert (prof, prior) == (st["profile"], st["profile_prior"])
    assert no_writes(pv) == no_writes(st["preview"])
    assert session.sig(pv) == session.sig(st["preview"]) == session.sig(no_writes(pv))
    assert re.fullmatch(r"[0-9a-f]{16}", session.sig(pv))


def test_preview_has_n_mistakes(env):
    go, conn, r = env
    kc = kc_id(conn)

    def g03(user, system):
        m = diagnoser.MistakeOut(step_idx=1, code="other.unclear", kc_id=kc, description="lỗi", evidence_latex="x",
                                 confidence=0.5)  # fmt: skip
        return diagnoser.DiagnosisOut(corrected_latex="", mistakes=[m])

    out, _, _ = go(THREE, handlers=lane_handlers() | {"03": g03})
    tid = out["thread_id"]
    cards = {"p1": {"action": "accept"}, "p2": {"action": "reject"}, "p3": {"action": "accept"},
             "n1": {"action": "add", "attempt_seq": 1, "step_idx": 1, "code": "notational.symbol", "kc_id": kc,
                    "description": "sót"},
             "n2": {"action": "add", "attempt_seq": 2, "step_idx": 1, "code": "notational.symbol",
                    "description": "không KC"}}  # fmt: skip
    assert r.save_decisions(tid, {"cards": cards}) == 0
    pv = session.preview_of(r._paths_for_test, r.state(tid), {"cards": cards})[2]
    assert [(k["kc"], k["n_mistakes"]) for k in pv["kcs"]] == [("Chuyển vế", 3)]
