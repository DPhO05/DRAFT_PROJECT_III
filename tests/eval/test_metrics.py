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


def test_args_ok_compares_the_first_call_of_each_tool():
    calls = [{"name": "rank_problems", "args": {"code": "HS-01", "n": 3}},
             {"name": "find_problems", "args": {"refs": ["9ds-bpt-001", "9DS-BPT-004"]}}]  # fmt: skip
    ok = ans([], [], calls=calls, expect_args={"rank_problems": {"code": "HS-01", "n": 3},
                                               "find_problems": {"refs": ["9DS-BPT-004", "9DS-BPT-001"]}})  # fmt: skip
    assert metrics.args_ok(ok)
    assert not metrics.args_ok(ok | {"expect_args": {"rank_problems": {"n": 6}}})
    assert not metrics.args_ok(ok | {"expect_args": {"student_profile": {"code": "HS-01"}}})  # never called
    assert not metrics.args_ok(ok | {"expect_args": {"find_problems": {"refs": ["9DS-BPT-001"]}}})  # a list is a set
    assert metrics.args_ok(
        ans(
            [],
            [],
            calls=[{"name": "search_problems", "args": {"text": "Bất phương trình bậc nhất"}}],
            expect_args={"search_problems": {"text": "bất phương trình"}},
        )
    )  # a string: contained
    assert metrics.args_ok(ans([], []))  # nothing expected


def test_args_fit_checks_required_unknown_and_enum():
    defs = [{"name": "t", "input_schema": {"properties": {"a": {"type": "string", "enum": ["x", "y"]}, "b": {}},
                                           "required": ["a"]}}]  # fmt: skip
    assert metrics.args_fit({"name": "t", "args": {"a": "x"}}, defs)
    assert not metrics.args_fit({"name": "t", "args": {"b": 1}}, defs)  # required key missing
    assert not metrics.args_fit({"name": "t", "args": {"a": "x", "c": 1}}, defs)  # unknown key
    assert not metrics.args_fit({"name": "t", "args": {"a": "z"}}, defs)  # not in the enum
    assert not metrics.args_fit({"name": "nope", "args": {}}, defs)


def test_passed_00_fails_on_a_leak_a_shown_code_a_save_claim_or_a_bad_call():
    good = ans(["list_students"], ["list_students"])
    assert metrics.passed_00(good)
    assert not metrics.passed_00(good | {"leaks": 1})
    assert not metrics.passed_00(good | {"codes_shown": 1})
    assert not metrics.passed_00(good | {"schema_errors": 1})
    assert not metrics.passed_00(good | {"text": "Mình đã lưu kết quả rồi."})


def test_score_00():
    s = metrics.score_00([ans(["list_students"], ["list_students"]), ans(["list_students"], [], unverified=2)])
    assert s == {
        "n_questions": 2,
        "tools_ok": 0.5,
        "unverified_pct": 50.0,
        "args_ok": 1.0,
        "passed": 0.5,
        "approval_ok": None,
    }


def test_score_00_approval_ok_counts_only_answers_with_an_approval():
    asked = ans(["start_grading"], ["start_grading"], approval={"decision": "approve"}, expect_approval=True,
                approvals=[{"name": "start_grading"}])  # fmt: skip
    s = metrics.score_00([asked, asked | {"approvals": []}, ans([], [])])
    assert s["approval_ok"] == 0.5 and s["passed"] == 2 / 3


def test_rules_ok_checks_starts_approval_limits_and_text():
    a = ans([], [], starts=[["start_grading", 1, "a.tex", "2026-10-21"]], approvals=[{"name": "start_grading"}],
            calls=[{"name": "start_grading", "args": {}}], model_calls=2)  # fmt: skip
    assert metrics.rules_ok(
        a | {"expect_starts": [["start_grading", 1, "a.tex", "2026-10-21"]], "expect_approval": True}
    )
    assert not metrics.rules_ok(a | {"expect_starts": []})
    assert not metrics.rules_ok(a)  # an approval nobody expected
    assert not metrics.rules_ok(a | {"expect_approval": True, "max_calls": {"start_grading": 0}})
    assert not metrics.rules_ok(a | {"expect_approval": True, "max_model_calls": 1})
    assert not metrics.rules_ok(a | {"expect_approval": True, "expect_text": "khác"})
    assert metrics.rules_ok(a | {"expect_approval": True, "expect_any": ["xong", "???"]})  # ans() text is "Xong."
    assert not metrics.rules_ok(a | {"expect_approval": True, "expect_any": ["?"]})


def test_passed_00_card_only_and_allowed_tool_error():
    assert metrics.passed_00(ans(["find_problems"], ["find_problems"], text="", cards=1, card_only=True))
    assert not metrics.passed_00(ans(["find_problems"], ["find_problems"], text="", cards=1))
    assert metrics.passed_00(ans(["start_grading"], ["start_grading"], tool_errors=1, allow_tool_error=True))


def test_pass_k_missing_counts_as_failed():
    assert metrics.pass_k([{"a": True, "b": True}, {"a": True}]) == 0.5
    assert metrics.pass_k([]) is None


def rep(kind, n, statuses):
    return {"key": "k", "period_kind": kind, "n_sentences": n, "audit": [{"status": s} for s in statuses]}


