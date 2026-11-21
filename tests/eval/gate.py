"""Gate: one scorecard against the floors and the no-drop rule of baseline.json (design 8.2, 8.3).

uv run python tests/eval/gate.py <scorecard.json> [--baseline FILE] [--backend real]
"""

import argparse
import json
import sys
from fnmatch import fnmatch
from pathlib import Path

BASELINE = Path(__file__).with_name("baseline.json")
PASS, FAIL, SKIP = "ĐẠT", "TRƯỢT", "BỎ QUA"
EPS = 1e-9  # float noise in `base - tolerance / n`


def _value(row: dict, metric: str):
    return row[metric] if metric in row else (row.get("metrics") or {}).get(metric)


def _line(status: str, row_set: str, metric: str, value, limit) -> dict:
    return {"status": status, "set": row_set, "metric": metric, "value": value, "limit": limit}


def _floor(f: dict, row: dict, baseline: dict) -> dict:
    value = _value(row, f["metric"])
    limit = f">= {f['min']}" if "min" in f else f"<= {f['max']}"
    if f.get("needs") and not baseline.get(f["needs"]):
        return _line(SKIP, row["set"], f["metric"], value, f"{limit} (cần {f['needs']})")
    if value is None:
        return _line(FAIL if f.get("hard") else SKIP, row["set"], f["metric"], value, limit)
    ok = value >= f["min"] if "min" in f else value <= f["max"]
    return _line(PASS if ok else FAIL, row["set"], f["metric"], value, limit)


def _no_drop(row: dict, base: dict, baseline: dict) -> list[dict]:
    tol = baseline["tolerance_tasks"]
    was, now = base.get("task_pass") or {}, row.get("task_pass") or {}
    both = was.keys() & now.keys()
    drops = sum(1 for t in both if was[t] and not now[t])
    out = [_line(PASS if drops <= tol else FAIL, row["set"], "task_pass", drops, f"<= {tol}")]
    if not both:
        out = [_line(SKIP, row["set"], "task_pass", None, f"<= {tol}")]
    n = row.get("n_tasks") or 0
    for m in baseline["no_drop"]:
        b, v = _value(base, m), _value(row, m)
        if b is None or v is None or not n:
            continue
        lo = b - tol / n
        out.append(_line(PASS if v >= lo - EPS else FAIL, row["set"], m, v, f">= {lo:.4g}"))
    return out


def check(rows: list[dict], baseline: dict) -> list[dict]:
    """One line per checked value: {"status": "ĐẠT" | "TRƯỢT" | "BỎ QUA", "set", "metric", "value", "limit"}."""
    out = [_floor(f, r, baseline) for f in baseline["floors"] for r in rows if fnmatch(r["set"], f["set"])]
    by_set = {r["set"]: r for r in rows}
    for name, base in baseline["real"]["rows"].items():
        if name in by_set:
            out += _no_drop(by_set[name], base, baseline)
        else:
            out.append(_line(SKIP, name, "no_drop", None, "set not in scorecard"))
    return out


def unverified(current: dict[str, list[str]], real: dict[str, list[str]]) -> list[str]:
    """`<agent> <prompt_version>` for every version in use that has no real scorecard yet (decision 10A)."""
    return [f"{a} {v}" for a, vs in current.items() for v in vs if v not in set(real.get(a, []))]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("scorecard", type=Path)
    ap.add_argument("--baseline", type=Path, default=BASELINE)
    ap.add_argument("--backend", default="real")
    a = ap.parse_args(argv)
    baseline = json.loads(a.baseline.read_text(encoding="utf-8"))
    rows = [r for r in json.loads(a.scorecard.read_text(encoding="utf-8"))["rows"] if r.get("backend") == a.backend]
    lines = check(rows, baseline)
    for x in lines:
        print(f"{x['status']} {x['set']} {x['metric']} {x['value']} {x['limit']}")
    return int(any(x["status"] == FAIL for x in lines))


if __name__ == "__main__":
    sys.exit(main())
