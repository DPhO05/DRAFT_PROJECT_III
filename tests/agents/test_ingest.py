"""P1-T08: agent 01 Ingest (.tex)."""

import pytest

from tests.bankfix import P1, P2, add_bank
from tests.fakes import FakeLLM
from tutor import llm
from tutor.agents import CallContext
from tutor.agents.a01_ingest import ingest
from tutor.db import repo

TEX = r"""% Bài làm
\begin{problem}[8DS-PT1-001]
a) $4x = 20$
$x = 5$
\end{problem}
\begin{problem}
Tìm m để $2x + m = 5 - x$ nhận $x = 3$ làm nghiệm.
$6 + m = 2$
$m = -4$
\end{problem}
"""
CTX = CallContext(graph="G1", thread_id="g1-hs01-20261020", session_id=1, student_code="HS-01")


@pytest.fixture
def bank(conn, tmp_path):
    add_bank(conn)
    llm.configure(tmp_path / "llm.jsonl", {})
    yield repo.bank_problems(conn)
    llm.set_backend(None)


def cands(*pairs):
    return ingest.MatchResult(candidates=[ingest.Candidate(ref=r, score=s) for r, s in pairs])


def test_ids_match_without_llm_and_no_id_goes_to_llm(bank):
    fake = FakeLLM({"01": cands(("NOPE-1", 0.99), (P2[0], 0.93), (P1[0], 0.2))})
    llm.set_backend(fake)
    res = ingest.run(TEX, bank, grade=8, ctx=CTX)
    a, b = res.attempts
    assert (a.ref, a.problem_id is not None, len(a.steps)) == (P1[0], True, 2)
    assert (b.ref, len(b.steps)) == (P2[0], 3)
    assert [c.ref for c in b.candidates] == [P2[0], P1[0]]  # unknown ref dropped by code
    assert fake.count["01"] == 1
    assert P2[1] in "".join(fake.calls[0]["system"]) and "9DS-PT2-001" not in "".join(fake.calls[0]["system"])
    assert "$m = -4$" in fake.calls[0]["user"]
    assert [(f.type, f.seq) for f in res.flags] == [("no_rubric", 2)]  # P2 has no approved rubric


def test_low_score_flags_low_match_with_candidates(bank):
    llm.set_backend(FakeLLM({"01": cands((P2[0], 0.6))}))
    res = ingest.run(TEX, bank, grade=8, ctx=CTX)
    b = res.attempts[1]
    assert b.ref is None and [c.ref for c in b.candidates] == [P2[0]]
    assert [f.type for f in res.flags] == ["low_match"]


def test_steps_keep_source_positions(bank):
    llm.set_backend(FakeLLM({"01": cands((P2[0], 0.95))}))
    res = ingest.run(TEX, bank, grade=8, ctx=CTX)
    for a in res.attempts:
        assert TEX[a.pos : a.pos_end].startswith("\\begin{problem}")
        assert all(TEX[s.pos : s.pos_end] == s.latex for s in a.steps)


def test_file_without_problems_is_an_error(bank):
    with pytest.raises(ValueError, match="problem"):
        ingest.run("chỉ có chữ", bank, grade=8, ctx=CTX)
