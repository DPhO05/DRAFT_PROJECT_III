"""Read-only student queries for the assistant's tools (P6-T03): SELECT only, students named by code."""

import json
import math
import re
from collections import Counter
from datetime import date
from itertools import groupby

from tutor.config import student_code
from tutor.services import elo, search

LEVELS = ("vững", "đang hình thành", "chưa vững")
METRICS = ("mistakes", "open_repeats", "level")
# mistakes the tutor approved, in saved sessions of active students; :sid NULL = all of them
_MISTAKES = (
    " FROM mistake_current m JOIN attempt_current a ON a.id = m.attempt_id"
    " JOIN session s ON s.id = a.session_id AND s.status = 'committed'"
    " JOIN student st ON st.id = s.student_id AND st.archived_at IS NULL"
    " JOIN problem p ON p.id = a.problem_id JOIN error_code e ON e.code = m.code"
    " LEFT JOIN kc k ON k.id = m.kc_id"
    " WHERE (:sid IS NULL OR s.student_id = :sid) AND (:since IS NULL OR s.held_on >= :since)"
    " AND (:kind IS NULL OR m.code = :kind) AND (:kc IS NULL OR m.kc_id = :kc)"
)


def _rows(conn, sql: str, args=()) -> list[dict]:
    cur = conn.execute(sql, args)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur]


def _filters(conn, kind: str | None, kc: int | None) -> tuple[str | None, str | None]:
    """(words of `kind`, name of `kc`); ValueError for a code or skill the database does not have."""
    words = name = None
    if kind is not None:
        if (row := conn.execute("SELECT description FROM error_code WHERE code = ?", (kind,)).fetchone()) is None:
            raise ValueError("Không có loại lỗi này trong danh mục")
        words = row[0]
    if kc is not None:
        if (row := conn.execute("SELECT name FROM kc WHERE id = ?", (kc,)).fetchone()) is None:
            raise ValueError(f"Không có kỹ năng {kc}")
        name = row[0]
    return words, name


def student_id(conn, code: str) -> int:
    m = re.fullmatch(r"HS-(\d+)", code)
    if m and conn.execute("SELECT 1 FROM student WHERE id = ? AND archived_at IS NULL", (int(m[1]),)).fetchone():
        return int(m[1])
    raise ValueError(f"Không có học sinh {code}")


def score_10(score: float, max_score: float) -> float:
    """Scale of 10 in steps of 0.5, halves rounded up (IA-app §0)."""
    return math.floor(score * 20 / max_score + 0.5) / 2 if max_score else 0.0


def _sessions(conn, sid: int, limit: int) -> list[dict]:
    rows = _rows(
        conn,
        "SELECT s.held_on,"
        " COALESCE((SELECT sum(score) FROM attempt_current WHERE session_id = s.id), 0) AS score,"
        " COALESCE((SELECT sum(max_score) FROM attempt_current WHERE session_id = s.id), 0) AS max_score,"
        " (SELECT count(*) FROM mistake_current m JOIN attempt_current a ON a.id = m.attempt_id"
        "  WHERE a.session_id = s.id) AS n_mistakes"
        " FROM session s WHERE s.student_id = ? AND s.status = 'committed'"
        " ORDER BY s.held_on DESC, s.id DESC LIMIT ?",
        (sid, limit),
    )
    return [{**r, "score_10": score_10(r["score"], r["max_score"])} for r in rows]


def list_students(conn) -> list[dict]:
    out = []
    for sid, grade in conn.execute("SELECT id, grade FROM student WHERE archived_at IS NULL ORDER BY id").fetchall():
        n = conn.execute(
            "SELECT count(*) FROM session WHERE student_id = ? AND status = 'committed'", (sid,)
        ).fetchone()[0]
        latest = _sessions(conn, sid, 1)
        last = {k: latest[0][k] for k in ("held_on", "score", "max_score", "score_10")} if latest else None
        out.append({"code": student_code(sid), "grade": grade, "n_sessions": n, "last": last})
    return out


