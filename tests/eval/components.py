"""Component targets: one agent run alone on a fixed task set, scored without the graph around it (plan T8).

01: match a student's problem to the bank. The task set is tests/eval/tasks/ingest_01.json.
04: agree, disagree or suggest another code for a claimed mistake. The set is tests/eval/tasks/verifier_04.json.
02r: draft a grading rubric for a bank problem. The set is tests/eval/tasks/rubric_02.json (bank refs).
08: rank bank problems for five student profiles (tasks/reco_08.json) and check the chat's problem search
(tasks/search_00.json). Code only, no model call. The labels are drafts until the owner reviews them.
"""

import json
from contextlib import closing
from datetime import timedelta
from pathlib import Path

from tests.eval import agents, metrics
from tests.fakes import FakeLLM, lane_handlers
from tests.services.test_select import did
from tests.services.test_student_reads import set_theta
from tutor import config, llm
from tutor.agents.a00_orchestrator.tools import Toolbox
from tutor.agents.a01_ingest import ingest
from tutor.agents.a02_grader import grader
from tutor.agents.a04_verifier import verifier
from tutor.agents.a08_recommender import select
from tutor.db import repo
from tutor.services import latex

TASKS_01: list[dict] = json.loads((Path(__file__).parent / "tasks" / "ingest_01.json").read_text(encoding="utf-8"))
TASKS_04: list[dict] = json.loads((Path(__file__).parent / "tasks" / "verifier_04.json").read_text(encoding="utf-8"))
TASKS_02R: list[dict] = json.loads((Path(__file__).parent / "tasks" / "rubric_02.json").read_text(encoding="utf-8"))
TASKS_08: list[dict] = json.loads((Path(__file__).parent / "tasks" / "reco_08.json").read_text(encoding="utf-8"))
SEARCH_00: list[dict] = json.loads((Path(__file__).parent / "tasks" / "search_00.json").read_text(encoding="utf-8"))
FIX = Path(__file__).parents[1] / "fixtures" / "submissions"


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


def _verify_04(paths, w, t, log) -> dict:
    n0 = len(agents.read_log(log))
    tex = (FIX / t["file"]).read_text(encoding="utf-8")
    ref = json.loads((FIX / "labels.json").read_text(encoding="utf-8"))[t["file"]]["problems"][t["seq"] - 1]["ref"]
    p = latex.split_problems(tex)[t["seq"] - 1]
    steps = [{"idx": s.idx, "latex": s.latex} for s in latex.split_steps(tex, p.body_pos, p.body_pos_end, by="line")]
    c = t["claim"]
    with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
        pid = next(b["id"] for b in repo.bank_problems(conn) if b["ref"] == ref)
        problem, codes = repo.problem_detail(conn, pid), repo.error_codes(conn, active_only=True)
    mistake = c | {"evidence_latex": next(s["latex"] for s in steps if s["idx"] == c["step_idx"])}
    ctx = llm.CallContext(graph="G1", thread_id=f"eval-{t['id']}", redact=_redact(paths))
    v = verifier.run(mistake, steps, problem, codes=codes, ctx=ctx)
    return {"id": t["id"], "expect": t["expect"], "expect_code": t.get("expect_code"), "verdict": v.verdict,
            "suggested_code": v.suggested_code, "model_calls": len(agents.read_log(log)) - n0}  # fmt: skip


def evaluate_04(make_backend, *, work: Path, runs: int = 3, only: list[str] | None = None, traces=None) -> dict:
    """make_backend(conn) -> (llm backend | None for the real API, models)."""
    t = agents.trials(TASKS_04, _verify_04, make_backend, work=work, runs=runs, only=only, traces=traces)
    return agents.summarize("04", t, key="id", score=metrics.score_04, passed=metrics.passed_04, payload="items")


def oracle_04(conn):
    """FakeLLM that finds its task by the claim description in the prompt and gives the expected verdict."""

    def handle(user, system):
        t = next(t for t in TASKS_04 if t["claim"]["description"] in user)
        return verifier.VerdictOut(verdict=t["expect"], reason="oracle", suggested_code=t.get("expect_code"))

    return FakeLLM({"04": handle}), {}


