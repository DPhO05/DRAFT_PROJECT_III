"""Read-only student queries for the assistant's tools (P6-T03): SELECT only, students named by code."""

import math
import re
from datetime import date

from tutor.config import student_code
from tutor.services import elo

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
