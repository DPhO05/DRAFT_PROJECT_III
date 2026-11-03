"""Report facts by period (P7-T02, C-44): committed sessions only, each fact has a `fact_id`; same DB, same facts."""

import calendar
from datetime import date, timedelta

from tutor.config import student_code
from tutor.services import elo
from tutor.services.students import _rows, score_10

KINDS = ("day", "week", "month")
# committed sessions of :sid held in [:lo, :hi]
_IN = "s.student_id = :sid AND s.status = 'committed' AND s.held_on BETWEEN :lo AND :hi"


class NotReady(Exception):
    """The period has no committed session; `detail` = {reason, previous_start}."""

    def __init__(self, detail: dict):
        super().__init__(detail["reason"])
        self.detail = detail


def week_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _bounds(kind: str, day: date) -> tuple[date, date]:
    """The period of `kind` that contains `day`."""
    if kind == "day":
        return day, day
    if kind == "week":
        return week_of(day), week_of(day) + timedelta(days=6)
    return day.replace(day=1), day.replace(day=calendar.monthrange(day.year, day.month)[1])


def period(kind: str, start: str, today: date) -> tuple[date, date]:
    """(first day, last day); ValueError in words for a malformed period (R8)."""
    if kind not in KINDS:
        raise ValueError("Loại kỳ phải là ngày, tuần hoặc tháng (day / week / month)")
    try:
        day = date.fromisoformat(start)
    except ValueError:
        day = None
    if day is None or day.isoformat() != start:  # fromisoformat also takes 20261012 and 2026-W43-1
        raise ValueError("Ngày bắt đầu phải có dạng yyyy-mm-dd")
    lo, hi = _bounds(kind, day)
    if kind == "week" and lo != day:
        raise ValueError("Kỳ tuần phải bắt đầu vào thứ Hai")
    if kind == "month" and lo != day:
        raise ValueError("Kỳ tháng phải bắt đầu vào ngày 1")
    if day > today:
        raise ValueError("Ngày bắt đầu kỳ không được ở tương lai")
    return lo, hi


def _sessions(conn, sid: int, lo: date, hi: date) -> list[dict]:
    return _rows(
        conn,
        "SELECT s.id, s.held_on,"
        " COALESCE((SELECT sum(score) FROM attempt_current WHERE session_id = s.id), 0) AS score,"
        " COALESCE((SELECT sum(max_score) FROM attempt_current WHERE session_id = s.id), 0) AS max_score,"
        " (SELECT count(*) FROM attempt_current WHERE session_id = s.id) AS problems,"
        " (SELECT count(*) FROM mistake_current m JOIN attempt_current a ON a.id = m.attempt_id"
        "  WHERE a.session_id = s.id) AS mistakes"
        f" FROM session s WHERE {_IN} ORDER BY s.held_on, s.id",
        {"sid": sid, "lo": lo.isoformat(), "hi": hi.isoformat()},
    )


def _previous(conn, sid: int, kind: str, lo: date) -> tuple[date, date] | None:
    """The latest earlier period of the same kind with a committed session (for a day: the session just before)."""
    last = conn.execute(
        "SELECT held_on FROM session WHERE student_id = ? AND status = 'committed' AND held_on < ?"
        " ORDER BY held_on DESC LIMIT 1",
        (sid, lo.isoformat()),
    ).fetchone()
    return _bounds(kind, date.fromisoformat(last[0])) if last else None


def _n(x: float) -> str:
    return f"{x:g}".replace(".", ",")


def _dm(day: date | str) -> str:
    day = date.fromisoformat(day) if isinstance(day, str) else day
    return f"{day.day:02d}/{day.month:02d}"


def _total(rows: list[dict]) -> dict:
    score, max_score = sum(r["score"] for r in rows), sum(r["max_score"] for r in rows)
    return {"score": score, "max_score": max_score, "score_10": score_10(score, max_score)}


def _rate(total: dict) -> float:
    return total["score"] / total["max_score"] if total["max_score"] else 0.0


def _points(t: dict) -> str:
    # "x trong y", not "x/y": the report audit strips d/m dates before checking numbers (R5)
    return f"đạt {_n(t['score'])} trong {_n(t['max_score'])} ý, điểm {_n(t['score_10'])} trên 10"