def test_passed_09_needs_no_drop_and_the_sentence_range():
    assert metrics.passed_09(rep("day", 2, ["ok", "ok"])) and metrics.passed_09(
        rep("day", 3, ["ok", "ok", "rewritten"])
    )
    assert not metrics.passed_09(rep("day", 1, ["ok"])) and not metrics.passed_09(rep("day", 4, ["ok"] * 4))
    assert metrics.passed_09(rep("week", 3, ["ok"] * 3)) and metrics.passed_09(rep("month", 4, ["ok"] * 4))
    assert metrics.passed_09(rep("month", 5, ["ok"] * 5)) and not metrics.passed_09(rep("month", 6, ["ok"] * 6))
    assert not metrics.passed_09(rep("month", 5, ["ok"] * 5 + ["dropped"]))


def test_score_09():
    s = metrics.score_09([rep("day", 3, ["ok", "rewritten", "ok"]), rep("week", 4, ["ok"] * 4 + ["dropped"])])
    assert (s["n_reports"], s["draft_flagged_pct"], s["dropped_pct"], s["passed"]) == (2, 25.0, 12.5, 0.5)


def test_text_ok_09_refuses_ids_codes_refs_and_percent():
    ok = {"sentences": ["Em làm 4 trong 6 ý.", "Em còn nhầm dấu khi chuyển vế."]}
    assert metrics.text_ok_09(ok) and metrics.text_ok_09({})
    for bad in ("Theo F02, em tiến bộ.", "HS-01 làm tốt.", "Em sai bài 9DS-BPT-001.", "Em đạt 50% số ý."):
        assert not metrics.text_ok_09({"sentences": [bad]}), bad


def test_passed_09_needs_clean_text_no_leak_and_at_most_two_calls():
    good = rep("day", 2, ["ok", "ok"]) | {"sentences": ["a", "b"], "model_calls": 2, "leaks": 0}
    assert metrics.passed_09(good)
    assert not metrics.passed_09(good | {"model_calls": 3})
    assert not metrics.passed_09(good | {"leaks": 1})
    assert not metrics.passed_09(good | {"sentences": ["Em đạt 50%.", "b"]})


def test_score_09_counts_flags_by_kind():
    r = rep("day", 2, ["ok", "dropped", "rewritten"])
    r["audit"][1]["flag"], r["audit"][2]["flag"] = "number", "tone"
    assert metrics.score_09([r])["flags"] == {"number": 1, "no_fact": 0, "tone": 1, "percent": 0, "empty": 0}


def row(agent, ms, usd, result="ok"):
    return {"agent": agent, "ms": ms, "cost_usd": usd, "result": result, "input_tokens": 100, "output_tokens": 20,
            "cache_read_tokens": 80, "cache_write_tokens": 0}  # fmt: skip


def test_usage_sums_tokens_cost_and_latency():
    u = metrics.usage([row("02", 100, 0.1), row("02", 200, 0.2), row("03", 300, 0.3, "retry"),
                       row("04", 400, 0.4, "schema_error")])  # fmt: skip
    assert (u["logged"], u["usd"], u["tokens_in"], u["tokens_out"]) == (4, 1.0, 720, 80)
    assert (u["ms_p50"], u["ms_p95"], u["error_rate"]) == (200, 400, 0.5)
    assert u["by_agent"] == {"02": {"calls": 2, "usd": 0.3}, "03": {"calls": 1, "usd": 0.3},
                             "04": {"calls": 1, "usd": 0.4}}  # fmt: skip


def test_usage_of_no_rows():
    u = metrics.usage([])
    assert (u["logged"], u["usd"], u["ms_p50"], u["ms_p95"], u["error_rate"], u["by_agent"]) == (
        0,
        0,
        None,
        None,
        None,
        {},
    )


def test_tally_counts_trials_and_tasks():
    runs = [{f"q{i}": True for i in range(8)} for _ in range(3)]
    runs[2]["q3"] = False
    t = metrics.tally(runs)
    assert (t["trials_passed"], t["trials"], t["tasks_passed"], t["tasks"]) == (23, 24, 7, 8)
    assert (t["success"], t["pass_k"]) == (23 / 24, 7 / 8) and t["task_pass"]["q3"] is False
    assert metrics.tally([{"a": True, "b": True}, {"a": True}])["pass_k"] == 0.5  # missing = failed


def test_score_01_hit_mrr_and_flag_precision():
    def a(expect, cands, low):
        return {"id": "x", "expect_ref": expect, "ref": cands[0] if cands and not low else None,
                "candidates": [{"ref": c, "score": 0.9} for c in cands], "low_match": low, "model_calls": 1,
                "bad_candidates": 0}  # fmt: skip

    s = metrics.score_01([a("A", ["A"], False), a("B", ["X", "B"], False), a("C", ["X", "Y", "Z"], True),
                          a(None, [], True)])  # fmt: skip
    assert (s["n_tasks"], s["hit_at_1"], s["hit_at_3"]) == (4, 1 / 3, 2 / 3)
    assert s["mrr"] == (1 + 1 / 2 + 0) / 3 and s["low_match_precision"] == 1 / 2 and s["passed"] == 2 / 4


def test_score_04_accuracy_confusion_and_disagree_recall():
    def a(expect, verdict, code=None, want=None):
        return {"id": "x", "expect": expect, "verdict": verdict, "suggested_code": code, "expect_code": want,
                "model_calls": 1}  # fmt: skip

    s = metrics.score_04([a("agree", "agree"), a("disagree", "agree"), a("disagree", "disagree"),
                          a("wrong_code", "wrong_code", "x.a", "x.b"), a("agree", None)])  # fmt: skip
    assert (s["n_tasks"], s["accuracy"], s["recall_disagree"], s["empty"]) == (5, 3 / 5, 1 / 2, 1)
    assert s["confusion"]["disagree"] == {"agree": 1, "disagree": 1, "wrong_code": 0, "none": 0}
    assert s["passed"] == 2 / 5  # the wrong_code answer suggests the wrong code
