"""Harvest teacher-corrected G1 sessions as draft eval tasks, plus the production rates (design T16, decision 8A).

uv run python tests/eval/harvest.py --data <data dir> [--out data/eval/tasks/inbox]

Only reads the data dir (SQLite `mode=ro&immutable=1`). An immutable reader does not see rows still in a `-wal` file,
so CLOSE THE APP FIRST: a non-empty `tutor.db-wal` or `checkpoints.db-wal` makes this exit 2 before any read.
Writes <out>/<today>/g1/<thread_id>.tex (names masked), g1/labels.json, failed|09|00|component/tasks.json (drafts,
names masked) and production.json.
"""

# ruff: noqa: E402
import argparse
import json
import sqlite3
import sys
from contextlib import closing
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if not __package__:  # run as a script: make `tests.*` importable
    sys.path.insert(0, str(ROOT))

from tutor import config, llm
from tutor.api.assistant import _read
from tutor.db import repo

STATUSES = ("confirmed", "edited", "rejected", "added")
CORRECTED = STATUSES[1:]


def _ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro&immutable=1", uri=True)


def rates(counts: dict) -> dict:
    """kept, edited, rejected: shares of what 03 proposed; added: share of the final mistakes 03 missed."""
    c, e, r, a = (counts[k] for k in STATUSES)

    def share(n: int, total: int):
        return round(n / total, 3) if total else None

    return {"kept": share(c, c + e + r), "edited": share(e, c + e + r), "rejected": share(r, c + e + r),
            "added": share(a, c + e + a)}  # fmt: skip


def _names(conn: sqlite3.Connection) -> dict[str, str]:
    return {s["name"]: s["code"] for s in repo.list_students(conn, include_archived=True)}


def sessions(conn: sqlite3.Connection, data: Path, out: Path) -> dict:
    """Write a draft task per committed session a teacher corrected under `out`; return the production.json body."""
    kc_code = {k["id"]: k["code"] for k in repo.list_kc(conn)}
    students = {s["id"]: s for s in repo.list_students(conn, include_archived=True)}
    names = _names(conn)
    root = data.resolve()
    total = dict.fromkeys(STATUSES, 0)
    labels: dict[str, dict] = {}
    committed = 0
    for row in repo.list_sessions(conn, status="committed"):
        committed += 1
        d = repo.session_detail(conn, row["id"])
        signals = dict.fromkeys(STATUSES, 0)
        for a in d["attempts"]:
            for m in a["mistakes"]:
                signals[m["status"]] += 1
        for k, n in signals.items():
            total[k] += n
        src = (root / d["source_path"]).resolve()
        if not any(signals[k] for k in CORRECTED) or not src.is_relative_to(root) or not src.is_file():
            continue
        name = f"{d['thread_id']}.tex"
        (out / "g1").mkdir(parents=True, exist_ok=True)
        (out / "g1" / name).write_text(llm.mask(src.read_text(encoding="utf-8"), names), encoding="utf-8")
        labels[name] = {
            "grade": students[d["student_id"]]["grade"],
            "student_name": None,
            "problems": [
                {
                    "seq": a["seq"],
                    "ref": a["ref"],
                    "has_id": True,
                    "n_steps": len(a["steps"]),
                    "mistakes": [
                        {
                            "step_idx": m["step_idx"],
                            "code": m["code"],
                            "kc": kc_code.get(m["kc_id"]),
                            "note": llm.mask(m["description"], names),
                            "propagates_to": [],
                        }
                        for m in a["mistakes"]
                        if m["status"] != "rejected"
                    ],
                }  # fmt: skip
                for a in d["attempts"]
            ],
            "notes": [],
            "source": "production",
            "status": "draft",
            "student_code": d["student_code"],
            "session_id": d["id"],
            "held_on": d["held_on"],
            "signals": signals,
        }
    if labels:
        (out / "g1" / "labels.json").write_text(json.dumps(labels, ensure_ascii=False, indent=1), encoding="utf-8")
    return {
        "created": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sessions": committed,
        "harvested": len(labels),
        "proposals": total,
        "rates": rates(total),
    }


def _select(db: Path, sql: str) -> list[sqlite3.Row]:
    """Rows of a read-only SELECT; a missing file or table gives []."""
    if not db.is_file():
        return []
    with closing(_ro(db)) as conn:
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(sql).fetchall()
        except sqlite3.OperationalError:
            return []


def _share(n: int, total: int):
    return round(n / total, 6) if total else None


def _save(out: Path, sub: str, drafts: list[dict]) -> None:
    if drafts:
        (out / sub).mkdir(parents=True, exist_ok=True)
        text = json.dumps(drafts, ensure_ascii=False, indent=1)
        (out / sub / "tasks.json").write_text(text, encoding="utf-8")


DRAFT = {"source": "production", "status": "draft"}


