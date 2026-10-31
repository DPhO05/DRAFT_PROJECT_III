"""Elo skill update, repeated-misconception log and level words (P4-T01..T03); pure, JSON-safe."""

import math

from tutor.config import RESOLVE_STREAK, THETA0, K


def expected(theta: float, delta: float) -> float:
    """P(correct) = 1 / (1 + e^-(theta - delta))."""
    return 1 / (1 + math.exp(-(theta - delta)))


def update(theta: float, delta: float, x: int) -> tuple[float, float]:
    """(p, theta_after) for one outcome x in {0, 1}."""
    p = expected(theta, delta)
    return p, theta + K * (x - p)


def level(theta: float) -> str:
    if theta < -0.5:
        return "chưa vững"
    return "vững" if theta > 0.5 else "đang hình thành"


def trend(d_theta: float) -> str:
    d = round(d_theta, 6)  # 0.05 must not fall to 0.0499999
    if d >= 0.05:
        return "tiến bộ"
    return "cần ôn" if d <= -0.05 else "giữ"


def difficulty_word(delta: float | None, approved: bool) -> str:
    if delta is None or not approved:
        return "chưa đặt mức"
    if delta < -0.3:
        return "dễ"
    return "khó" if delta > 0.3 else "vừa"


def empty_prior() -> dict:
    return {"skills": [], "miscon": [], "prev_codes": []}


def profile(prior: dict, attempts: list[dict], held_on: str) -> dict:
    """Replay one session over `prior`; `attempts` sorted by seq, mistakes already filtered."""
    skills = {s["kc_id"]: dict(s) for s in prior["skills"]}
    miscon = {(m["code"], m["kc_id"]): dict(m) for m in prior["miscon"]}
    known = set(miscon)
    events, theta_first = [], {}
    hit, touched, resolved, codes = set(), set(), set(), set()
    for a in attempts:
        delta = a["delta"] or 0  # NULL delta -> 0 (C-19)
        wrong = {m["kc_id"] for m in a["mistakes"] if m["kc_id"] is not None}
        codes.update(m["code"] for m in a["mistakes"])
        for key in sorted({(m["code"], m["kc_id"]) for m in a["mistakes"] if m["kc_id"] is not None}):
            if key in miscon:
                row = miscon[key]
                row.update(last_seen=held_on, count=row["count"] + 1, resolved_at=None)
            else:
                miscon[key] = {
                    "code": key[0],
                    "kc_id": key[1],
                    "first_seen": held_on,
                    "last_seen": held_on,
                    "count": 1,
                    "resolved_at": None,
                }
            hit.add(key)
            touched.add(key)
            resolved.discard(key)
        for kc in sorted(set(a["kcs"]) | wrong):
            s = skills.setdefault(kc, {"kc_id": kc, "theta": float(THETA0), "n_attempts": 0, "correct_streak": 0})
            x = 0 if kc in wrong else 1
            p, theta_after = update(s["theta"], delta, x)
            events.append(
                {
                    "seq": a["seq"],
                    "kc_id": kc,
                    "outcome": x,
                    "p_expected": p,
                    "theta_before": s["theta"],
                    "theta_after": theta_after,
                    "delta": delta,
                }
            )
            theta_first.setdefault(kc, s["theta"])
            s.update(
                theta=theta_after,
                n_attempts=s["n_attempts"] + 1,
                correct_streak=s["correct_streak"] + 1 if x else 0,
            )
            if s["correct_streak"] >= RESOLVE_STREAK:
                for key, row in miscon.items():
                    if key[1] == kc and row["resolved_at"] is None:
                        row["resolved_at"] = held_on
                        touched.add(key)
                        resolved.add(key)

    prev = set(prior["prev_codes"])
    touched_kcs = sorted(theta_first)
    return {
        "events": events,
        "skills": [skills[kc] for kc in touched_kcs],
        "miscon": [miscon[key] for key in sorted(touched)],
        "kcs": [
            {
                "kc_id": kc,
                "theta_before": theta_first[kc],
                "theta_after": skills[kc]["theta"],
                "d_theta": skills[kc]["theta"] - theta_first[kc],
                "level_before": level(theta_first[kc]),
                "level_after": level(skills[kc]["theta"]),
                "trend": trend(skills[kc]["theta"] - theta_first[kc]),
            }
            for kc in touched_kcs
        ],
        "miscon_change": {
            "new": [list(k) for k in sorted(hit - known)],
            "again": [list(k) for k in sorted(hit & known)],
            "resolved": [list(k) for k in sorted(resolved)],
        },
        "codes": {"repeat": sorted(codes & prev), "new": sorted(codes - prev), "gone": sorted(prev - codes)},
        "after": {
            "skills": [skills[kc] for kc in sorted(skills)],
            "miscon": [miscon[key] for key in sorted(miscon)],
            "prev_codes": sorted(codes),
        },
    }
