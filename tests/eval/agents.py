"""Agent 00 eval harness (P8b): ask the tutor app's chat assistant a fixed question set, score which tools it used.

Wiring mirrors api/assistant.py: MCP session, fixed prompt parts and tool list from it, `orchestrator.reply`.
"""

import json
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from tests.agents.test_tools import recorder
from tests.assistant_fix import world
from tests.eval import metrics
from tests.fakes import FakeLLM
from tutor import config, llm
from tutor.agents.a00_orchestrator import orchestrator
from tutor.agents.a00_orchestrator.tools import Toolbox
from tutor.db import repo
from tutor.mcp import server
from tutor.mcp.client import connect

QUESTIONS: list[dict] = json.loads((Path(__file__).parent / "questions_00.json").read_text(encoding="utf-8"))
DONE = "Mình đã tra xong, thầy/cô xem thẻ bên dưới."  # no digits: nothing for the number check to flag


def _world(work: Path):
    """(paths, world) in `work`: empty tutor.db, then the assistant test world."""
    paths = config.paths(work / "data").ensure()
    repo.init_db(paths.tutor_db, paths.backup)
    with closing(repo.connect(paths.tutor_db)) as conn:
        return paths, world(conn)


def _ask_00(paths, w: dict, q: dict) -> tuple[dict, str]:
    """(answer, app prompt_version) for one question in a new read-only session, as one tutor message."""
    calls = []
    starters = recorder(calls)
    with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
        everyone = {s["id"]: s for s in repo.list_students(conn, include_archived=True)}
        redact = {s["name"]: s["code"] for s in everyone.values()}
        box = Toolbox(conn, settings=config.defaults(), today=w["today"], text=q["text"], starters=starters)
        s = connect("00", box)
        fixed = orchestrator.fixed_parts(json.loads(s.resource(server.KCS)), json.loads(s.resource(server.ERROR_CODES)))
        tools = s.tools()
        events = list(
            orchestrator.reply(
                orchestrator.Turn(q["text"]),
                history=[],
                conn=conn,
                starters=starters,
                settings=config.defaults(),
                today=w["today"],
                redact=redact,
                students=everyone,
                conversation_id="2026-10-21-1",
                fixed=fixed,
                tools=tools,
                call=s.call,
            )
        )
    answer = {
        "id": q["id"],
        "expect": q["expect"],
        "forbid": q["forbid"],
        "tools": [e["name"] for e in events if e["type"] == "tool" and e["state"] != "start"],
        "tool_errors": sum(e["type"] == "tool" and e["state"] == "error" for e in events),
        "unverified": sum(e["type"] == "warning" and e["kind"] == "unverified_number" for e in events),
        "stopped": events[-1]["stopped"],
    }
    return answer, orchestrator.version(fixed, tools)


def evaluate_00(make_backend, *, work: Path, runs: int = 3) -> dict:
    """make_backend(conn) -> (llm backend | None for the real API, models). Runs and questions go in order."""
    paths, w = _world(work)
    with closing(repo.connect(paths.tutor_db)) as conn:
        backend, models = make_backend(conn)
    log = paths.logs / "llm.jsonl"
    llm.configure(log, models)
    llm.set_backend(backend)
    answers, errors, app_version = [], [], None
    for k in range(runs):
        got = []
        for q in QUESTIONS:
            try:
                answer, app_version = _ask_00(paths, w, q)
            except Exception as e:  # recorded; the question counts as failed in pass^k
                errors.append({"run": k + 1, "id": q["id"], "error": f"{type(e).__name__}: {e}"})
            else:
                got.append(answer)
        answers.append(got)
    versions: dict[str, set] = {}
    for row in llm.iter_log(log):
        versions.setdefault(row["agent"], set()).add(row["prompt_version"])
    passed = [{q["id"]: False for q in QUESTIONS} | {a["id"]: metrics.passed_00(a) for a in got} for got in answers]
    return {
        "agent": "00",
        "created": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "runs": runs,
        "app_version": app_version,
        "prompt_versions": {a: sorted(v) for a, v in sorted(versions.items())},
        "metrics": {"per_run": [metrics.score_00(got) for got in answers], "pass_k": metrics.pass_k(passed)},
        "errors": errors,
        "answers": answers,
    }


def question_of(messages: list[dict]) -> dict:
    """The question a chat call belongs to: the first user message is "Hôm nay: …" + blank line + the text."""
    text = messages[0]["content"].split("\n\n", 1)[1]
    return next(q for q in QUESTIONS if q["text"] == text)


def oracle_00(conn):
    """FakeLLM that follows each question's script, one model turn per scripted step, then answers without a number."""

    def handle(messages):
        script, step = question_of(messages)["script"], sum(m["role"] == "assistant" for m in messages)
        if step < len(script):
            return [{"type": "tool_use", **call} for call in script[step]]
        return [{"type": "text", "text": DONE}]

    return FakeLLM({"00": handle}), {}
