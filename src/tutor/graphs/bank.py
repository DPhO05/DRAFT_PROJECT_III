"""G2 bank import (P5-T03): read a teacher's .tex → DỪNG confirm_import → commit in one transaction. No LLM call."""

import json
import re
import sqlite3
import threading
from collections import Counter
from collections.abc import Callable
from contextlib import closing
from datetime import date
from pathlib import Path

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from tutor.config import DataPaths
from tutor.db import repo
from tutor.graphs.runner import Runner
from tutor.graphs.state import BankState
from tutor.services import bank, latex

GRAPH = "G2"
_START = threading.Lock()  # check-for-thread + start must not interleave: two POSTs for one file make one thread


def _source(paths: DataPaths, file: str):
    """Only .tex files inside data/inbox/bank/ (SDD §9.1 #4)."""
    folder = (paths.inbox / "bank").resolve()
    p = (folder / file).resolve()
    if p.suffix.lower() != ".tex" or not p.is_relative_to(folder) or not p.is_file():
        raise ValueError(f"Chỉ nhận file .tex trong data/inbox/bank/: {file}")
    return p, folder


def start_import(paths: DataPaths, runner: Runner, *, file: str) -> dict:
    """Check the file, then run `read` in the background. A file whose import is not committed yet keeps its thread."""
    src, folder = _source(paths, file)
    if not latex.split_problems(src.read_text(encoding="utf-8")):
        raise ValueError("Không tìm thấy bài nào trong file (chưa có dòng \\begin{problem})")
    name = src.relative_to(folder).as_posix()
    with _START:
        for t in runner.list_threads(graph=GRAPH):
            if t["subject"] == name and t["status"] in ("running", "awaiting_review", "failed"):
                return {"thread_id": t["thread_id"], "status": t["status"], "existing": True}
        stem = re.sub(r"[^a-z0-9-]", "-", src.stem.lower())
        base = f"g2-{stem}-{date.today():%Y%m%d}"
        tid, k = base, 1
        while runner.exists(tid):
            k += 1
            tid = f"{base}-{k}"
        runner.start(GRAPH, tid, {"file": src.relative_to(paths.root.resolve()).as_posix()}, {"subject": name})
    return {"thread_id": tid, "status": "running", "existing": False}


def inbox(paths: DataPaths, conn: sqlite3.Connection) -> list[dict]:
    """Every .tex in data/inbox/bank/ with how much of it is already in the bank. Broken problems are not counted."""
    created = repo.bank_created_at(conn)
    out = []
    for f in sorted((paths.inbox / "bank").glob("*.tex")):
        text = f.read_text(encoding="utf-8-sig", errors="replace")
        refs = [b.ref for b in bank.read_bank(text, {}) if not b.invalid]
        have = [created[r] for r in refs if r in created]
        first = text.split("\n", 1)[0].strip()
        title = (first.lstrip("%").strip() or None) if first.startswith("%") else None
        n, new = len(refs), len(refs) - len(have)
        out.append({
            "file": f.name,
            "title": title,
            "bytes": f.stat().st_size,
            "n_problems": n,
            "n_new": new,
            "status": "empty" if n == 0 else "imported" if new == 0 else "new" if new == n else "partly",
            "imported_at": max(have)[:10] if have else None,
        })  # fmt: skip
    return out


def _kc_ok(ids: object, known_kc: set[int]) -> bool:
    return (
        isinstance(ids, list)
        and bool(ids)
        and all(isinstance(i, int) and not isinstance(i, bool) and i in known_kc for i in ids)
    )


def final_items(items: list[dict], decisions: object, known_kc: set[int]) -> tuple[list[dict], int]:
    """(items to write with the teacher's answers applied, how many still lack a valid KC).

    Invalid and existing items are skipped. A decision key absent keeps the file's value; a malformed answer
    leaves the item missing, so it is never written."""
    answers = decisions.get("items") if isinstance(decisions, dict) else None
    answers = answers if isinstance(answers, dict) else {}
    out, missing = [], 0
    for it in items:
        if it["invalid"] or it["existing"]:
            continue
        d = answers.get(it["ref"])
        d = d if isinstance(d, dict) else {}
        final = dict(it)
        try:
            if "kc_ids" in d:
                if not _kc_ok(d["kc_ids"], known_kc):
                    raise ValueError("kc_ids")
                final["tags"] = [[k, 0, None] for k in dict.fromkeys(d["kc_ids"])]
            if "level" in d:
                final["delta"] = bank.level_delta(d["level"])
            if "rubric_items" in d:
                final["rubric_items"] = bank.rubric_items(d["rubric_items"])
        except (ValueError, TypeError):
            missing += 1
            continue
        if final["tags"]:
            out.append(final)
        else:
            missing += 1
    return out, missing


def _known_kc(paths: DataPaths) -> set[int]:
    with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
        return {k["id"] for k in repo.list_kc(conn)}


