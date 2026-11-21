"""Agent 00 and 09 eval harnesses (P8b), scored over several runs for pass^k.

00: ask the tutor app's chat assistant a fixed question set, score which tools it used. Wiring mirrors
api/assistant.py: fixed prompt parts and tool list from the catalog, `chat.events` on a fresh thread.
09: write the parent report of a few fixed periods of the same world, score what the audit did to the draft.
"""

import dataclasses
import json
import re
import shutil
import unicodedata
from contextlib import closing
from datetime import UTC, datetime
from functools import partial
from itertools import chain
from pathlib import Path

from langchain_core.messages import AIMessage, messages_to_dict
from langgraph.checkpoint.memory import InMemorySaver

from tests.agents.test_tools import recorder
from tests.assistant_fix import world
from tests.eval import judges, metrics
from tests.fakes import FakeLLM
from tutor import config, llm
from tutor.agents.a00_orchestrator import chat, orchestrator
from tutor.agents.a00_orchestrator.tools import Toolbox, lc_tools, tool_defs
from tutor.agents.a09_reporter import reporter
from tutor.api import assistant
from tutor.db import repo
from tutor.graphs import registry, report, session
from tutor.services import facts

QUESTIONS: list[dict] = json.loads((Path(__file__).parent / "questions_00.json").read_text(encoding="utf-8"))
DONE = "Mình đã tra xong, thầy/cô xem thẻ bên dưới."  # no digits: nothing for the number check to flag
PERIODS: list[dict] = [  # HS-02 has one session in `world`, on 14/10
    {"key": "HS-01 month 2026-10-01", "code": "HS-01", "period_kind": "month", "period_start": "2026-10-01"},
    {"key": "HS-01 week 2026-10-12", "code": "HS-01", "period_kind": "week", "period_start": "2026-10-12"},
    {"key": "HS-02 day 2026-10-14", "code": "HS-02", "period_kind": "day", "period_start": "2026-10-14"},
    {"key": "HS-01 day 2026-10-14", "code": "HS-01", "period_kind": "day", "period_start": "2026-10-14"},
    {"key": "HS-01 week 2026-10-05", "code": "HS-01", "period_kind": "week", "period_start": "2026-10-05"},
    {
        "key": "HS-02 week 2026-10-12 low",
        "code": "HS-02",
        "period_kind": "week",
        "period_start": "2026-10-12",
        "low_pass_rate": 0.6,
    },  # no period of `world` is low at the default 0.5
]


G5_PERIODS = [PERIODS[1]]  # HS-01 week 2026-10-12


def _world(work: Path):
    """(paths, world) in `work`: empty tutor.db, then the assistant test world."""
    paths = config.paths(work / "data").ensure()
    repo.init_db(paths.tutor_db, paths.backup)
    with closing(repo.connect(paths.tutor_db)) as conn:
        return paths, world(conn)


def _fails(*args):
    raise ValueError("File này không đọc được")


# task fields the grader reads, copied into the answer
_GRADER_FIELDS = ("expect_approval", "approval", "expect_starts", "allow_tool_error", "max_calls", "max_model_calls",
                  "expect_text", "expect_any", "card_only", "expect_last_args")  # fmt: skip


def _echo_sheet(record):
    """The recorder's propose_worksheet, answering with the refs it was sent: a fixed sheet makes a real model retry."""

    def f(sid, for_date, items, note, warnings):
        return record(sid, for_date, items, note, warnings) | {"added": [i["ref"] for i in items], "invalid": []}

    return f


