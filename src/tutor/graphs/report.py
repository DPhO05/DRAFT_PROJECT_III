"""G5 period report (P7-T05, P7-T06 file): write (09 over MCP) → DỪNG gate_report → commit the report row, then the .md.

Row first, file second: a rerun after a file error finds the row with the same text and only writes the file."""

import re
import threading
from collections.abc import Callable
from contextlib import closing
from datetime import date
from pathlib import Path

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from tutor import config
from tutor.agents.a00_orchestrator.tools import Toolbox
from tutor.agents.a09_reporter import reporter
from tutor.config import DataPaths, student_code
from tutor.db import repo
from tutor.graphs import session
from tutor.graphs.runner import Runner
from tutor.graphs.state import ReportState
from tutor.mcp import client
from tutor.services import facts
from tutor.services.audit import check_sentence

GRAPH = "G5"
WORDS = {"day": "ngày", "week": "tuần", "month": "tháng"}
_START = threading.Lock()  # find the period's draft + start a new one must not interleave: one draft per period
_UNSAVED = ("running", "awaiting_review", "failed")


def base_id(code: str, kind: str, start: str) -> str:
    """C-05: g5-<hsNN><d|w|m>-<yyyymmdd>."""
    return f"g5-{code.replace('-', '').lower()}{kind[0]}-{start.replace('-', '')}"


def report_file(paths: DataPaths, student_id: int, kind: str, start: str) -> Path:
    return paths.out / f"baocao-{student_code(student_id)}-{kind}-{start}.md"


def start(paths: DataPaths, runner: Runner, *, student_id: int, period_kind: str, period_start: str,
          today: date) -> dict:  # fmt: skip
    """Start the period's draft, or hand back the one it has (R16). Nothing is written to tutor.db (C-39).

    ValueError: malformed period; ReportApproved: approved already; NotReady: no committed session in the period."""
    lo, hi = facts.period(period_kind, period_start, today)
    with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
        code = repo.get_student(conn, student_id)["code"]
        if done := repo.report_for(conn, student_id, period_kind, period_start):
            raise repo.ReportApproved(done["id"], done["approved_at"])
        base = base_id(code, period_kind, period_start)
        with _START:
            for t in runner.list_threads(graph=GRAPH, student_id=student_id):
                if t["status"] in _UNSAVED and re.fullmatch(rf"{base}(-\d+)?", t["thread_id"]):
                    return {"thread_id": t["thread_id"], "status": t["status"], "existing": True}
            try:
                facts.report_facts(conn, student_id, period_kind, period_start, today=today,
                                   low_pass_rate=_settings(paths)["report"]["low_pass_rate"])  # fmt: skip
            except facts.NotReady as e:  # name the period's sessions still waiting for review (api-v3 §5.1)
                waiting = [{"thread_id": t["thread_id"], "held_on": t["held_on"]}
                           for t in runner.list_threads(graph=session.GRAPH, student_id=student_id)
                           if t["status"] in _UNSAVED and lo.isoformat() <= t["held_on"] <= hi.isoformat()]  # fmt: skip
                raise facts.NotReady(e.detail | {"pending": waiting}) from None
            tid, k = base, 1
            while runner.exists(tid):  # C-05: -k suffix
                k += 1
                tid = f"{base}-{k}"
            meta = {"subject": f"{code} · báo cáo {WORDS[period_kind]} {lo:%d/%m/%Y}", "student_id": student_id}
            runner.start(GRAPH, tid, {"student_id": student_id, "period_kind": period_kind,
                                      "period_start": period_start}, meta)  # fmt: skip
    return {"thread_id": tid, "status": "running", "existing": False}


def sentences(state: dict, decisions: object) -> list[dict]:
    """The report as it stands: saved sentences, else 09's; each re-audited (C-41) with `flag` and `why`.

    A sentence citing no known fact is checked against every fact of the period (api-v3 §9 #18). ValueError when
    the decisions are malformed."""
    draft = state["draft"]
    given = draft["sentences"]
    if decisions is not None:
        given = decisions.get("sentences") if isinstance(decisions, dict) else None
        ok = isinstance(given, list) and all(
            isinstance(s, dict) and isinstance(s.get("text"), str) and s["text"].strip()
            and isinstance(s.get("facts", []), list) and all(isinstance(f, str) for f in s.get("facts", []))
            for s in given
        )  # fmt: skip
        if not ok:
            raise ValueError("Câu báo cáo không đúng dạng")
    by_id = {f["fact_id"]: f for f in draft["facts"]}
    dates = [date.fromisoformat(d) for d in draft["dates"]]
    out = []
    for s in given:
        text = " ".join(s["text"].split())  # one line each in text_md
        ids = [f for f in dict.fromkeys(s.get("facts", [])) if f in by_id]
        cited = [by_id[f] for f in ids] or draft["facts"]
        flag = check_sentence(text, cited, low=draft["low"], need_fact=False, dates=dates) or {}
        out.append({"text": text, "facts": ids, "flag": flag.get("flag"), "why": flag.get("why")})
    return out


def pending(paths: DataPaths) -> Callable[[dict, object, str], int]:
    """Runner resume check: 1 while the decisions are malformed or leave no sentence; flags only warn."""

    def count(state: dict, decisions: object, node: str) -> int:
        try:
            return int(not sentences(state, decisions))
        except ValueError:
            return 1

    return count


def text_md(sentences: list[dict]) -> str:
    """R17: one sentence a line, its fact ids after it."""
    return "".join(f"{s['text']}{' ' if s['facts'] else ''}{''.join(f'[{f}]' for f in s['facts'])}\n"
                   for s in sentences)  # fmt: skip


def _settings(paths: DataPaths) -> dict:
    try:
        return config.load(paths.settings)
    except config.SettingsError:
        return config.defaults()


def build(paths: DataPaths) -> StateGraph:
    def write(state: ReportState, config) -> dict:
        sid = state["student_id"]
        ctx = session.call_context(paths, sid, None, config, graph=GRAPH)  # C-40: every full name masked
        with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
            box = Toolbox(conn, settings=_settings(paths), today=date.today(), text="", starters=None)
            period = {"period_kind": state["period_kind"], "period_start": state["period_start"]}
            draft = reporter.run(client.connect("09", box).call, code=ctx.student_code, **period, ctx=ctx)
        return {"draft": draft}

    def gate_report(state: ReportState) -> dict:
        return {"decisions": interrupt({"gate": "report"})["decisions"]}

    def commit(state: ReportState) -> dict:
        final = sentences(state, state["decisions"])  # pending() held the gate until it has a sentence
        md, sid, kind, start = text_md(final), state["student_id"], state["period_kind"], state["period_start"]
        audit = {"writer": state["draft"]["audit"],
                 "approved": [{"i": i, "flag": s["flag"], "why": s["why"]} for i, s in enumerate(final)]}  # fmt: skip
        with closing(repo.connect(paths.tutor_db)) as conn:
            receipt = repo.commit_report(conn, student_id=sid, period_kind=kind, period_start=start,
                                         facts=state["draft"]["facts"], text_md=md, audit=audit)  # fmt: skip
        paths.out.mkdir(parents=True, exist_ok=True)
        report_file(paths, sid, kind, start).write_text(md, encoding="utf-8")
        return {"receipt": receipt, "committed": True}

    g = StateGraph(ReportState)
    g.add_node("write", write)
    g.add_node("gate_report", gate_report)
    g.add_node("commit", commit)
    g.add_edge(START, "write")
    g.add_edge("write", "gate_report")
    g.add_edge("gate_report", "commit")
    g.add_edge("commit", END)
    return g
