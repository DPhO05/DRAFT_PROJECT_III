"""G1 eval metrics (P2-T10): pure functions over labels and the proposals at the review gate.

A problem is {labels: [{step_idx, code, propagates_to}], proposals: [{step_idx, code}], items: {item_id: passed}}.
Steps a label lists in propagates_to are not required, but flagging them (any code) is not an addition.

Agent 00 (P8b): an answer is {id, expect, forbid, tools, tool_errors, unverified, stopped, text, warnings}; see
`passed_00`.
Agent 09 (P8b): a report is {key, period_kind, n_sentences, audit}; audit rows have a status (ok, rewritten, dropped).
"""

import math
import re
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


def _llm_code(m: dict, p: dict) -> str | None:
    """The LLM code paired with label mistake `m`: the label's own code if proposed at its step, else the first one;
    None when the LLM proposed nothing there."""
    codes = [x["code"] for x in p["proposals"] if x["step_idx"] == m["step_idx"]]
    return m["code"] if m["code"] in codes else codes[0] if codes else None


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
            code = _llm_code(m, p)
            if code is None:
                dropped += 1
            else:
                pairs.append((m["code"], code))
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


def quoted(evidence: str, text: str) -> bool:
    """The evidence is not empty and sits in the text, whitespace runs collapsed on both sides."""
    ev = " ".join(evidence.split())
    return bool(ev) and ev in " ".join(text.split())


