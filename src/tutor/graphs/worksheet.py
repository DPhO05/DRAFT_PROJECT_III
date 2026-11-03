"""G4 worksheet (P6-T07): propose → DỪNG gate_worksheet → commit recommendation rows in one transaction, then the .tex.

No LLM call. Rows first, file second: a rerun after a file error finds the rows and only writes the file again."""

import json
import re
import sqlite3
import threading
from collections.abc import Callable
from contextlib import closing
from datetime import date
from pathlib import Path

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from tutor.agents.a08_recommender import select
from tutor.config import DataPaths, student_code
from tutor.db import repo
from tutor.graphs.runner import Runner
from tutor.graphs.state import WorksheetState
from tutor.services import search

GRAPH = "G4"
SELF_ADDED = "Thầy/cô tự thêm"
_START = threading.Lock()  # delete the old draft + start the new one must not interleave: one draft per student
_UNSAVED = ("running", "awaiting_review", "failed")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def _day(text: object) -> date:
    try:
        if isinstance(text, str) and _DATE.fullmatch(text):
            return date.fromisoformat(text)
    except ValueError:
        pass
    raise ValueError(f"Ngày phiếu phải dạng YYYY-MM-DD: {text}")


def _ref(ref: object) -> str:
    if not isinstance(ref, str):
        raise ValueError(f"Mã bài phải là chữ: {ref!r}")
    return ref.strip().upper()


def tex_url(student_id: int, for_date: str) -> str:
    return f"/api/worksheets/{student_id}/{for_date}.tex"


def sheet_file(paths: DataPaths, student_id: int, for_date: str) -> Path:
    """data/out/phieu-<HS>-<yyyy-mm-dd>.tex; ValueError unless for_date is a real date, so it stays in data/out/."""
    _day(for_date)
    return paths.out / f"phieu-{student_code(student_id)}-{for_date}.tex"


def resolve(conn: sqlite3.Connection, refs: list[str], reasons: dict) -> tuple[list[dict], list[dict]]:
    """(problems that can go on the sheet, in order; refs that cannot, each with `why`). Bank refs match any case."""
    cards = {c["ref"].upper(): c for c in search.find_problems(conn, refs)}
    ok, bad, seen = [], [], set()
    for ref in refs:
        c = cards.get(ref.upper())
        if c is None:
            why = "không có trong ngân hàng"
        elif not c["kcs"]:
            why = "bài chưa gắn kỹ năng"
        elif c["id"] in seen:
            why = "đã có trong phiếu"
        else:
            seen.add(c["id"])
            r = reasons.get(ref.upper()) or {}
            ok.append({
                "ref": c["ref"], "problem_id": c["id"], "kc_id": c["kcs"][0]["id"], "bucket": r.get("bucket"),
                "reason": r.get("reason") if r else SELF_ADDED, "level": c["level"],
                "kcs": [k["name"] for k in c["kcs"]], "statement_latex": c["statement_latex"],
            })  # fmt: skip
            continue
        bad.append({"ref": ref, "why": why})
    return ok, bad


def plan(state: WorksheetState, decisions: object) -> tuple[str, list[str], bool]:
    """(for_date, refs, replace) the sheet is made with; None decisions = the proposal. ValueError when malformed."""
    d = {} if decisions is None else decisions
    if not isinstance(d, dict):
        raise ValueError("Quyết định phiếu không đúng dạng")
    for_date, refs, replace = (
        d.get("for_date", state["for_date"]),
        d.get("refs", state["refs"]),
        d.get("replace", False),
    )
    _day(for_date)
    if not isinstance(refs, list) or not all(isinstance(r, str) for r in refs) or not isinstance(replace, bool):
        raise ValueError("Quyết định phiếu không đúng dạng")
    return for_date, refs, replace