def _ask_00(paths, w: dict, q: dict, log: Path, judge: bool = False) -> dict:
    """The answer to one task in a new read-only session: its messages in one thread, approvals answered as scripted."""
    calls = []
    starters = recorder(calls)
    starters = dataclasses.replace(starters, propose_worksheet=_echo_sheet(starters.propose_worksheet))
    if q.get("fail_tools"):
        starters = dataclasses.replace(starters, **dict.fromkeys(q["fail_tools"], _fails))
    with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
        everyone = {s["id"]: s for s in repo.list_students(conn, include_archived=True)}
        redact = {s["name"]: s["code"] for s in everyone.values()}
        codes = repo.error_codes(conn, active_only=True)
        code_names = [c["code"] for c in codes]
        fixed = orchestrator.fixed_parts(repo.list_kc(conn), codes)
        tools = tool_defs(code_names)
        n0 = len(read_log(log))
        saver, cfg = InMemorySaver(), {"configurable": {"thread_id": "eval"}, "recursion_limit": 200}
        cc = llm.CallContext(graph=None, conversation_id="2026-10-21-1", redact=orchestrator._names(redact))
        events, approvals, agent, error = [], [], None, None
        said = []
        try:
            with chat.scope(cc, fixed, tools):
                for text in [q["text"], *q.get("turns", [])]:  # as the app: all new per message, the thread stays
                    box = Toolbox(conn, settings=config.defaults(), today=w["today"], text=text, starters=starters)
                    ctx = chat.ChatContext(orchestrator.Turn(text), box, everyone, redact)
                    agent = chat.build(llm.model("00"), lc_tools(box, code_names), saver,
                                       max_tool_turns=config.defaults()["assistant"]["max_tool_turns"],
                                       system=fixed)  # fmt: skip
                    leg = list(chat.events(agent, ctx, cfg))
                    events += leg
                    said.append("".join(e["delta"] for e in leg if e["type"] == "text"))
                    while leg and leg[-1]["type"] == "approval":
                        approvals.append({"name": leg[-1]["name"], "args": leg[-1]["args"]})
                        decision = assistant.Decision(**q.get("approval", {"decision": "reject"}))
                        resume = assistant._decisions(decision, chat.waiting(agent, cfg))
                        leg = list(chat.events(agent, ctx, cfg, resume=resume))
                        events += leg
                        said[-1] += "".join(e["delta"] for e in leg if e["type"] == "text")
        except Exception as e:  # kept as a failed answer so its log rows still count for leaks
            events, approvals, error = [], [], orchestrator.mask(f"{type(e).__name__}: {e}", redact)
        thread = agent.get_state(cfg).values.get("messages", []) if agent else []
        messages = messages_to_dict(thread)
    rows = read_log(log)[n0:]  # before any judge call, so a judge never changes passed or the call bound
    leaks = leak_count(chain(_strings(rows), _strings(messages)), orchestrator._names(redact))
    made = [{"name": c["name"], "args": c["args"]} for m in thread if isinstance(m, AIMessage) for c in m.tool_calls]
    text = "" if error else "\n\n".join(s for s in said if s)
    dones = [e for e in events if e["type"] == "done"]
    verdict = {}
    if judge and q.get("judge") and not error:  # report-only: never changes passed; masked before it is stored
        seen = "\n".join(c if isinstance(c, str) else json.dumps(c, ensure_ascii=False) for c in ctx.seen)
        seen += "\nLời gọi công cụ: " + json.dumps(made, ensure_ascii=False)
        context = llm.mask(seen, cc.redact)
        sentences = [llm.mask(s, cc.redact) for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]
        n1 = len(read_log(log))
        verdict = {
            "judge": _judge(context, sentences, cc.redact),
            "judge_context": context,
            "judge_sentences": sentences,
        }
        leaks += _judge_leaks(log, n1, cc.redact, verdict)
    return {
        "id": q["id"],
        "expect": q["expect"],
        "forbid": q["forbid"],
        "expect_args": q.get("expect_args", {}),
        **{k: q[k] for k in _GRADER_FIELDS if k in q},
        "calls": made,
        "starts": [list(c) for c in calls],
        "approvals": approvals,
        "model_calls": len(rows),
        "leaks": leaks,
        "schema_errors": sum(not metrics.args_fit(c, tools) for c in made),
        "codes_shown": sum(c["code"] in text for c in codes),
        "cards": sum(e["type"] == "card" for e in events),
        "tools": [e["name"] for e in events if e["type"] == "tool" and e["state"] != "start"],
        "tool_errors": sum(e["type"] == "tool" and e["state"] == "error" for e in events),
        "unverified": sum(e["type"] == "warning" and e["kind"] == "unverified_number" for e in events),
        "stopped": "error" if error else dones[-1]["stopped"] if dones else "no_done",
        "error": error,
        "text": text,
        "warnings": [e for e in events if e["type"] == "warning"],
        "app_version": orchestrator.version(fixed, tools),
        "trace": {"events": events, "messages": messages},
    } | verdict


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
                errors.append({"run": k, key: t[key], "error": orchestrator.mask(f"{type(e).__name__}: {e}", names)})
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


def _judge(context: str, sentences: list[str], redact: dict[str, str]) -> dict:
    """judges.faithfulness; an unavailable judge becomes an empty result with its masked error, never a failed task."""
    try:
        return judges.faithfulness(context, sentences, llm.CallContext(graph=None, redact=redact))
    except llm.LLMUnavailable as e:
        return {"verdicts": [], "score": None, "unknown": 0, "error": llm.mask(f"{type(e).__name__}: {e}", redact)}


def _judge_leaks(log: Path, n0: int, redact: dict[str, str], result: dict) -> int:
    """Leaks in the judge's log rows after row n0 and in its verdicts."""
    return leak_count(chain(_strings(read_log(log)[n0:]), _strings(result)), redact)