def components(problems: list[dict]) -> dict:
    """One run of G1, agent by agent. Problems also carry steps {idx: latex}, score, max_score, evidence
    {item_id: latex} of the passed items, flags [type], and proposals with evidence_latex and verdict."""
    ev02 = [quoted(e, "\n".join(p["steps"].values())) for p in problems for e in p["evidence"].values()]
    ev03 = [quoted(x["evidence_latex"], p["steps"].get(x["step_idx"], "")) for p in problems for x in p["proposals"]]
    clean = [p for p in problems if not p["labels"]]
    full = [p for p in clean if p["score"] is not None and p["score"] == p["max_score"]]  # no lane: score None
    confusion: dict[str, dict[str, int]] = {}
    right, wrong = [], []
    for p in problems:
        at = {m["step_idx"] for m in p["labels"]}
        spread = at | {s for m in p["labels"] for s in m["propagates_to"]}
        for m in p["labels"]:
            if (code := _llm_code(m, p)) is not None:
                row = confusion.setdefault(m["code"], {})
                row[code] = row.get(code, 0) + 1
        right += [x["verdict"] == "agree" for x in p["proposals"] if x["step_idx"] in at]
        wrong += [x["verdict"] == "agree" for x in p["proposals"] if x["step_idx"] not in spread]
    return {
        "evidence_02": _rate(sum(ev02), len(ev02)),
        "evidence_03": _rate(sum(ev03), len(ev03)),
        "flags": dict(Counter(f for p in problems for f in p["flags"])),
        "clean_full_marks": _rate(len(full), len(clean)),
        "clean_flagged": _rate(sum(bool(p["proposals"]) for p in clean), len(clean)),
        "confusion": confusion,
        "agree_on_right": _rate(sum(right), len(right)),
        "agree_on_wrong": _rate(sum(wrong), len(wrong)),
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


_SHOWN_09 = re.compile(r"F\d\d|HS-\d\d|\d[A-Z]{2}-[A-Z0-9]+-\d{3}|%")  # fact id, student code, bank ref, percent
FLAGS_09 = ("number", "no_fact", "tone", "percent", "empty")


def text_ok_09(r: dict) -> bool:
    """No shown sentence holds a fact id, student code, bank ref or percent sign."""
    return not any(_SHOWN_09.search(s) for s in r.get("sentences", []))


def passed_09(r: dict) -> bool:
    """No draft sentence dropped, the sentence count fits its period, the text is clean, no leak, at most 2 calls."""
    lo, hi = SENTENCES[r["period_kind"]]
    return (
        all(a["status"] != "dropped" for a in r["audit"])
        and lo <= r["n_sentences"] <= hi
        and text_ok_09(r)
        and r.get("leaks", 0) == 0
        and r.get("model_calls", 1) <= 2
    )


def score_09(reports: list[dict]) -> dict:
    """One run of agent 09 over the periods that finished. Percentages are of audit rows (draft sentences)."""
    rows = [a["status"] for r in reports for a in r["audit"]]
    return {
        "n_reports": len(reports),
        "draft_flagged_pct": _rate(100 * sum(x != "ok" for x in rows), len(rows)),
        "dropped_pct": _rate(100 * rows.count("dropped"), len(rows)),
        "passed": _rate(sum(map(passed_09, reports)), len(reports)),
        "flags": {f: sum(a.get("flag") == f for r in reports for a in r["audit"]) for f in FLAGS_09},
    }


def passed_01(a: dict) -> bool:
    """The right problem (a low_match flag for one outside the bank), in one model call, no ref off the list."""
    return (
        a["ref"] == a["expect_ref"]
        and (a["expect_ref"] is not None or a["low_match"])
        and a["model_calls"] == 1
        and a["bad_candidates"] == 0
    )


def score_01(answers: list[dict]) -> dict:
    """One run of agent 01. hit and mrr are over the problems that are in the bank."""
    found = [a for a in answers if a["expect_ref"] is not None]
    ranks = [next((i for i, c in enumerate(a["candidates"], 1) if c["ref"] == a["expect_ref"]), 0) for a in found]
    low = [a for a in answers if a["low_match"]]
    return {
        "n_tasks": len(answers),
        "hit_at_1": _rate(sum(r == 1 for r in ranks), len(found)),
        "hit_at_3": _rate(sum(0 < r <= 3 for r in ranks), len(found)),
        "mrr": _rate(sum(1 / r for r in ranks if r), len(found)),
        "low_match_precision": _rate(sum(a["expect_ref"] is None for a in low), len(low)),
        "passed": _rate(sum(map(passed_01, answers)), len(answers)),
    }


def passed_04(a: dict) -> bool:
    """The expected verdict (and the expected code for wrong_code), in one model call."""
    return (
        a["verdict"] == a["expect"]
        and (a["expect"] != "wrong_code" or a["suggested_code"] == a["expect_code"])
        and a["model_calls"] == 1
    )


def score_04(answers: list[dict]) -> dict:
    """One run of agent 04. recall_disagree: of the claims that are wrong, how many 04 refuses."""
    dis = [a for a in answers if a["expect"] == "disagree"]
    kinds = ("agree", "disagree", "wrong_code")
    return {
        "n_tasks": len(answers),
        "accuracy": _rate(sum(a["verdict"] == a["expect"] for a in answers), len(answers)),
        "recall_disagree": _rate(sum(a["verdict"] == "disagree" for a in dis), len(dis)),
        "empty": sum(a["verdict"] is None for a in answers),
        "confusion": {
            e: {v: sum(a["expect"] == e and a["verdict"] == v for a in answers) for v in kinds}
            | {"none": sum(a["expect"] == e and a["verdict"] is None for a in answers)}
            for e in kinds
        },
        "passed": _rate(sum(map(passed_04, answers)), len(answers)),
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


_STATEMENT = re.compile(r"Đề:\n(.*?)\n\nLời giải mẫu:", re.S)


def trajectory(rows: list[dict], budgets: dict[str, int] | None) -> dict:
    """Calls per thread (run, thread_id) against budgets["<run>:<thread_id>"], retries, schema errors and the 02, 03,
    04 order per lane. A row has no lane field: a lane is the rows of a thread that share one `Đề:` block."""
    threads: dict[tuple, list[dict]] = {}
    lanes: dict[tuple, list[str]] = {}
    for r in rows:
        if not r.get("thread_id"):
            continue
        key = (r["run"], r["thread_id"])
        threads.setdefault(key, []).append(r)
        if m := _STATEMENT.search(r["user"]):
            lanes.setdefault((*key, m[1]), []).append(r["agent"])
    over = None if budgets is None else sum(
        len(v) > budgets[f"{k[0]}:{k[1]}"] for k, v in threads.items() if f"{k[0]}:{k[1]}" in budgets
    )  # fmt: skip
    return {
        "threads": len(threads),
        "calls_max": max(map(len, threads.values()), default=0),
        "by_agent": dict(sorted(Counter(r["agent"] for r in rows if r.get("thread_id")).items())),
        "retries": sum(r["result"] == "retry" for r in rows),
        "schema_errors": sum(r["result"] == "schema_error" for r in rows),
        "over_budget": over,
        "order_ok": _rate(sum(a == sorted(a) for a in lanes.values()), len(lanes)),
    }


def passed_02r(a: dict) -> bool:
    """A draft with items r1, r2, ... in order, every point above 0, max_score the sum, in one model call."""
    d = a["draft"]
    return (
        d is not None
        and [i["item_id"] for i in d["items"]] == [f"r{k}" for k in range(1, len(d["items"]) + 1)]
        and all(i["points"] > 0 for i in d["items"])
        and d["max_score"] == sum(i["points"] for i in d["items"])
        and a["model_calls"] == 1
    )


def score_02r(answers: list[dict]) -> dict:
    """One run of the 02 rubric draft."""
    return {"n_tasks": len(answers), "passed": _rate(sum(map(passed_02r, answers)), len(answers))}


def passed_08(a: dict) -> bool:
    """A full sheet (or a short one that warns) with none of the refs the profile must never get."""
    return bool(len(a["refs"]) == a["n"] or a["warnings"]) and not set(a["must_not"]) & set(a["refs"])


def score_08(answers: list[dict]) -> dict:
    """One run of the 08 ranking: mean precision and recall of the sheet against the labelled refs."""
    hit = [(len(set(a["refs"]) & set(a["relevant"])), a) for a in answers]
    return {
        "n_tasks": len(answers),
        "p_at_n": _rate(sum(h / a["n"] for h, a in hit), len(answers)),
        "recall_at_n": _rate(sum(h / len(a["relevant"]) for h, a in hit), len(answers)),
        "must_not_hits": sum(len(set(a["must_not"]) & set(a["refs"])) for a in answers),
        "passed": _rate(sum(map(passed_08, answers)), len(answers)),
    }
