"""P2-T03: agent 03 Diagnoser."""

import json

import pytest

from tests.fakes import FakeLLM
from tutor import llm
from tutor.agents import CallContext, diagnoser

CTX = CallContext(graph="G1", thread_id="g1-hs01-20261020", session_id=1, student_code="HS-01")
PROBLEM = {"statement_latex": "Giải $4x - 20 = 0$.", "solution_latex": "$4x = 20$\n\n$x = 5$",
           "kcs": [{"id": 7, "code": "8DS-PT1-01", "name": "Chuyển vế"}]}  # fmt: skip
STEPS = [{"idx": 1, "latex": "$4x = 20$"}, {"idx": 2, "latex": "$x = 4$"}]
CODES = [
    {"code": "computational.intermediate_calc", "category": "computational", "description": "Tính sai",
     "example": "$3 \\cdot 4 = 7$"},
    {"code": "other.unclear", "category": "other", "description": "Không rõ", "example": None},
]  # fmt: skip
HISTORY = [{"code": "notational.symbol", "kc_id": 7, "description": "Viết sai dấu bằng", "held_on": "2026-10-13"}]


def mistake(**kw):
    m = {"step_idx": 2, "code": "computational.intermediate_calc", "kc_id": 7, "description": "Chia sai",
         "evidence_latex": "x = 4", "confidence": 0.9} | kw  # fmt: skip
    return diagnoser.MistakeOut(**m)


@pytest.fixture
def fake(tmp_path):
    log = tmp_path / "llm.jsonl"
    llm.configure(log, {})

    def use(handler):
        f = FakeLLM({"03": handler})
        llm.set_backend(f)
        return f

    use.log = log
    yield use
    llm.set_backend(None)


def run(**kw):
    args = {"codes": CODES, "history": HISTORY, "failed_items": ["Đáp số x = 5"], "ctx": CTX} | kw
    return diagnoser.run(STEPS, PROBLEM, **args)


def test_valid_mistake_kept(fake):
    fake(diagnoser.DiagnosisOut(corrected_latex="[2] $x = 5$", mistakes=[mistake()]))
    d = run()
    assert [m.step_idx for m in d.mistakes] == [2] and d.flags == [] and d.corrected_latex == "[2] $x = 5$"


@pytest.mark.parametrize(
    ("bad", "flag"),
    [({"code": "notational.symbol"}, "bad_code"), ({"kc_id": 99}, "bad_kc"), ({"step_idx": 9}, "bad_step")],
)
def test_invalid_mistake_dropped_and_flagged(fake, bad, flag):
    fake(diagnoser.DiagnosisOut(corrected_latex="", mistakes=[mistake(**bad), mistake(kc_id=None)]))
    d = run()
    assert [m.kc_id for m in d.mistakes] == [None] and [f.type for f in d.flags] == [flag]


def test_prompt_has_active_codes_with_examples_history_and_kcs(fake):
    f = fake(diagnoser.DiagnosisOut(corrected_latex="", mistakes=[]))
    run()
    [c] = f.calls
    system, user = "\n".join(c["system"]), c["user"]
    assert "computational.intermediate_calc" in system and "$3 \\cdot 4 = 7$" in system and "other.unclear" in system
    head = user.split(llm.OPEN)[0]
    assert "[7] 8DS-PT1-01 Chuyển vế" in head and "Viết sai dấu bằng" in head and "Đáp số x = 5" in head
    assert "[2] $x = 4$" in user.split(llm.OPEN)[1]


def test_prompt_version_follows_taxonomy_not_problem(fake):
    fake(diagnoser.DiagnosisOut(corrected_latex="", mistakes=[]))
    run()
    run(history=[])
    edited = [CODES[0] | {"example": "$2 + 2 = 5$"}, CODES[1]]
    run(codes=edited)
    v = [json.loads(x)["prompt_version"] for x in fake.log.read_text(encoding="utf-8").splitlines()]
    assert v[0] == v[1] != v[2] and v[2] == diagnoser.prompt_version(edited)


def test_schema_error_twice_gives_flag(fake):
    fake(None)
    d = run()
    assert d.mistakes == [] and [f.type for f in d.flags] == ["schema"]