def profile(conn, student_id: int) -> dict:
    grade = conn.execute("SELECT grade FROM student WHERE id = ?", (student_id,)).fetchone()[0]
    skills = [
        {"kc_id": r["kc_id"], "kc": r["kc"], "level": elo.level(r["theta"]), "n_attempts": r["n_attempts"]}
        for r in _rows(
            conn,
            "SELECT t.kc_id, k.name AS kc, t.theta, t.n_attempts FROM skill_state t JOIN kc k ON k.id = t.kc_id"
            " WHERE t.student_id = ? ORDER BY t.theta, t.kc_id",
            (student_id,),
        )
    ]
    repeats = _rows(
        conn,
        "SELECT e.description AS kind, l.kc_id, k.name AS kc, l.count, l.last_seen FROM misconception_log l"
        " JOIN error_code e ON e.code = l.code JOIN kc k ON k.id = l.kc_id"
        " WHERE l.student_id = ? AND l.resolved_at IS NULL ORDER BY l.count DESC, l.last_seen DESC, l.kc_id",
        (student_id,),
    )
    return {
        "code": student_code(student_id),
        "grade": grade,
        "counts": {lv: sum(s["level"] == lv for s in skills) for lv in LEVELS},
        "skills": skills,
        "repeats": repeats,
        "sessions": _sessions(conn, student_id, 5),
    }


def mistakes(
    conn,
    student_id: int,
    *,
    since: str | None = None,
    kind: str | None = None,
    kc: int | None = None,
    limit: int = 30,
) -> dict:
    """Approved mistakes of one student since a date (inclusive); `total` counts all, `items` stops at `limit`."""
    if since is not None:
        try:
            since = date.fromisoformat(since).isoformat()  # also turns 20261010 into 2026-10-10
        except ValueError:
            raise ValueError("Ngày bắt đầu phải có dạng yyyy-mm-dd") from None
    _filters(conn, kind, kc)
    args = {"sid": student_id, "since": since, "kind": kind, "kc": kc}
    return {
        "code": student_code(student_id),
        "since": since,
        "total": conn.execute(f"SELECT count(*){_MISTAKES}", args).fetchone()[0],
        "by_kind": _rows(
            conn,
            f"SELECT e.description AS kind, count(*) AS n{_MISTAKES} GROUP BY m.code ORDER BY n DESC, m.code",
            args,
        ),
        "items": _rows(
            conn,
            f"SELECT s.held_on, p.ref, e.description AS kind, k.name AS kc, m.description{_MISTAKES}"
            " ORDER BY s.held_on DESC, a.seq, m.id LIMIT :limit",
            args | {"limit": limit},
        ),
    }


def compare(conn, metric: str, *, kc: int | None = None, kind: str | None = None) -> dict:
    """One number per active student, biggest first; students with none are left out of `rows`."""
    if metric not in METRICS:
        raise ValueError(f"Chỉ so sánh theo {' / '.join(METRICS)}")
    if metric == "level" and kc is None:
        raise ValueError("So sánh mức kỹ năng cần chọn một kỹ năng")
    words, kc_name = _filters(conn, kind, kc)
    args = {"sid": None, "since": None, "kind": kind, "kc": kc}
    if metric == "mistakes":
        got = conn.execute(
            f"SELECT s.student_id, count(*), max(s.held_on){_MISTAKES} GROUP BY s.student_id ORDER BY 2 DESC, 1", args
        )
    elif metric == "open_repeats":
        got = conn.execute(
            "SELECT l.student_id, sum(l.count), max(l.last_seen) FROM misconception_log l"
            " JOIN student st ON st.id = l.student_id AND st.archived_at IS NULL"
            " WHERE l.resolved_at IS NULL AND (:kind IS NULL OR l.code = :kind) AND (:kc IS NULL OR l.kc_id = :kc)"
            " GROUP BY l.student_id ORDER BY 2 DESC, 1",
            args,
        )
    else:
        got = conn.execute(
            "SELECT t.student_id, t.theta, t.last_seen FROM skill_state t"
            " JOIN student st ON st.id = t.student_id AND st.archived_at IS NULL"
            " WHERE t.kc_id = :kc ORDER BY t.theta DESC, t.student_id",
            args,
        )
    rows = [
        {"code": student_code(sid), "value": elo.level(v) if metric == "level" else v, "last_seen": seen}
        for sid, v, seen in got
    ]
    return {
        "metric": metric,
        "kind": words,
        "kc": kc_name,
        "n_students": conn.execute("SELECT count(*) FROM student WHERE archived_at IS NULL").fetchone()[0],
        "total": None if metric == "level" else sum(r["value"] for r in rows),
        "rows": rows,
    }