def _draft_02r(paths, w, t, log) -> dict:
    n0 = len(agents.read_log(log))
    with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
        pid = next(b["id"] for b in repo.bank_problems(conn) if b["ref"] == t["id"])
        problem = repo.problem_detail(conn, pid)
    ctx = llm.CallContext(graph="G1", thread_id=f"eval-{t['id']}", redact=_redact(paths))
    draft = grader.generate_rubric(problem, ctx=ctx)
    return {"id": t["id"], "draft": draft, "model_calls": len(agents.read_log(log)) - n0}


def evaluate_02r(make_backend, *, work: Path, runs: int = 3, only: list[str] | None = None, traces=None) -> dict:
    """make_backend(conn) -> (llm backend | None for the real API, models)."""
    t = agents.trials(TASKS_02R, _draft_02r, make_backend, work=work, runs=runs, only=only, traces=traces)
    return agents.summarize("02r", t, key="id", score=metrics.score_02r, passed=metrics.passed_02r, payload="items")


def oracle_02r(conn):
    """FakeLLM whose 02 returns the one-item draft for any problem."""
    return FakeLLM({"02": lane_handlers()["02"]}), {}


def _rank_08(paths, w, t, log) -> dict:
    """One profile: a new student with the task's skills, repeats and recent work, then the sheet 08 ranks."""
    with closing(repo.connect(paths.tutor_db)) as conn:
        sid = repo.add_student(conn, name=f"Eval {t['id']}", grade=t["grade"])
        kc = {k["code"]: k["id"] for k in repo.list_kc(conn)}
        ref = {b["ref"]: b["id"] for b in repo.bank_problems(conn)}
        for code, theta in t["theta"].items():
            set_theta(conn, sid, kc[code], theta)
        for r in t["repeats"]:
            conn.execute(
                "INSERT INTO misconception_log (student_id, code, kc_id, first_seen, last_seen, count)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (sid, r["code"], kc[r["kc"]], w["today"].isoformat(), w["today"].isoformat(), r["count"]),
            )
        for d in t["done"]:
            did(conn, sid, ref[d["ref"]], w["today"] - timedelta(days=d["days_ago"]))
        conn.commit()
        res = select.rank_problems(conn, sid, t["n"], reco=config.defaults()["reco"], today=w["today"])
    return {"id": t["id"], "n": t["n"], "refs": [i["ref"] for i in res["items"]], "warnings": res["warnings"],
            "relevant": t["relevant"], "must_not": t["must_not"]}  # fmt: skip


def evaluate_08(make_backend, *, work: Path, runs: int = 1, only: list[str] | None = None, traces=None) -> dict:
    """Ranking plus search recall. make_backend is ignored: a fake with no handler raises on any model call."""
    seen: dict = {}

    def one(paths, w, t, log):
        seen["today"] = w["today"]
        return _rank_08(paths, w, t, log)

    t = agents.trials(TASKS_08, one, lambda conn: (FakeLLM({}), {}), work=work, runs=runs, only=only, traces=traces)
    recall = []
    with closing(repo.connect(config.paths(work / "run1" / "data").tutor_db, readonly=True)) as conn:
        for q in SEARCH_00:
            box = Toolbox(conn, settings=config.defaults(), today=seen["today"], text=q["text"])
            out = box.run("search_problems", {"text": q["text"], "limit": 5})
            got = {p["ref"] for p in (out.card or {}).get("problems", [])}
            recall.append(len(got & set(q["relevant"])) / len(q["relevant"]))
    drafts = sum(x["status"] == "draft" for x in [*TASKS_08, *SEARCH_00])
    extra = {"search_recall_at_5": sum(recall) / len(recall), "draft_labels": drafts}
    return agents.summarize("08", t, key="id", score=metrics.score_08, passed=metrics.passed_08, payload="items",
                            extra=extra)  # fmt: skip
