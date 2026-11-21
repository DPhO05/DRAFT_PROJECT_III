"""Agent 00 and 09 eval harnesses (P8b), scored over several runs for pass^k.

00: ask the tutor app's chat assistant a fixed question set, score which tools it used. Wiring mirrors
api/assistant.py: fixed prompt parts and tool list from the catalog, `chat.events` on a fresh thread.
09: write the parent report of a few fixed periods of the same world, score what the audit did to the draft.
"""

import json
import re
import shutil
import unicodedata
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from langchain_core.messages import messages_to_dict
from langgraph.checkpoint.memory import InMemorySaver

from tests.agents.test_tools import recorder
from tests.assistant_fix import world
from tests.eval import metrics
from tests.fakes import FakeLLM
from tutor import config, llm
from tutor.agents.a00_orchestrator import chat, orchestrator
from tutor.agents.a00_orchestrator.tools import Toolbox, lc_tools, tool_defs
from tutor.agents.a09_reporter import reporter
from tutor.db import repo
from tutor.graphs import session
from tutor.services import facts

QUESTIONS: list[dict] = json.loads((Path(__file__).parent / "questions_00.json").read_text(encoding="utf-8"))
DONE = "Mình đã tra xong, thầy/cô xem thẻ bên dưới."  # no digits: nothing for the number check to flag
PERIODS: list[dict] = [  # HS-02 has one session in `world`, on 14/10
    {"key": "HS-01 month 2026-10-01", "code": "HS-01", "period_kind": "month", "period_start": "2026-10-01"},
    {"key": "HS-01 week 2026-10-12", "code": "HS-01", "period_kind": "week", "period_start": "2026-10-12"},
    {"key": "HS-02 day 2026-10-14", "code": "HS-02", "period_kind": "day", "period_start": "2026-10-14"},
]


def _world(work: Path):
    """(paths, world) in `work`: empty tutor.db, then the assistant test world."""
    paths = config.paths(work / "data").ensure()
    repo.init_db(paths.tutor_db, paths.backup)
    with closing(repo.connect(paths.tutor_db)) as conn:
        return paths, world(conn)


def _ask_00(paths, w: dict, q: dict, log: Path) -> dict:
    """The answer to one question in a new read-only session, as one tutor message."""
    calls = []
    starters = recorder(calls)
    with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
        everyone = {s["id"]: s for s in repo.list_students(conn, include_archived=True)}
        redact = {s["name"]: s["code"] for s in everyone.values()}
        box = Toolbox(conn, settings=config.defaults(), today=w["today"], text=q["text"], starters=starters)
        codes = repo.error_codes(conn, active_only=True)
        fixed = orchestrator.fixed_parts(repo.list_kc(conn), codes)
        tools = tool_defs([c["code"] for c in codes])
        ctx = chat.ChatContext(orchestrator.Turn(q["text"]), box, everyone, redact)
        agent = chat.build(
            llm.model("00"),
            lc_tools(box, [c["code"] for c in codes]),
            InMemorySaver(),
            max_tool_turns=config.defaults()["assistant"]["max_tool_turns"],
            system=fixed,
        )
        cfg = {"configurable": {"thread_id": "eval"}, "recursion_limit": 200}
        cc = llm.CallContext(graph=None, conversation_id="2026-10-21-1", redact=orchestrator._names(redact))
        with chat.scope(cc, fixed, tools):
            events = list(chat.events(agent, ctx, cfg))
        messages = messages_to_dict(agent.get_state(cfg).values["messages"])
    return {
        "id": q["id"],
        "expect": q["expect"],
        "forbid": q["forbid"],
        "tools": [e["name"] for e in events if e["type"] == "tool" and e["state"] != "start"],
        "tool_errors": sum(e["type"] == "tool" and e["state"] == "error" for e in events),
        "unverified": sum(e["type"] == "warning" and e["kind"] == "unverified_number" for e in events),
        "stopped": events[-1]["stopped"],
        "text": "".join(e["delta"] for e in events if e["type"] == "text"),
        "warnings": [e for e in events if e["type"] == "warning"],
        "app_version": orchestrator.version(fixed, tools),
        "trace": {"events": events, "messages": messages},
    }


