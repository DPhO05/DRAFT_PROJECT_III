"""G1 eval metrics (P2-T10): pure functions over labels and the proposals at the review gate.

A problem is {labels: [{step_idx, code, propagates_to}], proposals: [{step_idx, code}], items: {item_id: passed}}.
Steps a label lists in propagates_to are not required, but flagging them (any code) is not an addition.
"""

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
