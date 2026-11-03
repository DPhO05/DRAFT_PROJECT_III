"""P2-T01, P2-T02: agent 02 Grader (grade by rubric, draft a rubric)."""

from pathlib import Path

import pytest

from tests.fakes import FakeLLM
from tutor import llm
from tutor.agents import CallContext
from tutor.agents.a02_grader import grader
from tutor.services import latex

CTX = CallContext(graph="G1", thread_id="g1-hs01-20261020", session_id=1, student_code="HS-01")
PROBLEM = {"statement_latex": "Giải $4x - 20 = 0$.", "solution_latex": "$4x = 20$\n\n$x = 5$"}
RUBRIC = {"version": 2, "max_score": 3, "items": [
    {"item_id": "r1", "text": "Chuyển vế đúng", "points": 1},
    {"item_id": "r2", "text": "Đáp số x = 5", "points": 2},
]}  # fmt: skip
STEPS = [{"idx": 1, "latex": "$4x = 20$"}, {"idx": 2, "latex": "$x = 4$"}]


def out(items, score, alt=False):
    return grader.GradeOut(items=[grader.GradeItem(**i) for i in items], score=score, alt_method=alt)


@pytest.fixture
def fake(tmp_path):
    llm.configure(tmp_path / "llm.jsonl", {})

    def use(handler):
        f = FakeLLM({"02": handler})
        llm.set_backend(f)
        return f

    yield use
    llm.set_backend(None)


def flags(g):
    return [f.type for f in g.flags]


def test_clean_grade_has_no_flags_and_rubric_order(fake):
    fake(out([{"item_id": "r2", "passed": False}, {"item_id": "r1", "passed": True, "evidence_latex": "4x = 20"}], 1))
    g = grader.grade(STEPS, PROBLEM, RUBRIC, ctx=CTX)
    assert [(i.item_id, i.passed) for i in g.items] == [("r1", True), ("r2", False)]
    assert (g.score, g.max_score, g.rubric_version, g.flags) == (1, 3, 2, [])


def test_score_not_sum_of_items_is_flagged_and_recomputed(fake):
    fake(out([{"item_id": "r1", "passed": True, "evidence_latex": "4x = 20"}, {"item_id": "r2", "passed": False}], 3))
    g = grader.grade(STEPS, PROBLEM, RUBRIC, ctx=CTX)
    assert flags(g) == ["score_mismatch"] and g.score == 1


def test_passed_item_without_evidence_is_flagged(fake):
    fake(out([{"item_id": "r1", "passed": True, "evidence_latex": " "}, {"item_id": "r2", "passed": False}], 1))
    assert flags(grader.grade(STEPS, PROBLEM, RUBRIC, ctx=CTX)) == ["no_evidence"]


def test_alt_method_goes_to_review_queue(fake):
    fake(out([{"item_id": "r1", "passed": False}, {"item_id": "r2", "passed": False}], 0, alt=True))
    g = grader.grade(STEPS, PROBLEM, RUBRIC, ctx=CTX)
    assert g.alt_method and flags(g) == ["alt_method"]


def test_missing_item_counts_as_failed_and_unknown_item_dropped(fake):
    fake(out([{"item_id": "r1", "passed": True, "evidence_latex": "4x"}, {"item_id": "zz", "passed": True}], 1))
    g = grader.grade(STEPS, PROBLEM, RUBRIC, ctx=CTX)
    assert [(i.item_id, i.passed) for i in g.items] == [("r1", True), ("r2", False)]
    assert flags(g) == ["missing_item"]


def test_prompt_rubric_and_solution_outside_fixed_part_work_framed(fake):
    f = fake(out([{"item_id": "r1", "passed": False}, {"item_id": "r2", "passed": False}], 0))
    grader.grade(STEPS, PROBLEM, RUBRIC, ctx=CTX)
    [c] = f.calls
    system, user = "\n".join(c["system"]), c["user"]
    assert "Chuyển vế đúng" not in system and "Ví dụ" in system
    head, work = user.split(llm.OPEN)
    assert "[r2] (2 điểm) Đáp số x = 5" in head and "$x = 5$" in head
    assert "[1] $4x = 20$" in work and "[2] $x = 4$" in work


def test_schema_error_twice_gives_flag_not_crash(fake):
    fake(None)
    g = grader.grade(STEPS, PROBLEM, RUBRIC, ctx=CTX)
    assert flags(g) == ["schema"] and g.score == 0 and not any(i.passed for i in g.items)


BANK = Path(__file__).resolve().parents[2] / "data/dummy/bank"


def test_generate_rubric_on_10_dummy_problems(fake):
    def by_paragraph(user, system):
        sol = user.split("Lời giải mẫu:")[1]
        paras = [p for p in sol.split("\n\n") if p.strip()]
        return grader.RubricDraftOut(items=[
            grader.RubricItem(item_id=f"r{i}", text=p.strip()[:40], points=1 + i % 2) for i, p in enumerate(paras, 1)
        ])  # fmt: skip

    fake(by_paragraph)
    probs = []
    for f in sorted(BANK.glob("*.tex")):
        tex = f.read_text(encoding="utf-8")
        p = latex.split_problems(tex)[0]
        s = p.solutions[0]
        probs.append({"statement_latex": p.statement, "solution_latex": tex[s.pos : s.pos_end]})
    assert len(probs) == 10
    for p in probs:
        d = grader.generate_rubric(p, ctx=CTX)
        assert len(d["items"]) >= 1 and d["max_score"] == sum(i["points"] for i in d["items"])


def test_generate_rubric_schema_error_returns_none(fake):
    fake(None)
    assert grader.generate_rubric(PROBLEM, ctx=CTX) is None
