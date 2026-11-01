"""Pick the next problems for a student from Elo state (P6-T04): review / zpd / challenge buckets. SELECT only."""

import re
import sqlite3
from datetime import date, timedelta

from tutor.services import elo, search

BUCKETS = ("review", "zpd", "challenge")
# first skill of a problem by (step_idx, kc_id): its main skill (C-45)
_MAIN = "(SELECT kc_id FROM problem_kc WHERE problem_id = p.id ORDER BY step_idx, kc_id LIMIT 1)"


def split(n: int, ratios: dict[str, float]) -> dict[str, int]:
    """Largest remainder; a tie goes to the earlier of review, zpd, challenge."""
    total = sum(ratios.values()) if set(ratios) == set(BUCKETS) else 0
    if total <= 0 or any(not 0 <= r <= 1 for r in ratios.values()):
        raise ValueError("Tỉ lệ ôn / vừa sức / thử thách: mỗi số từ 0 đến 1, tổng lớn hơn 0")
    quota = {b: round(n * ratios[b] / total, 9) for b in BUCKETS}
    out = {b: int(quota[b]) for b in BUCKETS}
    rest = {b: round(quota[b] - out[b], 9) for b in BUCKETS}
    for b in sorted(BUCKETS, key=lambda b: -rest[b])[: n - sum(out.values())]:
        out[b] += 1
    return out


def _repeats(conn, student_id: int) -> dict[int, tuple[str, int, int]]:
    """kc_id -> (words of its most repeated open mistake, its count, count over all open mistakes of the skill)."""
    out: dict[int, tuple[str, int, int]] = {}
    for kc, words, count in conn.execute(
        "SELECT l.kc_id, e.description, l.count FROM misconception_log l JOIN error_code e ON e.code = l.code"
        " WHERE l.student_id = ? AND l.resolved_at IS NULL ORDER BY l.count DESC, l.last_seen DESC, l.code",
        (student_id,),
    ):
        if kc in out:
            out[kc] = (*out[kc][:2], out[kc][2] + count)
        else:
            words = re.sub(r"\s*\([^()]*\)\s*$", "", words)
            out[kc] = (words[:1].lower() + words[1:], count, count)
    return out


def rank_problems(
    conn: sqlite3.Connection,
    student_id: int,
    n: int,
    *,
    reco: dict,
    today: date,
    ratios: dict | None = None,
) -> dict:
    """Up to `n` bank problems for the student, each in one bucket with a one-line reason."""
    need = split(n, ratios or reco["ratios"])
    lo, hi = reco["zpd_window"]
    cutoff = (today - timedelta(days=reco["no_repeat_days"])).isoformat()
    theta = dict(conn.execute("SELECT kc_id, theta FROM skill_state WHERE student_id = ?", (student_id,)))
    repeats = _repeats(conn, student_id)
    prereqs: dict[int, list[int]] = {}
    for kc, pre in conn.execute("SELECT kc_id, prereq_id FROM kc_prereq"):
        prereqs.setdefault(kc, []).append(pre)
    pool = [
        {"id": pid, "kc": kc, "delta": delta, "gap": theta.get(kc, 0.0) - delta}
        for pid, delta, kc in conn.execute(
            f"SELECT p.id, COALESCE(p.delta, 0), {_MAIN} FROM problem p"
            " WHERE EXISTS (SELECT 1 FROM rubric r WHERE r.problem_id = p.id)"
            " AND NOT EXISTS (SELECT 1 FROM attempt_current a JOIN session s ON s.id = a.session_id"
            "  WHERE a.problem_id = p.id AND s.student_id = ? AND s.held_on >= ?)"
            " ORDER BY p.ref",
            (student_id, cutoff),
        )
        if kc is not None
    ]
    chosen: list[dict] = []
    taken: set[int] = set()
    kcs: set[int] = set()  # main skills already on the sheet: a new one wins inside a bucket

    def pick(bucket: str, k: int) -> None:
        for _ in range(k):
            left = [c for c in pool if c["id"] not in taken]
            if bucket == "review":
                cand, order = [c for c in left if c["kc"] in repeats], lambda c: abs(c["gap"])
            elif bucket == "zpd":
                cand, order = [c for c in left if lo <= c["gap"] <= hi], lambda c: abs(c["gap"])
            else:
                # S5: a challenge needs every prerequisite skill at theta >= 0 (missing = 0)
                ok = [c for c in left if all(theta.get(p, 0.0) >= 0 for p in prereqs.get(c["kc"], []))]
                cand, order = [c for c in ok if c["gap"] < lo], lambda c: -c["gap"]
                if not cand:
                    cand, order = ok, lambda c: -c["delta"]
            if not cand:
                return
            best = min(cand, key=lambda c: (c["kc"] in kcs, order(c)))
            chosen.append(best | {"bucket": bucket, "fallback": bucket == "challenge" and best["gap"] >= lo})
            taken.add(best["id"])
            kcs.add(best["kc"])

    for b in BUCKETS:
        pick(b, need[b])
    for b in ("zpd", "review", "challenge"):
        pick(b, n - len(chosen))
    chosen.sort(key=lambda c: BUCKETS.index(c["bucket"]))

    cards = {c["id"]: c for c in search.items_by_id(conn, [c["id"] for c in chosen])}
    items = []
    for c in chosen:
        card = cards[c["id"]]
        name = card["kcs"][0]["name"]
        if c["bucket"] == "review":
            words, count, total = repeats[c["kc"]]
            more = f", cả kỹ năng {total} lần" if total != count else ""
            reason = f"Ôn lại “{name}”: còn {words} ({count} lần){more}."
        elif c["bucket"] == "zpd":
            reason = f"Vừa sức: luyện “{name}” ({elo.level(theta.get(c['kc'], 0.0))})."
        elif c["fallback"]:
            reason = f"Thử thách: “{name}” — bài khó nhất còn lại trong ngân hàng."
        else:
            reason = f"Thử thách: “{name}” — đã vững phần nền."
        items.append(
            {
                "problem_id": c["id"],
                "ref": card["ref"],
                "kc_id": c["kc"],
                "bucket": c["bucket"],
                "reason": reason,
                "level": card["level"],
                "kcs": [k["name"] for k in card["kcs"]],
                "statement_latex": card["statement_latex"],
            }
        )
    warnings = []
    if len(items) < n:
        warnings.append(f"Chỉ tìm được {len(items)} bài hợp")
    if len(kcs) < min(reco["min_kc_mix"], len(items)):
        warnings.append(f"Phiếu chỉ có {len(kcs)} kỹ năng")
    return {
        "items": items,
        "counts": {b: sum(i["bucket"] == b for i in items) for b in BUCKETS},
        "warnings": warnings,
    }
