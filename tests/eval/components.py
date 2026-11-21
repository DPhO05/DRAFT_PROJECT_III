"""Component targets: one agent run alone on a fixed task set, scored without the graph around it (plan T8).

01: match a student's problem to the bank. The task set is tests/eval/tasks/ingest_01.json.
"""

import json
from contextlib import closing
from pathlib import Path

from tests.eval import agents, metrics
from tests.fakes import FakeLLM
from tutor import llm
from tutor.agents.a01_ingest import ingest
from tutor.db import repo
from tutor.services import latex

TASKS_01: list[dict] = json.loads((Path(__file__).parent / "tasks" / "ingest_01.json").read_text(encoding="utf-8"))


def body(t: dict) -> str:
    """The problem text between \\begin{problem} and \\end{problem}, as 01 receives it."""
    p = latex.split_problems(t["tex"])[0]
    return t["tex"][p.body_pos : p.body_pos_end]


def _redact(paths) -> dict[str, str]:
    """Every student with a full name (two words or more) -> student code, for the Guard."""
    with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
        return {
            s["name"]: s["code"] for s in repo.list_students(conn, include_archived=True) if len(s["name"].split()) > 1
        }


def _match_01(paths, w, t, log) -> dict:
    n0 = len(agents.read_log(log))
    with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
        bank = repo.bank_problems(conn)
    ctx = llm.CallContext(graph="G1", thread_id=f"eval-{t['id']}", redact=_redact(paths))
    res = ingest.run(t["tex"], bank, grade=t["grade"], ctx=ctx)
    rows, refs, a = agents.read_log(log)[n0:], {b["ref"] for b in bank}, res.attempts[0]
    raw = [c.get("ref") for r in rows if r["result"] == "ok" for c in json.loads(r["output"])["candidates"]]
    return {"id": t["id"], "expect_ref": t["expect_ref"], "ref": a.ref,
            "candidates": [c.model_dump() for c in a.candidates],
            "low_match": any(f.type == "low_match" for f in res.flags), "model_calls": len(rows),
            "bad_candidates": sum(r not in refs for r in raw)}  # fmt: skip


def evaluate_01(make_backend, *, work: Path, runs: int = 3, only: list[str] | None = None, traces=None) -> dict:
    """make_backend(conn) -> (llm backend | None for the real API, models). Runs and tasks go in order."""
    t = agents.trials(TASKS_01, _match_01, make_backend, work=work, runs=runs, only=only, traces=traces)
    return agents.summarize("01", t, key="id", score=metrics.score_01, passed=metrics.passed_01, payload="items")


def oracle_01(conn):
    """FakeLLM that finds its task by the problem text in the prompt: one candidate at 0.95, or none."""

    def handle(user, system):
        t = next(t for t in TASKS_01 if body(t)[:40] in user)
        return ingest.MatchResult(
            candidates=[ingest.Candidate(ref=t["expect_ref"], score=0.95)] if t["expect_ref"] else []
        )

    return FakeLLM({"01": handle}), {}
