"""Find problems in the bank: FTS5 text search, filters, and the teacher's problem grid (P5-T01)."""

import re
import sqlite3

from tutor.services import latex

LEVELS = ("dễ", "vừa", "khó")

_LEVEL = (
    "CASE WHEN p.difficulty_approved_at IS NULL OR p.delta IS NULL THEN 'none'"
    " WHEN p.delta < -0.3 THEN 'dễ' WHEN p.delta > 0.3 THEN 'khó' ELSE 'vừa' END"
)
_TOPIC = "COALESCE(k.parent_id, k.id)"
_HAS_TOPIC = (
    "EXISTS (SELECT 1 FROM problem_kc pk JOIN kc k ON k.id = pk.kc_id"
    f" WHERE pk.problem_id = p.id AND {_TOPIC} = :topic)"
)
_REF_STARTS = "substr(p.ref, 1, length(:q)) = :q COLLATE NOCASE"
# MATERIALIZED: one FTS lookup, not one per problem row
_FTS = (
    "WITH h AS MATERIALIZED (SELECT rowid AS id, bm25(problem_fts, 1.0, 0.5, 2.0) AS score"
    " FROM problem_fts WHERE problem_fts MATCH :match)"
)


def _tokens(text: str) -> list[str]:
    return re.findall(r"\w+", text.replace("đ", "d").replace("Đ", "D").lower())


def _query(q: str, topic, grade, kc, levels) -> tuple[str, str, str, dict]:
    """(WITH …, FROM … WHERE …, ORDER BY, args) for the filters; with a text query, ref prefix first then bm25."""
    args: dict = {"topic": topic, "grade": grade, "kc": kc}
    where = ["1"]
    with_, join, order = "", "", "p.ref"
    if tokens := _tokens(q):
        args |= {"q": q.strip(), "match": " OR ".join(f'"{t}"' for t in tokens)}
        with_, join = _FTS, "LEFT JOIN h ON h.id = p.id"
        where.append(f"({_REF_STARTS} OR h.id IS NOT NULL)")
        order = f"({_REF_STARTS}) DESC, h.score, p.ref"
    if topic is not None:
        where.append(_HAS_TOPIC)
    if grade is not None:
        where.append("CAST(p.ref AS INTEGER) = :grade")
    if kc is not None:
        where.append("EXISTS (SELECT 1 FROM problem_kc pk WHERE pk.problem_id = p.id AND pk.kc_id = :kc)")
    if levels is not None:
        args |= {f"l{i}": lv for i, lv in enumerate(levels)}
        where.append(f"{_LEVEL} IN ({', '.join(f':l{i}' for i in range(len(levels)))})")
    return with_, f"FROM problem p {join} WHERE {' AND '.join(where)}", order, args


def items_by_id(conn: sqlite3.Connection, ids: list[int]) -> list[dict]:
    """Grid cards for ids, in the order given; unknown ids are skipped."""
    if not ids:
        return []
    marks = ", ".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT p.id, p.ref, NULLIF(CAST(p.ref AS INTEGER), 0), {_LEVEL},"
        " EXISTS (SELECT 1 FROM rubric r WHERE r.problem_id = p.id),"
        " p.created_at >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-7 days'), p.statement_latex,"
        f" (SELECT {_TOPIC} FROM problem_kc pk JOIN kc k ON k.id = pk.kc_id WHERE pk.problem_id = p.id"
        "   ORDER BY k.id LIMIT 1)"
        f" FROM problem p WHERE p.id IN ({marks})",
        ids,
    ).fetchall()
    kcs: dict[int, dict[int, str]] = {}
    for pid, kid, name in conn.execute(
        "SELECT pk.problem_id, k.id, k.name FROM problem_kc pk JOIN kc k ON k.id = pk.kc_id"
        f" WHERE pk.problem_id IN ({marks}) ORDER BY pk.step_idx, k.id",
        ids,
    ):
        kcs.setdefault(pid, {}).setdefault(kid, name)
    topics = dict(conn.execute("SELECT id, name FROM kc"))
    by_id = {
        r[0]: {
            "id": r[0],
            "ref": r[1],
            "grade": r[2],
            "topic": {"id": r[7], "name": topics[r[7]]} if r[7] is not None else None,
            "kcs": [{"id": k, "name": n} for k, n in kcs.get(r[0], {}).items()],
            "level": None if r[3] == "none" else r[3],
            "has_rubric": bool(r[4]),
            "is_new": bool(r[5]),
            "statement_latex": r[6],
        }
        for r in rows
    }
    return [by_id[i] for i in ids if i in by_id]


def browse(
    conn: sqlite3.Connection,
    *,
    q: str = "",
    topic: int | None = None,
    grade: int | None = None,
    level: str | None = None,
    kc: int | None = None,
    offset: int = 0,
    limit: int = 12,
) -> dict:
    if level is not None and level not in (*LEVELS, "none"):
        raise ValueError(f"unknown level {level!r}")
    with_, frm, order, args = _query(q, topic, grade, kc, None if level is None else [level])
    total = conn.execute(f"{with_} SELECT count(*) {frm}", args).fetchone()[0]
    ids = conn.execute(
        f"{with_} SELECT p.id {frm} ORDER BY {order} LIMIT :limit OFFSET :offset",
        args | {"limit": limit, "offset": offset},
    )
    counts = conn.execute(
        f"SELECT {_TOPIC}, count(DISTINCT pk.problem_id) FROM problem_kc pk JOIN kc k ON k.id = pk.kc_id GROUP BY 1"
    )
    return {
        "total": total,
        "topic_counts": {str(t): n for t, n in counts},
        "items": items_by_id(conn, [r[0] for r in ids]),
    }


def search_problems(
    conn: sqlite3.Connection,
    text: str,
    *,
    kc: int | None = None,
    grade: int | None = None,
    level_min: str | None = None,
    level_max: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Best matches for the tutor's chat tool: at most 10; a level bound drops problems with no level."""
    levels = None
    if level_min is not None or level_max is not None:
        lo = LEVELS.index(level_min) if level_min is not None else 0
        hi = LEVELS.index(level_max) if level_max is not None else len(LEVELS) - 1
        levels = LEVELS[lo : hi + 1]
    with_, frm, order, args = _query(text, None, grade, kc, levels)
    ids = conn.execute(
        f"{with_} SELECT p.id {frm} ORDER BY {order} LIMIT :limit", args | {"limit": max(0, min(limit, 10))}
    )
    return items_by_id(conn, [r[0] for r in ids])


def find_problems(conn: sqlite3.Connection, refs: list[str]) -> list[dict]:
    """Problems for the refs given (case-insensitive), in that order; unknown refs are skipped."""
    ids = []
    for ref in refs:
        if row := conn.execute("SELECT id FROM problem WHERE ref = ? COLLATE NOCASE LIMIT 1", (ref,)).fetchone():
            ids.append(row[0])
    return items_by_id(conn, ids)


def solution_steps(conn: sqlite3.Connection, ids: list[int]) -> dict[int, list[str]]:
    """Bank solution of each problem split into paragraph steps, as the problem page shows it."""
    marks = ", ".join("?" * len(ids))
    return {
        pid: [s.latex for s in latex.split_steps(sol, 0, len(sol), by="paragraph")]
        for pid, sol in conn.execute(f"SELECT id, solution_latex FROM problem WHERE id IN ({marks})", ids)
    }