def propose(
    paths: DataPaths,
    runner: Runner,
    *,
    student_id: int,
    for_date: str,
    items: list[dict],
    note: str | None = None,
    warnings: list[str] | None = None,
) -> dict:
    """Start a draft sheet and wait until it stops at the gate. items = [{ref, bucket?, reason?}] in sheet order.

    A student has one draft: an unsaved G4 thread of theirs is deleted and the new one takes its place (R18)."""
    day = _day(for_date)
    refs, reasons = [], {}
    for it in items:
        ref = _ref(it.get("ref"))
        if it.get("bucket") not in (None, *select.BUCKETS):
            raise ValueError(f"Nhóm bài không hợp lệ: {it['bucket']}")
        if ref not in refs:
            refs.append(ref)
            if it.get("bucket") or it.get("reason"):
                reasons[ref] = {"bucket": it.get("bucket"), "reason": it.get("reason")}
    with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
        code = repo.get_student(conn, student_id)["code"]
    state = {"student_id": student_id, "for_date": for_date, "refs": refs, "reasons": reasons,
             "warnings": warnings or [], "note": note}  # fmt: skip
    meta = {"subject": f"{code} · phiếu {day:%d/%m/%Y}", "student_id": student_id}
    with _START:
        old = [t["thread_id"] for t in runner.list_threads(graph=GRAPH, student_id=student_id)
               if t["status"] in _UNSAVED]  # fmt: skip
        for tid in old:
            runner.delete(tid)
        base = f"g4-{code.replace('-', '').lower()}-{day:%Y%m%d}"
        tid, k = base, 1
        while runner.exists(tid):  # C-05: -k suffix
            k += 1
            tid = f"{base}-{k}"
        runner.start(GRAPH, tid, state, meta)
    runner.wait(tid)
    with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
        ok, bad = resolve(conn, refs, reasons)
    return {"thread_id": tid, "existing": bool(old), "added": [o["ref"] for o in ok], "invalid": bad}


def add_refs(paths: DataPaths, runner: Runner, thread_id: str, refs: list[str]) -> dict:
    """Append refs to the draft's saved decision (or its own refs), repeats dropped. `invalid` stay on the sheet."""
    row = runner.get(thread_id)
    if row["graph"] != GRAPH or row["status"] != "awaiting_review":
        raise ValueError("Không có phiếu nháp để thêm bài")
    state = runner.state(thread_id)
    for_date, have, replace = plan(state, json.loads(row["decisions_json"]) if row["decisions_json"] else None)
    seen, fresh = {r.upper() for r in have}, []
    for ref in map(_ref, refs):
        if ref not in seen:
            seen.add(ref)
            fresh.append(ref)
    runner.save_decisions(thread_id, {"for_date": for_date, "refs": [*have, *fresh], "replace": replace})
    with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
        ok, bad = resolve(conn, fresh, state["reasons"])
    return {"thread_id": thread_id, "added": [o["ref"] for o in ok], "invalid": bad}


def pending(paths: DataPaths) -> Callable[[dict, object, str], int]:
    """Runner resume check: 1 while the sheet is empty, has a bad or repeated ref, or the date is malformed."""

    def count(state: dict, decisions: object, node: str) -> int:
        try:
            _, refs, _ = plan(state, decisions)
        except ValueError:
            return 1
        with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
            ok, bad = resolve(conn, refs, state["reasons"])
        return int(bool(bad) or not ok)

    return count


def check(paths: DataPaths) -> Callable[[dict, object], None]:
    """Runner resume check: WorksheetExists when the date holds a different live sheet and `replace` is false."""

    def run(state: dict, decisions: object) -> None:
        for_date, refs, replace = plan(state, decisions)
        with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
            live = repo.worksheet_problem_ids(conn, state["student_id"], for_date)
            ids = [o["problem_id"] for o in resolve(conn, refs, state["reasons"])[0]]
        if live and not replace and live != ids:
            raise repo.WorksheetExists(for_date, len(live))

    return run