def pending(paths: DataPaths) -> Callable[[dict, object, str], int]:
    """Runner resume check: problems that still have no valid KC (a level is optional)."""

    def count(state: dict, decisions: object, node: str) -> int:
        return final_items(state["items"], decisions, _known_kc(paths))[1]

    return count


def _level(delta: float | None) -> str | None:
    if delta is None:
        return None
    return "dễ" if delta < -0.3 else "khó" if delta > 0.3 else "vừa"


def card(row: dict, state: dict, kcs: list[dict]) -> dict:
    """The teacher's view of an import thread; `kcs` is the catalog (repo.list_kc). Saved decisions are applied."""
    items, names = state.get("items") or [], {k["id"]: k for k in kcs}
    known = set(names)
    saved = json.loads(row["decisions_json"]) if row.get("decisions_json") else state.get("decisions")
    answers = saved.get("items") if isinstance(saved, dict) else None
    answers = answers if isinstance(answers, dict) else {}
    shown, write = [], []
    for it in items:
        kept, _ = final_items([it], saved, known)
        fin = kept[0] if kept else it
        decided = isinstance(a := answers.get(it["ref"]), dict) and "level" in a
        live = not (it["invalid"] or it["existing"])
        needs = [n for n, lack in (("kc", not kept), ("level", fin["delta"] is None and not decided)) if live and lack]
        write += kept
        shown.append({
            "ref": it["ref"],
            "statement_latex": it["statement_latex"],
            "kcs": [{"id": k, "name": names[k]["name"]} for k in dict.fromkeys(t[0] for t in fin["tags"])],
            "level": _level(fin["delta"]),
            "needs": needs,
            "unknown_label": it["unknown_label"],
            "existing": it["existing"],
            "invalid": it["invalid"],
            "rubric_items": fin["rubric_items"],
        })  # fmt: skip
    # R5: a problem's topic is the parent (or itself) of its smallest KC id
    topics: Counter[int] = Counter()
    for w in write:
        k = names[min(t[0] for t in w["tags"])]
        topics[k["parent_id"] or k["id"]] += 1
    top = min(topics, key=lambda t: (-topics[t], t)) if topics else None
    valid = [i for i in shown if not i["invalid"]]
    status = row["status"]
    stage = ("saving" if items else "reading") if status == "running" else {
        "awaiting_review": "preview", "committed": "saved"}.get(status, "failed")  # fmt: skip
    return {
        "kind": "bank_import",
        "stage": stage,
        "file": row["subject"],
        "topic": {"id": top, "name": names[top]["name"]} if top is not None else None,
        "n_total": len(valid),
        "n_ready": sum(not i["needs"] and not i["existing"] for i in valid),
        "n_need": sum(bool(i["needs"]) for i in valid),
        "n_existing": sum(i["existing"] for i in valid),
        "n_invalid": len(shown) - len(valid),
        "receipt": state.get("receipt"),
        "items": shown,
    }


def build(paths: DataPaths) -> StateGraph:
    def read(state: BankState) -> dict:
        tex = (paths.root / state["file"]).read_text(encoding="utf-8")
        with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
            kc_ids = {k["code"]: k["id"] for k in repo.list_kc(conn)}
            refs = {p["ref"] for p in repo.bank_problems(conn)}
        items = [
            {"ref": b.ref, "statement_latex": b.statement, "solution_latex": b.solution,
             "tags": [list(t) for t in b.tags], "delta": b.delta, "rubric_items": b.rubric_items, "needs": b.needs,
             "unknown_label": b.unknown_label, "invalid": b.invalid,
             "existing": b.invalid is None and b.ref in refs}
            for b in bank.read_bank(tex, kc_ids)
        ]  # fmt: skip
        return {"items": items}

    def gate_confirm_import(state: BankState) -> dict:
        return {"decisions": interrupt({"gate": "confirm_import"})["decisions"]}

    def commit(state: BankState) -> dict:
        rows, _ = final_items(state["items"], state["decisions"], _known_kc(paths))
        source = f"import:{Path(state['file']).name}"
        write = [
            {"ref": r["ref"], "statement": r["statement_latex"], "solution": r["solution_latex"], "source": source,
             "delta": r["delta"], "tags": r["tags"], "rubric_items": r["rubric_items"]}
            for r in rows
        ]  # fmt: skip
        repo.backup(paths.tutor_db, paths.backup)
        with closing(repo.connect(paths.tutor_db)) as conn:
            receipt = repo.import_bank(conn, write)
        receipt["skipped_existing"] += sum(i["existing"] for i in state["items"])  # flagged at read, never sent
        return {"receipt": receipt, "committed": True}

    g = StateGraph(BankState)
    g.add_node("read", read)
    g.add_node("gate_confirm_import", gate_confirm_import)
    g.add_node("commit", commit)
    g.add_edge(START, "read")
    g.add_edge("read", "gate_confirm_import")
    g.add_edge("gate_confirm_import", "commit")
    g.add_edge("commit", END)
    return g
