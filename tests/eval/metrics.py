"""G1 eval metrics (P2-T10): pure functions over labels and the proposals at the review gate.

A problem is {labels: [{step_idx, code, propagates_to}], proposals: [{step_idx, code}], items: {item_id: passed}}.
Steps a label lists in propagates_to are not required, but flagging them (any code) is not an addition.

Agent 00 (P8b): an answer is {id, expect, forbid, tools, tool_errors, unverified, stopped, text, warnings}; see
`passed_00`.
Agent 09 (P8b): a report is {key, period_kind, n_sentences, audit}; audit rows have a status (ok, rewritten, dropped).
"""

import math
from collections import Counter


def _rate(a: int, b: int) -> float | None:
    return a / b if b else None


def first_wrong_step(label_steps: list[int], llm_steps: list[int]) -> bool:
    """Earliest flagged step matches; a clean problem is right only if the LLM flags nothing."""
    return min(label_steps, default=None) == min(llm_steps, default=None)


def cohen_kappa(pairs: list[tuple[str, str]]) -> float | None:
    """(teacher code, LLM code) pairs. None with no pairs or pe = 1 (both sides one same code: 0/0)."""
    n = len(pairs)
    a, b = Counter(x for x, _ in pairs), Counter(y for _, y in pairs)
    chance = sum(a[k] * b[k] for k in a)
    if not n or chance == n * n:
        return None
    po, pe = sum(x == y for x, y in pairs) / n, chance / (n * n)
    return (po - pe) / (1 - pe)


def _fws(p: dict) -> bool:
    return first_wrong_step([m["step_idx"] for m in p["labels"]], [x["step_idx"] for x in p["proposals"]])


def score(problems: list[dict]) -> dict:
    """One run.

    precision / recall: on sets of wrong steps per problem. drop / add: on label mistakes / proposals.
    kappa: label mistakes whose step the LLM flagged; the LLM code is the label's code if proposed there, else the
    first one proposed at that step.
    """
    found = wrong = ok = flagged = dropped = added = n_props = 0
    pairs = []
    for p in problems:
        steps = {m["step_idx"] for m in p["labels"]}
        allowed = steps | {s for m in p["labels"] for s in m["propagates_to"]}
        got = {x["step_idx"] for x in p["proposals"]}
        found, wrong = found + len(got & steps), wrong + len(steps)
        ok, flagged = ok + len(got & allowed), flagged + len(got)
        for m in p["labels"]:
            codes = [x["code"] for x in p["proposals"] if x["step_idx"] == m["step_idx"]]
            if codes:
                pairs.append((m["code"], m["code"] if m["code"] in codes else codes[0]))
            else:
                dropped += 1
        added += sum(x["step_idx"] not in allowed for x in p["proposals"])
        n_props += len(p["proposals"])
    n_labels = sum(len(p["labels"]) for p in problems)
    return {
        "n_problems": len(problems),
        "n_labels": n_labels,
        "n_proposals": n_props,
        "n_pairs": len(pairs),
        "first_wrong_step_acc": _rate(sum(map(_fws, problems)), len(problems)),
        "precision": _rate(ok, flagged),
        "recall": _rate(found, wrong),
        "kappa": cohen_kappa(pairs),
        "drop_rate": _rate(dropped, n_labels),
        "add_rate": _rate(added, n_props),
    }


def stability(runs: list[dict[str, dict]]) -> dict:
    """runs: {problem key: problem} per run. A problem missing from a run (failed thread) counts as changed and
    not passed. pass_k: share of problems whose first wrong step is right in every run (pass^k, k = runs)."""
    keys = set().union(*runs)
    items = {(k, i) for r in runs for k, p in r.items() for i in p["items"]}
    changed = sum(len({r[k]["items"].get(i) if k in r else None for r in runs}) > 1 for k, i in items)
    passed = sum(all(k in r and _fws(r[k]) for r in runs) for k in keys)
    pct = _rate(100 * changed, len(items))
    return {"runs": len(runs), "n_items": len(items), "items_changed_pct": pct, "n_problems": len(keys),
            "pass_k": _rate(passed, len(keys))}  # fmt: skip


def _tools_ok(a: dict) -> bool:
    """Expected tools in order (others may sit between), none forbidden ("*" = any), no tool error unless allowed."""
    forbidden = bool(a["tools"]) if "*" in a["forbid"] else bool(set(a["forbid"]) & set(a["tools"]))
    calls = iter(a["tools"])
    return (
        all(name in calls for name in a["expect"])
        and not forbidden
        and (a["tool_errors"] == 0 or a.get("allow_tool_error", False))
    )


def _arg_match(want, got) -> bool:
    if isinstance(want, list):
        return isinstance(got, list) and {str(x).upper() for x in want} == {str(x).upper() for x in got}
    if isinstance(want, str):
        return isinstance(got, str) and want.lower() in got.lower()
    return want == got


def args_ok(a: dict) -> bool:
    """The first call of each expected tool carries the expected arguments (lists as sets, strings contained)."""
    for tool, want in a.get("expect_args", {}).items():
        call = next((c for c in a.get("calls", []) if c["name"] == tool), None)
        if call is None or not all(k in call["args"] and _arg_match(v, call["args"][k]) for k, v in want.items()):
            return False
    return True


def args_fit(call: dict, defs: list[dict]) -> bool:
    """The call names a defined tool, has every required argument, no unknown one, and enum values in range."""
    schema = next((d["input_schema"] for d in defs if d["name"] == call["name"]), None)
    if schema is None:
        return False
    props, args = schema.get("properties", {}), call["args"]
    return (
        all(k in args for k in schema.get("required", []))
        and all(k in props for k in args)
        and all(args[k] in p["enum"] for k, p in props.items() if k in args and "enum" in p)
    )


