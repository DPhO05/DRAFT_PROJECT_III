"""P2-T04: agent 04 Verifier + review queue order."""

import pytest

from tests.fakes import FakeLLM
from tutor import llm
from tutor.agents import CallContext
from tutor.agents.a03_diagnoser import diagnoser
from tutor.agents.a04_verifier import verifier

CTX = CallContext(graph="G1", thread_id="g1-hs01-20261020", session_id=1, student_code="HS-01")
PROBLEM = {"statement_latex": "Giải $4x - 20 = 0$.", "solution_latex": "$4x = 20$\n\n$x = 5$", "kcs": []}
STEPS = [{"idx": 1, "latex": "$4x = 20$"}, {"idx": 2, "latex": "$x = 4$"}]
CODES = [{"code": "computational.intermediate_calc", "category": "computational", "description": "Tính sai",
          "example": None}, {"code": "notational.symbol", "category": "notational", "description": "Ký hiệu",
          "example": None}]  # fmt: skip
MISTAKE = {"step_idx": 2, "code": "computational.intermediate_calc", "kc_id": None, "description": "Chia sai",
           "evidence_latex": "x = 4", "confidence": 0.42}  # fmt: skip


@pytest.fixture
def fake(tmp_path):
    llm.configure(tmp_path / "llm.jsonl", {})

    def use(handler):
        f = FakeLLM({"04": handler})
        llm.set_backend(f)
        return f

    yield use
    llm.set_backend(None)


def test_prompt_sees_only_the_conclusion_of_03(fake):
    f = fake(verifier.VerdictOut(verdict="agree", reason="đúng"))
    v = verifier.run(MISTAKE | {"corrected_latex": "BẢN SỬA CỦA 03"}, STEPS, PROBLEM, codes=CODES, ctx=CTX)
    assert v.verdict == "agree"
    [c] = f.calls
    sent = "\n".join(c["system"]) + c["user"]
    assert diagnoser.INSTRUCTIONS not in sent and "BẢN SỬA CỦA 03" not in sent and "0.42" not in sent
    assert "bước 2" in sent and "computational.intermediate_calc" in sent and "Chia sai" in sent


def test_suggested_code_must_be_active(fake):
    fake(verifier.VerdictOut(verdict="wrong_code", reason="r", suggested_code="presentation.format"))
    v = verifier.run(MISTAKE, STEPS, PROBLEM, codes=CODES, ctx=CTX)
    assert (v.verdict, v.suggested_code) == ("wrong_code", None)
    fake(verifier.VerdictOut(verdict="wrong_code", reason="r", suggested_code="notational.symbol"))
    assert verifier.run(MISTAKE, STEPS, PROBLEM, codes=CODES, ctx=CTX).suggested_code == "notational.symbol"


def test_schema_error_gives_no_verdict(fake):
    fake(None)
    v = verifier.run(MISTAKE, STEPS, PROBLEM, codes=CODES, ctx=CTX)
    assert v.verdict is None and "sai schema" in v.reason


def card(pid, seq, step, conf, verdict):
    return {"pid": pid, "attempt_seq": seq, "step_idx": step, "confidence": conf, "verifier": {"verdict": verdict}}


def test_queue_order_disputed_then_low_confidence_then_rest():
    # the 6 showcase cards of contract §8.3, shuffled
    cards = [
        card("p5", 3, 4, 0.88, "agree"), card("p3", 2, 6, 0.55, "agree"), card("p6", 3, 5, 0.64, "agree"),
        card("p2", 3, 2, 0.47, "disagree"), card("p4", 1, 4, 0.81, "agree"), card("p1", 1, 3, 0.58, "wrong_code"),
    ]  # fmt: skip
    assert [c["pid"] for c in verifier.order_queue(cards, 0.6)] == ["p1", "p2", "p3", "p4", "p5", "p6"]


def test_queue_missing_verdict_counts_as_disputed():
    cards = [card("a", 1, 1, 0.3, "agree"), card("b", 2, 1, 0.9, None)]
    assert [c["pid"] for c in verifier.order_queue(cards, 0.6)] == ["b", "a"]