def _point(theta: float) -> dict:
    """Level word and 0-100 chart position (display scale only; the app never shows the number)."""
    return {"level": elo.level(theta), "pos": max(0, min(100, round((theta + 1.5) / 3 * 100)))}


def _events(conn, student_id: int) -> list[tuple]:
    """(held_on, session_id, kc_id, theta_before, theta_after) of saved sessions, oldest first."""
    return conn.execute(
        "SELECT s.held_on, s.id, e.kc_id, e.theta_before, e.theta_after FROM skill_event e"
        " JOIN attempt a ON a.id = e.attempt_id JOIN session s ON s.id = a.session_id"
        " WHERE e.student_id = ? AND s.status = 'committed' ORDER BY s.held_on, s.id, e.id",
        (student_id,),
    ).fetchall()


def session_rows(
    conn, *, student_id: int | None = None, status: str | None = None, month: str | None = None
) -> list[dict]:
    """Sessions newest first with the numbers the Học sinh tab lists; none of the raw columns."""
    conds = {"s.student_id = ?": student_id, "s.status = ?": status, "substr(s.held_on, 1, 7) = ?": month}
    conds = {k: v for k, v in conds.items() if v is not None}
    where = (" WHERE " + " AND ".join(conds)) if conds else ""
    return _rows(
        conn,
        "SELECT s.id, s.student_id, s.held_on,"
        " (SELECT count(*) FROM attempt_current WHERE session_id = s.id) AS n_attempts,"
        " COALESCE((SELECT sum(score) FROM attempt_current WHERE session_id = s.id), 0) AS score,"
        " COALESCE((SELECT sum(max_score) FROM attempt_current WHERE session_id = s.id), 0) AS max_score,"
        " (SELECT count(*) FROM mistake_current m JOIN attempt_current a ON a.id = m.attempt_id"
        "  WHERE a.session_id = s.id) AS n_mistakes"
        f" FROM session s{where} ORDER BY s.held_on DESC, s.id DESC",
        tuple(conds.values()),
    )


def overview(conn) -> dict[int, dict]:
    """Per student, archived too: day they joined, newest saved session, how many skills at each level."""
    last: dict[int, dict] = {}
    for r in session_rows(conn, status="committed"):
        last.setdefault(
            r["student_id"],
            {"session_id": r["id"], "held_on": r["held_on"], "score": r["score"], "max_score": r["max_score"]},
        )
    levels = Counter(
        (sid, elo.level(theta)) for sid, theta in conn.execute("SELECT student_id, theta FROM skill_state")
    )
    return {
        sid: {
            "since": created_at[:10],
            "last_session": last.get(sid),
            "level_counts": [{"level": lv, "n": levels[sid, lv]} for lv in LEVELS],
        }
        for sid, created_at in conn.execute("SELECT id, created_at FROM student ORDER BY id")
    }


def skills(conn, student_id: int) -> list[dict]:
    """Every skill the student has met; `trend` = change in the newest session that had the skill."""
    moved: dict[int, tuple[tuple, float]] = {}
    for held_on, session_id, kc_id, before, after in _events(conn, student_id):
        key, total = moved.get(kc_id, (None, 0.0))
        moved[kc_id] = ((held_on, session_id), (total if key == (held_on, session_id) else 0.0) + after - before)
    return [
        {
            "kc_id": r["kc_id"],
            "kc": r["kc"],
            "topic": r["topic"],
            "level": elo.level(r["theta"]),
            "trend": elo.trend(moved.get(r["kc_id"], (None, 0.0))[1]),
            "last_seen": r["last_seen"],
            "n_attempts": r["n_attempts"],
        }
        for r in _rows(
            conn,
            "SELECT t.kc_id, k.name AS kc, COALESCE(p.name, k.name) AS topic, t.theta, t.last_seen, t.n_attempts"
            " FROM skill_state t JOIN kc k ON k.id = t.kc_id LEFT JOIN kc p ON p.id = k.parent_id"
            " WHERE t.student_id = ? ORDER BY t.last_seen DESC, t.kc_id",
            (student_id,),
        )
    ]