def _faithfulness(items: list[dict]) -> dict:
    """Mean judge score over the judged items of all runs (None when none), and the unknown and failed judge calls."""
    judged = [x["judge"] for x in items if x.get("judge")]
    scores = [j["score"] for j in judged if j["score"] is not None]
    return {"faithfulness": sum(scores) / len(scores) if scores else None,
            "judge_unknown": sum(j["unknown"] for j in judged),
            "judge_errors": sum("error" in j for j in judged)}  # fmt: skip


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


def evaluate_00(make_backend, *, work: Path, runs: int = 3, only: list[str] | None = None, traces=None,
                judge: bool = False, judge_model: str | None = None) -> dict:  # fmt: skip
    """make_backend(conn) -> (llm backend | None for the real API, models). Runs and questions go in order.

    judge: also score the faithfulness of the marked tasks' replies (report-only); judge_model: the judge's model."""
    t = trials(QUESTIONS, partial(_ask_00, judge=judge), make_backend, work=work, runs=runs, only=only, traces=traces,
               models={"judge": judge_model} if judge_model else None)  # fmt: skip
    answers, app_version = t["got"], None
    for k, got in enumerate(answers, 1):
        chats = [{"id": a["id"], **a.pop("trace")} for a in got]
        if traces is not None:
            traces.mkdir(parents=True, exist_ok=True)
            (traces / f"run{k}-chat.json").write_text(json.dumps(chats, ensure_ascii=False), encoding="utf-8")
        for a in got:
            app_version = a.pop("app_version")
            if error := a.pop("error"):
                t["errors"].append({"run": k, "id": a["id"], "error": error})
    leaks = sum(a["leaks"] for done in t["got"] for a in done)
    res = summarize("00", t, key="id", score=metrics.score_00, passed=metrics.passed_00, payload="answers",
                    leaks=leaks)  # fmt: skip
    rates = [s["approval_ok"] for s in res["metrics"]["per_run"] if s["approval_ok"] is not None]
    res["metrics"]["extra"]["approval_ok"] = sum(rates) / len(rates) if rates else None
    res["metrics"]["extra"] |= _judge_extra(t, judge) or {}
    return res | {"app_version": app_version}


def _report_09(paths, w: dict, p: dict, log: Path, judge: bool = False) -> dict:
    """The report of one period, written in a new read-only session."""
    with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
        settings, today = config.defaults(), w["today"]
        sid = next(s["id"] for s in repo.list_students(conn, include_archived=True) if s["code"] == p["code"])
        cfg = {"configurable": {"thread_id": f"eval-{p['key']}"}}
        ctx = session.call_context(paths, sid, None, cfg, graph="G5")  # as the app: names masked
        got = facts.report_facts(conn, sid, p["period_kind"], p["period_start"], today=today,
                                 low_pass_rate=p.get("low_pass_rate", settings["report"]["low_pass_rate"]))  # fmt: skip
        n0, error = len(read_log(log)), None
        try:
            r = reporter.run(got, ctx=ctx)
        except Exception as e:  # kept as a failed report so its log rows still count for leaks
            error = orchestrator.mask(f"{type(e).__name__}: {e}", ctx.redact)
            r = {"sentences": [], "audit": [], "low": got["low"], "insights": [], "facts": got["facts"]}
        rows = read_log(log)[n0:]  # before any judge call, so a judge never changes passed or the call bound
    row = _report_row(p, r, rows, ctx.redact, error)
    return _judged(row, log, ctx.redact) if judge and not error else row


def _judged(row: dict, log: Path, redact: dict[str, str]) -> dict:
    """The report row plus the judge's verdicts on its sentences; report-only, `passed` never reads them."""
    n0 = len(read_log(log))
    row["judge"] = _judge(row["facts_block"], row["sentences"], redact)
    row["leaks"] += _judge_leaks(log, n0, redact, row["judge"])
    return row


def _report_row(p: dict, r: dict, rows: list[dict], redact: dict[str, str], error: str | None) -> dict:
    """The row of one 09 report (or of a failed one: empty `r`), as the 09 and G5 targets score it."""
    sentences = [s["text"] for s in r["sentences"]]
    return {
        "key": p["key"],
        "period_kind": p["period_kind"],
        "n_sentences": len(sentences),
        "audit": r["audit"],
        "sentences": sentences,
        "low": r["low"],
        "n_insights": len(r["insights"]),
        "has_previous": any(f["kind"] == "previous" for f in r["facts"]),
        "model_calls": len(rows),
        "leaks": leak_count(chain(_strings(rows), sentences), redact),
        "facts_block": "\n".join(f"{f['fact_id']} · {f['text']}" for f in r["facts"]),
        "error": error,
    }