def report_facts(conn, student_id: int, kind: str, start: str, *, today: date, low_pass_rate: float) -> dict:
    """Facts F01… (R10), up to 3 insights (R11) and `low` (pass rate below `low_pass_rate`) of committed sessions."""
    lo, hi = period(kind, start, today)
    prev = _previous(conn, student_id, kind, lo)
    rows = _sessions(conn, student_id, lo, hi)
    if not rows:
        raise NotReady({"reason": "no_committed_session", "previous_start": prev[0].isoformat() if prev else None})
    args = {"sid": student_id, "lo": lo.isoformat(), "hi": hi.isoformat()}
    out: list[dict] = []

    def add(fact_kind: str, val, text: str) -> str:
        out.append({"fact_id": f"F{len(out) + 1:02d}", "kind": fact_kind, "value": val, "text": text})
        return out[-1]["fact_id"]

    add("sessions", len(rows), f"Số buổi học: {len(rows)}.")
    n = sum(r["problems"] for r in rows)
    add("problems", n, f"Số bài đã làm: {n}.")
    total = _total(rows)
    score_id = add("score", total, f"Cả kỳ {_points(total)}.")
    if kind != "day":
        for r in rows:
            t = _total([r]) | {"mistakes": r["mistakes"]}
            add("session", t, f"Buổi {_dm(r['held_on'])}: {_points(t)}, {r['mistakes']} lỗi.")

    first, last, names = {}, {}, {}
    for kc, name, before, after in conn.execute(
        "SELECT e.kc_id, k.name, e.theta_before, e.theta_after FROM skill_event e"
        " JOIN attempt a ON a.id = e.attempt_id JOIN session s ON s.id = a.session_id JOIN kc k ON k.id = e.kc_id"
        f" WHERE e.student_id = :sid AND {_IN} ORDER BY e.id",
        args,
    ):
        first.setdefault(kc, before)
        last[kc], names[kc] = after, name
    moved = []  # (|dθ|, fact) of skills whose trend is not "giữ"
    for kc, before in first.items():
        d = last[kc] - before
        val = {"kc": names[kc], "before": elo.level(before), "after": elo.level(last[kc]), "trend": elo.trend(d)}
        text = f"Kỹ năng “{val['kc']}”: từ {val['before']} thành {val['after']} ({val['trend']})."
        if val["after"] == "chưa vững":
            val["prereqs"] = [
                r[0]
                for r in conn.execute(
                    "SELECT k.name FROM kc_prereq p JOIN kc k ON k.id = p.prereq_id WHERE p.kc_id = ?"
                    " ORDER BY p.prereq_id",
                    (kc,),
                )
            ]
            if val["prereqs"]:
                text += " Kỹ năng cần ôn trước: " + ", ".join(f"“{p}”" for p in val["prereqs"]) + "."
        fid = add("skill", val, text)
        if val["trend"] != "giữ":
            moved.append((abs(d), fid, val))

    top = None
    for r in _rows(
        conn,
        "SELECT e.description AS kind, count(*) AS n FROM mistake_current m"
        " JOIN attempt_current a ON a.id = m.attempt_id JOIN session s ON s.id = a.session_id"
        f" JOIN error_code e ON e.code = m.code WHERE {_IN} GROUP BY m.code ORDER BY n DESC, m.code LIMIT 3",
        args,
    ):
        fid = add("mistake_kind", r, f"Lỗi “{r['kind']}”: {r['n']} lần.")
        top = top or (fid, r)
    miscon = (
        "SELECT e.description AS kind, k.name AS kc, l.count FROM misconception_log l"
        " JOIN error_code e ON e.code = l.code JOIN kc k ON k.id = l.kc_id WHERE l.student_id = :sid"
    )
    # R9: what is still open today, not rebuilt at the end of the period
    open_ = " AND l.resolved_at IS NULL ORDER BY l.count DESC, l.last_seen DESC, l.kc_id, l.code"
    for r in _rows(conn, miscon + open_, args):
        add("repeat", r, f"Lỗi “{r['kind']}” ở “{r['kc']}” hiện còn, đã gặp {r['count']} lần.")
    gone = " AND l.resolved_at BETWEEN :lo AND :hi ORDER BY l.resolved_at, l.kc_id, l.code"
    for r in _rows(conn, miscon + gone, args):
        add("resolved", {"kind": r["kind"], "kc": r["kc"]}, f"Đã hết lỗi “{r['kind']}” ở “{r['kc']}”.")

    insights = []
    if prev:
        p_rows = _sessions(conn, student_id, *prev)
        p_total = _total(p_rows)
        span = _dm(prev[0]) if prev[0] == prev[1] else f"{_dm(prev[0])}–{_dm(prev[1])}"
        prev_id = add(
            "previous",
            {"sessions": len(p_rows)} | p_total,
            f"Kỳ trước ({span}): {len(p_rows)} buổi, {_points(p_total)}.",
        )
        d = round(_rate(total) - _rate(p_total), 6)
        word = "tốt hơn" if d >= 0.05 else "kém hơn" if d <= -0.05 else "giữ như"
        insights.append({"text": f"Kết quả {word} kỳ trước.", "facts": [score_id, prev_id]})
    if moved:
        _, fid, val = max(moved, key=lambda m: m[0])  # first one wins a tie
        insights.append({"text": f"Thay đổi rõ nhất ở “{val['kc']}” ({val['trend']}).", "facts": [fid]})
    if top and top[1]["n"] >= 2:
        insights.append({"text": f"Lỗi gặp nhiều nhất: “{top[1]['kind']}”.", "facts": [top[0]]})
    return {
        "code": student_code(student_id),
        "period_kind": kind,
        "period_start": lo.isoformat(),
        "period_end": hi.isoformat(),
        "facts": out,
        "insights": insights,
        "low": _rate(total) < low_pass_rate,
    }