def recurring(conn, student_id: int) -> list[dict]:
    """Repeated mistakes in words, fixed ones included (`resolved_at` set)."""
    return _rows(
        conn,
        "SELECT e.description AS kind, l.kc_id, k.name AS kc, l.count, l.first_seen, l.last_seen, l.resolved_at"
        " FROM misconception_log l JOIN error_code e ON e.code = l.code JOIN kc k ON k.id = l.kc_id"
        " WHERE l.student_id = ? ORDER BY l.count DESC, l.last_seen DESC, l.kc_id",
        (student_id,),
    )


def progress(conn, student_id: int) -> dict:
    """Level over the saved sessions' days: overall (mean of the skills met so far) and per skill (None = not met)."""
    theta: dict[int, float] = {}
    dates: list[str] = []
    overall: list[dict] = []
    per_skill: dict[int, list] = {}
    for day, rows in groupby(_events(conn, student_id), key=lambda e: e[0]):
        theta |= {kc_id: after for _, _, kc_id, _, after in rows}
        dates.append(day)
        overall.append(_point(sum(theta.values()) / len(theta)))
        for kc_id, t in theta.items():
            per_skill.setdefault(kc_id, [None] * (len(dates) - 1)).append(_point(t))
    return {"dates": dates, "all": overall, "skills": per_skill}


def session_view(conn, session_id: int) -> dict | None:
    """One saved session for the Xem bài window: the mistakes in force, in words; None when there is no such session."""
    if conn.execute("SELECT 1 FROM session WHERE id = ?", (session_id,)).fetchone() is None:
        return None
    attempts = _rows(
        conn,
        "SELECT id, problem_id, seq, score, max_score, steps_json FROM attempt_current WHERE session_id = ?"
        " ORDER BY seq, id",
        (session_id,),
    )
    cards = {c["id"]: c for c in search.items_by_id(conn, [a["problem_id"] for a in attempts])}
    mistakes = _rows(
        conn,
        "SELECT m.attempt_id, m.step_idx, e.description AS kind, m.code, m.kc_id, k.name AS kc_name, m.description,"
        " m.evidence_latex, m.teacher_note, m.status FROM mistake_current m"
        " JOIN error_code e ON e.code = m.code LEFT JOIN kc k ON k.id = m.kc_id"
        " WHERE m.attempt_id IN (SELECT id FROM attempt_current WHERE session_id = ?) ORDER BY m.step_idx, m.id",
        (session_id,),
    )
    student, held_on = conn.execute("SELECT student_id, held_on FROM session WHERE id = ?", (session_id,)).fetchone()
    return {
        "id": session_id,
        "student_id": student,
        "held_on": held_on,
        "score": sum(a["score"] for a in attempts),
        "max_score": sum(a["max_score"] for a in attempts),
        "n_mistakes": len(mistakes),
        "attempts": [
            {
                "seq": a["seq"],
                "ref": cards[a["problem_id"]]["ref"],
                "statement_latex": cards[a["problem_id"]]["statement_latex"],
                "score": a["score"],
                "max_score": a["max_score"],
                "steps": [{"idx": s["idx"], "latex": s["latex"]} for s in json.loads(a["steps_json"])],
                "mistakes": [
                    {
                        "step_idx": m["step_idx"],
                        "kind": m["kind"],
                        "code": m["code"],
                        "kc": None if m["kc_id"] is None else {"id": m["kc_id"], "name": m["kc_name"]},
                        "description": m["description"],
                        "evidence_latex": m["evidence_latex"],
                        "teacher_note": m["teacher_note"],
                        "status": m["status"],
                    }
                    for m in mistakes
                    if m["attempt_id"] == a["id"]
                ],
            }
            for a in attempts
        ],
    }