def _judge_extra(t: dict, judge: bool) -> dict | None:
    """The extra keys of a judged run; None keeps the extra of an unjudged run as it was."""
    return _faithfulness([r for done in t["got"] for r in done]) if judge else None


def _pop_errors(t: dict) -> int:
    """Move each failed report's error into t["errors"]; the leaks of all reports."""
    for k, got in enumerate(t["got"], 1):
        for r in got:
            if error := r.pop("error"):
                t["errors"].append({"run": k, "key": r["key"], "error": error})
    return sum(r["leaks"] for done in t["got"] for r in done)


def evaluate_09(make_backend, *, work: Path, runs: int = 3, only: list[str] | None = None, traces=None,
                judge: bool = False, judge_model: str | None = None) -> dict:  # fmt: skip
    """make_backend(conn) -> (llm backend | None for the real API, models). Runs and periods go in order."""
    t = trials(PERIODS, partial(_report_09, judge=judge), make_backend, work=work, runs=runs, key="key", only=only,
               traces=traces, models={"judge": judge_model} if judge_model else None)  # fmt: skip
    return summarize("09", t, key="key", score=metrics.score_09, passed=metrics.passed_09, payload="reports",
                     leaks=_pop_errors(t), extra=_judge_extra(t, judge))  # fmt: skip


def _draft_g5(paths, w: dict, p: dict, log: Path, judge: bool = False) -> dict:
    """The G5 draft of one period, run to its review gate; no teacher decision, so no report row may exist."""
    with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
        everyone = repo.list_students(conn, include_archived=True)
    sid = next(s["id"] for s in everyone if s["code"] == p["code"])
    redact = {s["name"]: s["code"] for s in everyone}
    n0, error, draft, gate = len(read_log(log)), None, None, False
    r = registry.make_runner(paths)
    try:
        tid = report.start(paths, r, student_id=sid, period_kind=p["period_kind"], period_start=p["period_start"],
                           today=w["today"])["thread_id"]  # fmt: skip
        try:
            row = r.wait(tid, 900)
            rows = read_log(log)[n0:]  # before any judge call, so a judge never changes passed or the call bound
            if (row["status"], row["node"]) != ("awaiting_review", "gate_report"):
                raise RuntimeError(f"{row['status']} ở {row['node']}: {row['error']}")
            draft, gate = r.state(tid)["draft"], True
        except Exception as e:  # kept as a failed report so its log rows still count for leaks
            error = orchestrator.mask(f"{type(e).__name__}: {e}", redact)
            rows = read_log(log)[n0:]
    finally:
        r.close()
    with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
        report_rows = conn.execute("SELECT COUNT(*) FROM report").fetchone()[0]
    draft = draft or {"sentences": [], "audit": [], "low": False, "insights": [], "facts": []}
    row = _report_row(p, draft, rows, redact, error) | {"gate": gate, "report_rows": report_rows}
    return _judged(row, log, redact) if judge and not error else row


def evaluate_g5(make_backend, *, work: Path, runs: int = 3, only: list[str] | None = None, traces=None,
                judge: bool = False, judge_model: str | None = None) -> dict:  # fmt: skip
    """G5 up to its review gate, on the period of G5_PERIODS. Same errors and leaks rules as evaluate_09."""
    t = trials(G5_PERIODS, partial(_draft_g5, judge=judge), make_backend, work=work, runs=runs, key="key", only=only,
               traces=traces, models={"judge": judge_model} if judge_model else None)  # fmt: skip
    return summarize("g5", t, key="key", score=metrics.score_09, payload="reports", leaks=_pop_errors(t),
                     passed=lambda r: metrics.passed_09(r) and r["gate"] and r["report_rows"] == 0,
                     extra=_judge_extra(t, judge))  # fmt: skip


def question_of(messages: list[dict]) -> dict:
    """The question a chat call belongs to: the first user message is "Hôm nay: …" + blank line + the text."""
    first = messages[0]["content"]  # a string, or blocks when the message came through the agent
    text = (first if isinstance(first, str) else "".join(b["text"] for b in first)).split("\n\n", 1)[1]
    return next(q for q in QUESTIONS if text in (q["text"], q.get("masked")))


def oracle_00(conn):
    """FakeLLM that follows each question's script, one model turn per scripted step, then answers without a number."""

    def handle(messages):
        step = sum(m["role"] == "assistant" for m in messages)
        q = question_of(messages)
        if step < len(q["script"]) and q["script"][step]:  # an empty step: answer in words
            return [{"type": "tool_use", **call} for call in q["script"][step]]
        return [{"type": "text", "text": q.get("say", DONE)}]

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
