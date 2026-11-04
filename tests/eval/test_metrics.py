"""P2-T10: eval metrics on hand-computed examples."""

import pytest

from tests.eval import metrics


def mk(step, code, prop=()):
    return {"step_idx": step, "code": code, "propagates_to": list(prop)}


def pr(step, code):
    return {"step_idx": step, "code": code}


def test_kappa_matches_hand_computed_3x3():
    # teacher (rows) × LLM (cols), n = 10
    #          A  B  C | row
    #     A    3  1  0 |  4
    #     B    0  3  1 |  4
    #     C    1  0  1 |  2
    #   col    4  4  2
    # po = (3+3+1)/10 = 0.7 ; pe = (4·4 + 4·4 + 2·2)/100 = 0.36 ; κ = (0.7−0.36)/(1−0.36) = 0.34/0.64 = 0.53125
    pairs = [("A", "A")] * 3 + [("A", "B")] + [("B", "B")] * 3 + [("B", "C")] + [("C", "C"), ("C", "A")]
    assert metrics.cohen_kappa(pairs) == pytest.approx(0.53125)


def test_kappa_undefined_without_pairs_or_with_one_shared_category():
    assert metrics.cohen_kappa([]) is None
    assert metrics.cohen_kappa([("A", "A"), ("A", "A")]) is None  # pe = 1
    assert metrics.cohen_kappa([("A", "A"), ("B", "B")]) == 1


def test_first_wrong_step():
    assert metrics.first_wrong_step([5, 2], [2, 7])
    assert not metrics.first_wrong_step([5], [6])
    assert metrics.first_wrong_step([], [])
    assert not metrics.first_wrong_step([], [1])
    assert not metrics.first_wrong_step([3], [])


def test_score_hand_example():
    problems = [
        # P1: right first step; step 6 flagged as propagation of 5 -> not an addition
        {"labels": [mk(5, "notational.operator_swap", [6, 7])],
         "proposals": [pr(5, "notational.operator_swap"), pr(6, "computational.propagated")]},
        # P2: clean, LLM invents step 2
        {"labels": [], "proposals": [pr(2, "other.unclear")]},
        # P3: misses step 1, finds step 4 with another code
        {"labels": [mk(1, "presentation.units"), mk(4, "conceptual.wrong_fact")],
         "proposals": [pr(4, "computational.final_answer")]},
        # P4: clean, nothing proposed
        {"labels": [], "proposals": []},
    ]  # fmt: skip
    s = metrics.score(problems)
    assert s["first_wrong_step_acc"] == 2 / 4  # P1, P4
    assert s["recall"] == 2 / 3  # label steps {5}, {1, 4}: found 5, 4
    assert s["precision"] == 3 / 4  # flagged {5, 6}, {2}, {4}: 2 is wrong
    assert s["drop_rate"] == 1 / 3  # P3 step 1
    assert s["add_rate"] == 1 / 4  # P2 step 2
    # pairs (op_swap, op_swap), (wrong_fact, final_answer): po = 0.5, pe = 1·1/4 = 0.25, κ = 0.25/0.75
    assert s["kappa"] == pytest.approx(1 / 3)
    assert (s["n_problems"], s["n_labels"], s["n_proposals"], s["n_pairs"]) == (4, 3, 4, 2)


def test_score_empty_rates_are_none():
    s = metrics.score([{"labels": [], "proposals": []}])
    assert s["first_wrong_step_acc"] == 1
    assert (s["precision"], s["recall"], s["drop_rate"], s["add_rate"], s["kappa"]) == (None,) * 5


def test_stability_items_changed_and_pass_k():
    ok = {"labels": [mk(2, "a")], "proposals": [pr(2, "a")]}
    bad = {"labels": [mk(2, "a")], "proposals": [pr(3, "a")]}
    runs = [
        {"s01#1": ok | {"items": {"r1": True, "r2": True}}, "s01#2": ok | {"items": {"r1": True}},
         "s02#1": ok | {"items": {"r1": True}}},
        {"s01#1": ok | {"items": {"r1": True, "r2": True}}, "s01#2": ok | {"items": {"r1": False}},
         "s02#1": ok | {"items": {"r1": True}}},
        {"s01#1": ok | {"items": {"r1": True, "r2": True}}, "s01#2": bad | {"items": {"r1": True}}},  # s02 failed
    ]  # fmt: skip
    s = metrics.stability(runs)
    # items: s01#1 r1, r2 stable; s01#2 r1 flips; s02#1 r1 missing in run 3 -> 2 of 4 changed
    assert s == {"runs": 3, "n_items": 4, "items_changed_pct": 50.0, "n_problems": 3, "pass_k": 1 / 3}


def ans(expect, tools, forbid=(), **kw):
    return {"id": "q", "expect": list(expect), "forbid": list(forbid), "tools": list(tools),
            "tool_errors": 0, "unverified": 0, "stopped": None, "text": "Xong."} | kw  # fmt: skip


def test_passed_00_needs_expected_tools_in_order():
    assert metrics.passed_00(
        ans(["rank_problems", "propose_worksheet"], ["rank_problems", "find_problems", "propose_worksheet"])
    )
    assert not metrics.passed_00(ans(["rank_problems", "propose_worksheet"], ["propose_worksheet", "rank_problems"]))
    assert not metrics.passed_00(ans(["student_profile"], []))


def test_passed_00_fails_on_forbidden_errors_numbers_and_stop():
    assert metrics.passed_00(ans([], [], ["*"]))
    assert not metrics.passed_00(ans([], ["list_students"], ["*"]))
    assert not metrics.passed_00(ans(["list_students"], ["list_students", "student_profile"], ["student_profile"]))
    assert not metrics.passed_00(ans(["list_students"], ["list_students"], tool_errors=1))
    assert not metrics.passed_00(ans(["list_students"], ["list_students"], unverified=1))
    assert not metrics.passed_00(ans(["list_students"], ["list_students"], stopped="max_tool_turns"))
    assert not metrics.passed_00(ans(["list_students"], ["list_students"], text=""))
    assert not metrics.passed_00(ans(["list_students"], ["list_students"], text=" \n"))


def test_score_00():
    s = metrics.score_00([ans(["list_students"], ["list_students"]), ans(["list_students"], [], unverified=2)])
    assert s == {"n_questions": 2, "tools_ok": 0.5, "unverified_pct": 50.0, "passed": 0.5}


def test_pass_k_missing_counts_as_failed():
    assert metrics.pass_k([{"a": True, "b": True}, {"a": True}]) == 0.5
    assert metrics.pass_k([]) is None


def rep(kind, n, statuses):
    return {"key": "k", "period_kind": kind, "n_sentences": n, "audit": [{"status": s} for s in statuses]}


def test_passed_09_needs_no_drop_and_the_sentence_range():
    assert metrics.passed_09(rep("day", 3, ["ok", "ok", "rewritten"]))
    assert not metrics.passed_09(rep("day", 2, ["ok", "ok"]))
    assert not metrics.passed_09(rep("day", 5, ["ok"] * 5))
    assert metrics.passed_09(rep("week", 5, ["ok"] * 5)) and metrics.passed_09(rep("month", 8, ["ok"] * 8))
    assert not metrics.passed_09(rep("month", 5, ["ok"] * 5 + ["dropped"]))


def test_score_09():
    s = metrics.score_09([rep("day", 3, ["ok", "rewritten", "ok"]), rep("week", 4, ["ok"] * 4 + ["dropped"])])
    assert s == {"n_reports": 2, "draft_flagged_pct": 25.0, "dropped_pct": 12.5, "passed": 0.5}
