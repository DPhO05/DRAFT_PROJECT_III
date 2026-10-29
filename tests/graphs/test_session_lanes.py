"""P2-T05: G1 runs one 02 → 03 → 04 lane per problem up to the review gate; confirm_match loop."""

import pytest

from tests.bankfix import P1, P2
from tests.fakes import lane_handlers
from tests.graphs.g1 import THREE, prob, status
from tutor.agents import ingest
from tutor.db import repo
from tutor.graphs import runner as rmod


def test_three_problems_three_lanes_stop_at_review(env):
    go, conn, r = env
    before = repo.row_counts(conn)
    out, row, fake = go(THREE)
    assert (row["status"], row["node"], row["error"]) == ("awaiting_review", "gate_review", None)
    assert fake.count == {"02": 3, "03": 3, "04": 3}
    st = r.state(out["thread_id"])
    assert sorted(lane["seq"] for lane in st["lanes"]) == [1, 2, 3]
    assert [(p["pid"], p["attempt_seq"]) for p in st["proposals"]] == [("p1", 1), ("p2", 2), ("p3", 3)]
    assert st["proposals"][0]["verifier"]["verdict"] == "agree"
    assert status(conn, out["session_id"]) == "awaiting_review"
    after = repo.row_counts(conn)
    assert {k: after[k] - before[k] for k in after if after[k] != before[k]} == {"session": 1}
    log = (r._paths_for_test.logs / "llm.jsonl").read_text(encoding="utf-8")
    assert log.count(f'"thread_id": "{out["thread_id"]}"') == 9 and "Nguyễn" not in log


def test_failure_in_03_lane_2_reruns_only_its_03_and_04(env):
    go, conn, r = env
    failed = []

    def boom(user):
        if "LANE2" in user and not failed:
            failed.append(1)
            return RuntimeError("gài lỗi 03 lane 2")
        return None

    out, row, fake = go(THREE, handlers=lane_handlers(fail_03=boom))
    assert row["status"] == "failed" and "gài lỗi 03 lane 2" in row["error"]
    assert status(conn, out["session_id"]) == "failed"
    first = dict(fake.count)
    r.resume(out["thread_id"])
    row = r.wait(out["thread_id"])
    assert (row["status"], row["node"]) == ("awaiting_review", "gate_review")
    assert {k: fake.count[k] - first.get(k, 0) for k in fake.count} == {"02": 0, "03": 1, "04": 1}
    assert first == {"02": 3, "03": 3, "04": 2}
    assert len(r.state(out["thread_id"])["lanes"]) == 3


def test_low_match_blocks_until_problem_chosen_then_lanes_run(env):
    go, conn, r = env
    h = lane_handlers() | {"01": ingest.MatchResult(candidates=[ingest.Candidate(ref=P1[0], score=0.5)])}
    out, row, fake = go(prob(None, "LANE1 $4x = 20$"), handlers=h)
    tid = out["thread_id"]
    assert row["node"] == "gate_confirm_match" and fake.count == {"01": 1}
    with pytest.raises(rmod.UndecidedItems):
        r.resume(tid)
    assert r.save_decisions(tid, {"1": {"problem_ref": "NO-SUCH"}}) == 1
    assert r.save_decisions(tid, {"1": {"problem_ref": P1[0], "note": "đúng bài"}}) == 0
    r.resume(tid)
    row = r.wait(tid)
    assert (row["status"], row["node"]) == ("awaiting_review", "gate_review")
    st = r.state(tid)
    assert st["ingest"]["attempts"][0]["ref"] == P1[0] and all(f["resolved"] for f in st["ingest"]["flags"])
    assert fake.count == {"01": 1, "02": 1, "03": 1, "04": 1}


def test_no_rubric_gets_02_draft_and_teacher_rubric_is_used(env):
    go, conn, r = env
    out, row, fake = go(prob(P2[0], "LANE1 $m = -4$"))
    tid = out["thread_id"]
    assert row["node"] == "gate_confirm_match"
    st = r.state(tid)
    assert st["rubric_drafts"]["1"]["max_score"] == 2 and fake.count == {"02": 1}
    assert r.save_decisions(tid, {"1": {"rubric_items": []}}) == 1
    items = [{"item_id": "r1", "text": "Thay x = 3", "points": 1}, {"item_id": "r2", "text": "m = -4", "points": 3}]
    assert r.save_decisions(tid, {"1": {"rubric_items": items}}) == 0
    r.resume(tid)
    assert r.wait(tid)["node"] == "gate_review"
    st = r.state(tid)
    assert st["approved_rubrics"]["1"] == {"items": items, "max_score": 4}
    assert st["lanes"][0]["grade"]["max_score"] == 4 and st["lanes"][0]["grade"]["score"] == 4
    assert repo.row_counts(conn)["rubric"] == 2  # nothing written before commit ② (C-16)


def test_chosen_problem_without_rubric_stops_again_for_rubric(env):
    go, conn, r = env
    h = lane_handlers() | {"01": ingest.MatchResult(candidates=[ingest.Candidate(ref=P2[0], score=0.5)])}
    out, row, fake = go(prob(None, "LANE1 $m = -4$"), handlers=h)
    tid = out["thread_id"]
    r.save_decisions(tid, {"1": {"problem_ref": P2[0]}})
    r.resume(tid)
    row = r.wait(tid)
    assert (row["status"], row["node"]) == ("awaiting_review", "gate_confirm_match")
    flags = r.state(tid)["ingest"]["flags"]
    assert [(f["type"], f["resolved"]) for f in flags] == [("low_match", True), ("no_rubric", False)]
    assert r.save_decisions(tid, {"1": {"problem_ref": P2[0]}}) == 1
    r.save_decisions(tid, {"1": {"rubric_items": [{"item_id": "r1", "text": "m = -4", "points": 1}]}})
    r.resume(tid)
    assert r.wait(tid)["node"] == "gate_review" and fake.count["01"] == 1


def test_lane_keeps_the_5_mistakes_03_saw(env):
    go, conn, r = env
    out, _, _ = go(THREE)
    assert [lane["diagnosis"]["context"] for lane in r.state(out["thread_id"])["lanes"]] == [[], [], []]


@pytest.mark.parametrize(
    "bad",
    [
        {"1": "x"},
        {"1": {"rubric_items": "x"}},
        {"1": {"rubric_items": ["x"]}},
        {"1": {"rubric_items": [{"item_id": "r1", "text": "t", "points": "2"}]}},
        {"1": {"rubric_items": [{"item_id": "r1", "text": "t", "points": True}]}},
        {"1": {"rubric_items": [{"text": "t", "points": 1}]}},
        {"1": {"rubric_items": [{"item_id": "r1", "text": "a", "points": 1}] * 2}},
    ],
)
def test_malformed_decisions_count_as_pending(env, bad):
    go, conn, r = env
    out, row, _ = go(prob(P2[0], "LANE1 $m = -4$"))
    assert r.save_decisions(out["thread_id"], bad) == 1
