"""Harvest teacher-corrected G1 sessions as draft eval tasks, plus the production rates (design T16, decision 8A).

uv run python tests/eval/harvest.py --data <data dir> [--out data/eval/tasks/inbox]

Only reads the data dir (SQLite `mode=ro&immutable=1`). An immutable reader does not see rows still in a `-wal` file,
so CLOSE THE APP FIRST: a non-empty `tutor.db-wal` or `checkpoints.db-wal` makes this exit 2 before any read.
Writes <out>/<today>/g1/<thread_id>.tex (names masked), g1/labels.json and production.json.
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


def sessions(conn: sqlite3.Connection, data: Path, out: Path) -> dict:
    """Write a draft task per committed session a teacher corrected under `out`; return the production.json body."""
    kc_code = {k["id"]: k["code"] for k in repo.list_kc(conn)}
    students = {s["id"]: s for s in repo.list_students(conn, include_archived=True)}
    names = {s["name"]: s["code"] for s in students.values()}
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
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
    day.mkdir(parents=True, exist_ok=True)
    (day / "production.json").write_text(json.dumps(prod, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Gom {prod['harvested']}/{prod['sessions']} buổi → {day}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