def failed_threads(data: Path, out: Path, names: dict) -> dict:
    """Draft flow tasks from threads that ended `failed`."""
    rows = _select(
        config.paths(data).checkpoints_db,
        "SELECT thread_id, graph, student_id, held_on, error, input_json FROM tutor_thread WHERE status = 'failed'",
    )
    drafts = []
    for r in rows:
        src = json.loads(r["input_json"]).get("source_path") if r["input_json"] else None
        drafts.append({
            "thread_id": r["thread_id"],
            "graph": r["graph"],
            "student_code": config.student_code(r["student_id"]) if r["student_id"] is not None else None,
            "held_on": r["held_on"],
            "error": llm.mask(r["error"] or "", names),
            "source_path": llm.mask(src, names) if src else None,
        } | DRAFT)  # fmt: skip
    _save(out, "failed", drafts)
    return {"failed_threads": len(drafts)}


def reports(data: Path, out: Path, names: dict) -> dict:
    """Draft 09 tasks from reports with a writer row that is not `ok` or an approved row with a flag."""
    rows = _select(
        config.paths(data).tutor_db, "SELECT id, student_id, period_kind, period_start, audit_json FROM report"
    )
    drafts, writer_rows, flagged = [], 0, 0
    for r in rows:
        try:
            audit = json.loads(r["audit_json"] or "{}")
        except ValueError:
            continue
        rows_of = {k: [x for x in audit.get(k) or [] if isinstance(x, dict)] for k in ("writer", "approved")}
        bad = [x for x in rows_of["writer"] if x.get("status") != "ok"]
        writer_rows += len(rows_of["writer"])
        flagged += len(bad)
        approved = [x for x in rows_of["approved"] if x.get("flag")]
        if bad or approved:
            drafts.append({
                "code": config.student_code(r["student_id"]),
                "period_kind": r["period_kind"],
                "period_start": r["period_start"],
                "writer": json.loads(llm.mask(json.dumps(bad, ensure_ascii=False), names)),
                "approved": json.loads(llm.mask(json.dumps(approved, ensure_ascii=False), names)),
            } | DRAFT)  # fmt: skip
    _save(out, "09", drafts)
    return {"report_flagged_rate": _share(flagged, writer_rows)}


def chats(data: Path, out: Path, names: dict) -> dict:
    """Draft 00 tasks from answers with an unverified-number warning and from rejected approvals."""
    drafts, answers, warned = [], 0, 0
    for f in sorted(config.paths(data).logs.glob("chat/*.jsonl")):
        said = ""
        for row in _read(f):
            if row.get("role") == "user" and not row.get("decision"):
                said = row.get("text") or ""
            hit = row.get("role") == "assistant" and any(
                e.get("kind") == "unverified_number" for e in row.get("events") or [] if isinstance(e, dict)
            )
            reject = row.get("role") == "user" and row.get("decision") == "reject"
            if row.get("role") == "assistant":
                answers += 1
                warned += hit
            if hit or reject:
                drafts.append({
                    "id": f"{f.stem}-{row.get('id')}",
                    "text": llm.mask(said, names),
                    "expect": [],
                    "forbid": ["start_grading"] if reject else [],
                } | DRAFT)  # fmt: skip
    _save(out, "00", drafts)
    return {"unverified_rate": _share(warned, answers)}


def llm_rows(data: Path, out: Path, names: dict) -> dict:
    """Draft component tasks from calls that ended `schema_error` or `retry`; G1 cost per session."""
    prices = config.defaults()
    drafts, usd, threads = [], 0.0, set()
    for r in llm.iter_log(
        config.paths(data).logs / "llm.jsonl", prices["price_assumption"], by_model=prices["price_by_model"]
    ):
        if r.get("graph") == "G1":
            usd += r["cost_usd"]
            threads.add(r.get("thread_id"))
        if r.get("result") in ("schema_error", "retry") and r.get("user"):
            drafts.append({
                "agent": r.get("agent"),
                "prompt_version": r.get("prompt_version"),
                "thread_id": r.get("thread_id"),
                "user": llm.mask(r["user"], names),
            } | DRAFT)  # fmt: skip
    _save(out, "component", drafts)
    return {"usd_per_session": round(usd / len(threads), 6) if threads else None}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, required=True, help="thư mục data, chỉ đọc. Đóng app trước khi gom")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "eval" / "tasks" / "inbox")
    a = ap.parse_args(argv)
    paths = config.paths(a.data)
    for db in (paths.tutor_db, paths.checkpoints_db):
        wal = db.with_name(f"{db.name}-wal")
        if wal.exists() and wal.stat().st_size:
            print("Đóng app trước khi gom: còn file -wal")
            return 2
    if not paths.tutor_db.is_file():
        print(f"Không thấy {paths.tutor_db.name} trong {a.data}")
        return 2
    day = a.out / date.today().isoformat()
    with closing(_ro(paths.tutor_db)) as conn:
        prod = sessions(conn, a.data, day)
        names = _names(conn)
    for source in (failed_threads, reports, chats, llm_rows):
        prod |= source(a.data, day, names)
    day.mkdir(parents=True, exist_ok=True)
    (day / "production.json").write_text(json.dumps(prod, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Gom {prod['harvested']}/{prod['sessions']} buổi, {prod['failed_threads']} luồng lỗi → {day}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