class UnknownTask(ValueError):
    """--only named a task the target does not have."""


PRICES, BY_MODEL = config.defaults()["price_assumption"], config.defaults()["price_by_model"]


def read_log(log: Path) -> list[dict]:
    """llm.jsonl rows with cost_usd at the default prices (config.py:32-48)."""
    return list(llm.iter_log(log, PRICES, by_model=BY_MODEL))


def trials(tasks, one, make_backend, *, work: Path, runs: int, key: str = "id", only=None, traces=None,
           models=None) -> dict:  # fmt: skip
    """Run every task `runs` times; each run gets a new world in work/run<k> and its own llm.jsonl.

    one(paths, w, task, log) -> dict that carries task[key]. make_backend(conn) is called once, on run 1.
    """
    if only is not None:
        if unknown := sorted(set(only) - {t[key] for t in tasks}):
            raise UnknownTask(f"Không có task {', '.join(unknown)}")
        tasks = [t for t in tasks if t[key] in only]
    got, errors, rows = [], [], []
    for k in range(1, runs + 1):
        paths, w = _world(work / f"run{k}")
        if k == 1:  # once: a stateful fake keeps its counters across runs
            with closing(repo.connect(paths.tutor_db)) as conn:
                backend, base = make_backend(conn)
                names = {s["name"]: s["code"] for s in repo.list_students(conn, include_archived=True)}
        log = paths.logs / "llm.jsonl"
        llm.configure(log, base | (models or {}))
        llm.set_backend(backend)
        done = []
        for t in tasks:
            try:
                done.append(one(paths, w, t, log))
            except Exception as e:  # recorded; the task counts as failed in pass^k
                errors.append({"run": k, key: t[key], "error": f"{type(e).__name__}: {e}"})
        got.append(done)
        rows += [r | {"run": k} for r in read_log(log)]
        if traces is not None and log.exists():
            traces.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(log, traces / f"run{k}.jsonl")
    return {"tasks": tasks, "got": got, "errors": errors, "rows": rows, "names": names}


def _strings(x):
    """Every string leaf of nested dicts and lists (JSON text would escape the backslashes and line breaks)."""
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for v in x.values():
            yield from _strings(v)
    elif isinstance(x, list):
        for v in x:
            yield from _strings(v)


def leak_count(texts, names: dict[str, str]) -> int:
    """How many of `texts` hold a full student name in any spelling llm.mask knows (case, diacritics, LaTeX spacing)."""
    names = {n: c for n, c in names.items() if len(n.split()) >= 2}
    # llm.mask returns NFC text: compare with the NFC form, or any non-NFC text would count as a leak
    return sum(llm.mask(t, names) != unicodedata.normalize("NFC", t) for t in texts)


def summarize(agent: str, t: dict, *, key: str, score, passed, payload: str, leaks: int | None = None,
              extra: dict | None = None) -> dict:  # fmt: skip
    """The result every trials-based target returns (plan contract C1); run.main adds set, backend and traces."""
    ok = [{x[key]: False for x in t["tasks"]} | {a[key]: passed(a) for a in done} for done in t["got"]]
    tally = metrics.tally(ok)
    seen: dict[str, dict[str, set]] = {"prompt_version": {}, "model": {}}
    for r in t["rows"]:
        for field, by_agent in seen.items():
            by_agent.setdefault(r["agent"], set()).add(r[field])
    if leaks is None:
        leaks = leak_count((x for r in t["rows"] for x in _strings(r)), t["names"])
    return {
        "agent": agent,
        "created": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "runs": len(t["got"]),
        "prompt_versions": {a: sorted(v) for a, v in sorted(seen["prompt_version"].items())},
        "models": {a: sorted(v) for a, v in sorted(seen["model"].items())},
        "metrics": {
            "per_run": [score(done) for done in t["got"]],
            "pass_k": tally["pass_k"],
            "success": tally["success"],
            "tally": tally,
            "extra": {"name_leaks": leaks} | (extra or {}),
        },
        "errors": t["errors"],
        "calls": metrics.usage(t["rows"]),
        payload: t["got"],
    }