def rules_ok(a: dict) -> bool:
    """No student name in the trace, no error code shown, every call fits its tool, no claim of saving, and the
    task's own limits: approval, starts, calls per tool, model calls, reply text."""
    text = a["text"].strip()
    return (
        a.get("leaks", 0) == 0
        and a.get("codes_shown", 0) == 0
        and a.get("schema_errors", 0) == 0
        and "đã lưu" not in a["text"].lower()
        and bool(a.get("approvals")) == bool(a.get("expect_approval"))
        and ("expect_starts" not in a or a["starts"] == a["expect_starts"])
        and all(sum(c["name"] == t for c in a["calls"]) <= n for t, n in a.get("max_calls", {}).items())
        and ("max_model_calls" not in a or a["model_calls"] <= a["max_model_calls"])
        and text == a.get("expect_text", text)
        and ("expect_any" not in a or any(x.lower() in text.lower() for x in a["expect_any"]))
    )


def passed_00(a: dict) -> bool:
    """Right tools and arguments, the rules kept, no unverified number, the loop not cut off, and a reply that says
    something.

    A max_tokens cut is not `stopped` (orchestrator.py), so an empty reply is caught here.
    """
    return (
        _tools_ok(a)
        and args_ok(a)
        and rules_ok(a)
        and a["unverified"] == 0
        and a["stopped"] is None
        and (bool(a["text"].strip()) or bool(a.get("card_only") and a.get("cards", 0) > 0))
    )


def score_00(answers: list[dict]) -> dict:
    """One run of agent 00 over the questions that finished."""
    n, asked = len(answers), [a for a in answers if "approval" in a]
    return {
        "n_questions": n,
        "tools_ok": _rate(sum(map(_tools_ok, answers)), n),
        "unverified_pct": _rate(100 * sum(a["unverified"] > 0 for a in answers), n),
        "args_ok": _rate(sum(map(args_ok, answers)), n),
        "passed": _rate(sum(map(passed_00, answers)), n),
        "approval_ok": _rate(sum(map(passed_00, asked)), len(asked)),
    }


SENTENCES = {"day": (2, 3), "week": (3, 5), "month": (3, 5)}  # reporter.INSTRUCTIONS


def passed_09(r: dict) -> bool:
    """No draft sentence dropped, and the shown report has the sentence count its period asks for."""
    lo, hi = SENTENCES[r["period_kind"]]
    return all(a["status"] != "dropped" for a in r["audit"]) and lo <= r["n_sentences"] <= hi


def score_09(reports: list[dict]) -> dict:
    """One run of agent 09 over the periods that finished. Percentages are of audit rows (draft sentences)."""
    rows = [a["status"] for r in reports for a in r["audit"]]
    return {
        "n_reports": len(reports),
        "draft_flagged_pct": _rate(100 * sum(x != "ok" for x in rows), len(rows)),
        "dropped_pct": _rate(100 * rows.count("dropped"), len(rows)),
        "passed": _rate(sum(map(passed_09, reports)), len(reports)),
    }


def pass_k(runs: list[dict[str, bool]]) -> float | None:
    """runs: {question id: passed} per run. A question missing from a run counts as failed (pass^k, k = runs)."""
    keys = set().union(*runs)
    return _rate(sum(all(r.get(k, False) for r in runs) for k in keys), len(keys))


def g1_passed(run: dict[str, dict]) -> dict[str, bool]:
    """One G1 run as {problem key: first wrong step found}."""
    return {k: _fws(p) for k, p in run.items()}


def tally(runs: list[dict[str, bool]]) -> dict:
    """runs: {task id: passed} per run. A task missing from a run failed. success counts trials, pass_k tasks."""
    keys = sorted(set().union(*runs))
    task_pass = {k: all(r.get(k, False) for r in runs) for k in keys}
    trials = len(runs) * len(keys)
    passed = sum(r.get(k, False) for r in runs for k in keys)
    return {
        "trials_passed": passed,
        "trials": trials,
        "tasks_passed": sum(task_pass.values()),
        "tasks": len(keys),
        "success": _rate(passed, trials),
        "pass_k": _rate(sum(task_pass.values()), len(keys)),
        "task_pass": task_pass,
    }


def percentile(xs: list[float], p: float) -> float | None:
    """Nearest rank."""
    return sorted(xs)[math.ceil(p / 100 * len(xs)) - 1] if xs else None


def usage(rows: list[dict]) -> dict:
    """Calls, cost, tokens and latency of logged rows (cost_usd comes from llm.iter_log)."""
    by_agent: dict[str, dict] = {}
    for r in rows:
        a = by_agent.setdefault(r["agent"], {"calls": 0, "usd": 0})
        a["calls"] += 1
        a["usd"] += r["cost_usd"]
    ms = [r["ms"] for r in rows]
    return {
        "logged": len(rows),
        "usd": round(sum(r["cost_usd"] for r in rows), 6),
        "tokens_in": sum(r["input_tokens"] + r["cache_read_tokens"] + r["cache_write_tokens"] for r in rows),
        "tokens_out": sum(r["output_tokens"] for r in rows),
        "ms_p50": percentile(ms, 50),
        "ms_p95": percentile(ms, 95),
        "error_rate": _rate(sum(r["result"] != "ok" for r in rows), len(rows)),
        "by_agent": {k: {"calls": v["calls"], "usd": round(v["usd"], 6)} for k, v in sorted(by_agent.items())},
    }