def tex(code: str, for_date: str, problems: list[dict]) -> str:
    """R27: the sheet as problems in order, statements only."""
    head = f"% Phiếu bài tập {code} · {_day(for_date):%d/%m/%Y}\n"
    return head + "".join(
        f"\n\\begin{{problem}}[{p['ref']}]\n{p['statement_latex']}\n\\end{{problem}}\n" for p in problems
    )


def _shown(row: dict, state: dict) -> tuple[str, list[str]]:
    """(for_date, refs) of the sheet as saved; the proposal when nothing is saved or the save is malformed."""
    saved = json.loads(row["decisions_json"]) if row.get("decisions_json") else state.get("decisions")
    try:
        return plan(state, saved)[:2]
    except ValueError:
        return plan(state, None)[:2]


def card(row: dict, state: dict, conn: sqlite3.Connection) -> dict:
    """The teacher's view of a G4 thread (api-v3 §3.5): the sheet as saved or proposed, words only (no kc_id)."""
    for_date, refs = _shown(row, state)
    ok, invalid = resolve(conn, refs, state["reasons"])
    stage = {"running": "saving", "awaiting_review": "draft", "committed": "saved"}.get(row["status"], "failed")
    sid, receipt = state["student_id"], state.get("receipt")
    live = repo.worksheet_problem_ids(conn, sid, for_date) if stage == "draft" else []
    items = [{k: o[k] for k in ("ref", "problem_id", "level", "kcs", "bucket", "reason", "statement_latex")}
             for o in ok]  # fmt: skip
    return {
        "kind": "worksheet",
        "stage": stage,
        "student_id": sid,
        "for_date": for_date,
        "items": items,
        "counts": {b: sum(i["bucket"] == b for i in items) for b in select.BUCKETS}
        | {"added": sum(i["bucket"] is None for i in items)},
        "warnings": state.get("warnings", []),
        "invalid": invalid,
        "existing_for_date": {"n_problems": len(live)} if live else None,
        "saved": {"for_date": receipt["for_date"], "n_problems": receipt["n_problems"],
                  "tex": tex_url(sid, receipt["for_date"])} if stage == "saved" and receipt else None,
    }  # fmt: skip


def reminder(row: dict, state: dict) -> dict:
    """One line of GET /api/assistant/pending (api-v3 §3.3) for a G4 thread."""
    for_date, refs = _shown(row, state)
    return {"kind": "worksheet", "thread_id": row["thread_id"], "student_id": state["student_id"], "date": for_date,
            "words": f"{len(refs)} bài"}  # fmt: skip


def build(paths: DataPaths) -> StateGraph:
    def gate_worksheet(state: WorksheetState) -> dict:
        return {"decisions": interrupt({"gate": "worksheet"})["decisions"]}

    def commit(state: WorksheetState) -> dict:
        for_date, refs, replace = plan(state, state["decisions"])
        with closing(repo.connect(paths.tutor_db)) as conn:
            ok, bad = resolve(conn, refs, state["reasons"])
            if bad or not ok:
                raise ValueError("Phiếu còn bài không hợp lệ")
            receipt = repo.commit_worksheet(conn, student_id=state["student_id"], for_date=for_date, replace=replace,
                                            items=[{k: o[k] for k in ("problem_id", "kc_id", "bucket", "reason")}
                                                   for o in ok])  # fmt: skip
        code = student_code(state["student_id"])
        paths.out.mkdir(parents=True, exist_ok=True)
        sheet_file(paths, state["student_id"], for_date).write_text(tex(code, for_date, ok), encoding="utf-8")
        return {"receipt": receipt, "committed": True}

    g = StateGraph(WorksheetState)
    g.add_node("gate_worksheet", gate_worksheet)
    g.add_node("commit", commit)
    g.add_edge(START, "gate_worksheet")
    g.add_edge("gate_worksheet", "commit")
    g.add_edge("commit", END)
    return g