def evaluate_00(make_backend, *, work: Path, runs: int = 3, only: list[str] | None = None, traces=None) -> dict:
    """make_backend(conn) -> (llm backend | None for the real API, models). Runs and questions go in order."""
    t = trials(QUESTIONS, _ask_00, make_backend, work=work, runs=runs, only=only, traces=traces)
    answers, app_version = t["got"], None
    for k, got in enumerate(answers, 1):
        chats = [{"id": a["id"], **a.pop("trace")} for a in got]
        if traces is not None:
            traces.mkdir(parents=True, exist_ok=True)
            (traces / f"run{k}-chat.json").write_text(json.dumps(chats, ensure_ascii=False), encoding="utf-8")
        for a in got:
            app_version = a.pop("app_version")
    res = summarize("00", t, key="id", score=metrics.score_00, passed=metrics.passed_00, payload="answers")
    return res | {"app_version": app_version}


def _report_09(paths, w: dict, p: dict, log: Path) -> dict:
    """The report of one period, written in a new read-only session."""
    with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
        settings, today = config.defaults(), w["today"]
        sid = next(s["id"] for s in repo.list_students(conn, include_archived=True) if s["code"] == p["code"])
        cfg = {"configurable": {"thread_id": f"eval-{p['key']}"}}
        ctx = session.call_context(paths, sid, None, cfg, graph="G5")  # as the app: names masked
        got = facts.report_facts(conn, sid, p["period_kind"], p["period_start"], today=today,
                                 low_pass_rate=settings["report"]["low_pass_rate"])  # fmt: skip
        r = reporter.run(got, ctx=ctx)
    return {
        "key": p["key"],
        "period_kind": p["period_kind"],
        "n_sentences": len(r["sentences"]),
        "audit": r["audit"],
    }


def evaluate_09(make_backend, *, work: Path, runs: int = 3, only: list[str] | None = None, traces=None) -> dict:
    """make_backend(conn) -> (llm backend | None for the real API, models). Runs and periods go in order."""
    t = trials(PERIODS, _report_09, make_backend, work=work, runs=runs, key="key", only=only, traces=traces)
    return summarize("09", t, key="key", score=metrics.score_09, passed=metrics.passed_09, payload="reports")


def question_of(messages: list[dict]) -> dict:
    """The question a chat call belongs to: the first user message is "Hôm nay: …" + blank line + the text."""
    first = messages[0]["content"]  # a string, or blocks when the message came through the agent
    text = (first if isinstance(first, str) else "".join(b["text"] for b in first)).split("\n\n", 1)[1]
    return next(q for q in QUESTIONS if q["text"] == text)


def oracle_00(conn):
    """FakeLLM that follows each question's script, one model turn per scripted step, then answers without a number."""

    def handle(messages):
        script, step = question_of(messages)["script"], sum(m["role"] == "assistant" for m in messages)
        if step < len(script):
            return [{"type": "tool_use", **call} for call in script[step]]
        return [{"type": "text", "text": DONE}]

    return FakeLLM({"00": handle}), {}


def oracle_09(conn):
    """FakeLLM that writes each "Số liệu" line as a sentence citing itself, repeated up to the period's minimum."""
    kinds = {"ngày": "day", "tuần": "week", "tháng": "month"}

    def handle(user, system):
        lo, hi = metrics.SENTENCES[kinds[re.search(r"^Kỳ: (ngày|tuần|tháng)", user, re.M)[1]]]
        block = user.split("Số liệu:\n", 1)[1].split("\n\n", 1)[0]
        facts = re.findall(r"^(F\d\d) · (.+)$", block, re.M)
        picks = [facts[i % len(facts)] for i in range(max(len(facts), lo))][:hi]
        return reporter.ReportOut(sentences=[reporter.Sentence(text=t, facts=[f]) for f, t in picks])

    return FakeLLM({"09": handle}), {}
