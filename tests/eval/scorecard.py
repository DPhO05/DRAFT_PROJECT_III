"""Scorecard: newest result file per (set, backend) as one row each (plan contract C2).

uv run python tests/eval/scorecard.py [--results data/eval/results] [--out data/eval/scorecards] [--backend fake]
                                      [--baseline tests/eval/baseline.json] [--with-tests]
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = Path(__file__).with_name("workflows.json")
if not __package__:  # run as a script: make `tests.*` importable
    sys.path.insert(0, str(ROOT))

KEY = {
    "g1": ["recall", "precision"], "00": ["tools_ok", "args_ok"], "09": ["dropped_pct"], "g5": ["dropped_pct"],
    "01": ["hit_at_1", "mrr"], "04": ["accuracy", "recall_disagree"], "02r": [], "08": ["p_at_n", "recall_at_n"],
}  # fmt: skip


def _num(x) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def row(res: dict, name: str, baseline_rows: dict | None = None) -> dict:
    """Legacy files (no set, tally, extra) give a row with None where the number is unknown."""
    m = res.get("metrics", {})
    runs = m.get("per_run", [])
    tally = m.get("tally") or {}
    calls = res.get("calls", {})
    target = res.get("target") or res.get("agent") or "g1"
    flat = {k: _mean(v) for k in {k for r in runs for k in r} if (v := [r[k] for r in runs if _num(r.get(k))])}
    flat |= {k: v for k, v in m.get("extra", {}).items() if _num(v)}
    first = runs[0] if runs else {}
    tasks = tally.get("tasks", next((first[k] for k in ("n_problems", "n_questions", "n_reports") if k in first), None))
    task_pass = tally.get("task_pass")
    base = (baseline_rows or {}).get(res.get("set") or f"{target}-dev")
    kinds = None
    if base is not None and task_pass is not None:
        was = base.get("task_pass", {})
        regression = sum(bool(was.get(t)) for t in task_pass)
        kinds = {"regression": regression, "capability": len(task_pass) - regression}
    return {
        "set": res.get("set") or f"{target}-dev", "target": target, "split": res.get("split"),
        "source": res.get("source"), "backend": res.get("backend"), "created": res.get("created"), "file": name,
        "models": res.get("models"), "prompt_versions": res.get("prompt_versions"),
        "subset": res.get("subset"), "n_tasks": tasks, "k": res.get("runs"),
        "success": m.get("success"),
        "pass_k": m.get("pass_k", (m.get("stability") or {}).get("pass_k")),
        "trials_passed": tally.get("trials_passed"), "trials": tally.get("trials"),
        "tasks_passed": tally.get("tasks_passed"), "tasks": tasks, "task_pass": task_pass,
        "metrics": flat,
        "calls": calls.get("logged"), "usd": calls.get("usd"),
        "tokens_in": calls.get("tokens_in"), "tokens_out": calls.get("tokens_out"),
        "ms_p50": calls.get("ms_p50"), "ms_p95": calls.get("ms_p95"), "error_rate": calls.get("error_rate"),
        "kind_counts": kinds,
    }  # fmt: skip


def build(results: Path, *, backend: str | None = None, baseline_rows: dict | None = None) -> list[dict]:
    newest: dict[tuple, dict] = {}
    for f in sorted(results.glob("*.json")):
        r = row(json.loads(f.read_text(encoding="utf-8")), f.name, baseline_rows)
        if backend and r["backend"] != backend:
            continue
        k = (r["set"], r["backend"], tuple(r["subset"] or ()))  # a partial run sits beside the full row
        if k not in newest or (r["created"] or "") >= (newest[k]["created"] or ""):
            newest[k] = r
    return sorted(newest.values(), key=lambda r: (r["set"], r["backend"] or "", r["subset"] or []))


def _count(out: str, word: str) -> int:
    return sum(int(n) for n in re.findall(rf"(\d+) (?:{word})", out.strip().splitlines()[-1] if out.strip() else ""))


def code_rows(created: str) -> list[dict]:
    """One row per workflow target: its listed pytest ids run once per level; no model call, so calls and usd are 0."""
    levels: dict[str, dict[str, set[str]]] = {}
    for w in json.loads(WORKFLOWS.read_text(encoding="utf-8")):
        levels.setdefault(w["target"], {}).setdefault(w["level"], set()).update(w["tests"])
    rows = []
    for target, by_level in levels.items():
        passed = total = 0
        share = {}
        for level, ids in by_level.items():
            cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *sorted(ids)]
            out = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT).stdout
            ok, n = _count(out, "passed"), _count(out, "passed") + _count(out, "failed|errors?")
            passed, total, share[level] = passed + ok, total + n, ok / n if n else 0.0
        rate = passed / total if total else 0.0
        rows.append({
            "set": f"{target}-tests", "target": target, "split": "dev", "source": "synthetic", "backend": "code",
            "created": created, "file": None, "models": None, "prompt_versions": None,
            "subset": None, "n_tasks": total, "k": 1, "success": rate, "pass_k": rate,
            "trials_passed": None, "trials": None, "tasks_passed": passed, "tasks": total, "task_pass": None,
            "metrics": share, "calls": 0, "usd": 0,
            "tokens_in": None, "tokens_out": None, "ms_p50": None, "ms_p95": None, "error_rate": None,
            "kind_counts": None,
        })  # fmt: skip
    return rows


def _frac(n, total, rate) -> str:
    if n is not None and total:
        return f"{n}/{total}"
    return "-" if rate is None else f"{rate:.3f}"


def _fmt(x) -> str:
    return "-" if x is None else str(x) if isinstance(x, int) else f"{x:.3f}"


def table(rows: list[dict]) -> str:
    head = ["set", "target", "backend", "k", "n", "success", "pass_k", "key metrics", "calls", "usd", "model"]
    out = [head]
    for r in rows:
        n = f"{r['n_tasks']}*" if r.get("subset") else str(r["n_tasks"])
        shown = KEY.get(r["target"], []) + ["name_leaks"]  # a missing key prints "-", never 0
        mt = " ".join(f"{k}={_fmt(r['metrics'].get(k))}" for k in shown)
        models = sorted({m for v in (r["models"] or {}).values() for m in v})
        out.append([
            r["set"], r["target"], str(r["backend"]), str(r["k"]), n,
            _frac(r["trials_passed"], r["trials"], r["success"]),
            _frac(r["tasks_passed"], r["tasks"], r["pass_k"]),
            mt, str(r["calls"]), _fmt(r["usd"]), ",".join(models) or "-",
        ])  # fmt: skip
    return "\n".join("| " + " | ".join(c) + " |" for c in out[:1] + [["---"] * len(head)] + out[1:])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--results", type=Path, default=ROOT / "data" / "eval" / "results")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "eval" / "scorecards")
    ap.add_argument("--backend", default=None)
    ap.add_argument("--baseline", type=Path, default=ROOT / "tests" / "eval" / "baseline.json")
    ap.add_argument("--with-tests", action="store_true", help="add one <target>-tests row per workflow target")
    a = ap.parse_args(argv)
    base = None
    if a.baseline.exists():
        base = json.loads(a.baseline.read_text(encoding="utf-8")).get("real", {}).get("rows")
    rows = build(a.results, backend=a.backend, baseline_rows=base)
    now = datetime.now(UTC)
    if a.with_tests:
        rows = sorted(rows + code_rows(f"{now:%Y-%m-%dT%H:%M:%SZ}"), key=lambda r: (r["set"], r["backend"] or ""))
    a.out.mkdir(parents=True, exist_ok=True)
    f = a.out / f"{now:%Y%m%dT%H%M%SZ}.json"
    f.write_text(
        json.dumps({"created": f"{now:%Y-%m-%dT%H:%M:%SZ}", "rows": rows}, ensure_ascii=False), encoding="utf-8"
    )
    print(table(rows))
    print(f"→ {f}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
