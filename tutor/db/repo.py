"""The only module that writes tutor.db: connect, init, migrate, backup, reads, writes."""

import csv
import io
import json
import re
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path

from tutor.config import student_code

SCHEMA = Path(__file__).with_name("schema.sql")
MIGRATIONS = Path(__file__).with_name("migrations")
TABLES = (
    "kc", "kc_prereq", "error_code", "problem", "problem_kc", "rubric", "problem_pair",
    "student", "session", "attempt", "mistake",
    "skill_event", "skill_state", "misconception_log",
    "recommendation", "report",
)  # fmt: skip
_BACKUP_RE = re.compile(r"^tutor-(\d{4}-\d{2})-\d{2}-\d{6}(?:-(\d+))?\.db$")


class MigrationError(Exception):
    """A migration file failed; that file was rolled back."""


class NotFound(Exception):
    pass


class DuplicateSubmission(Exception):
    """Same student, same file sha256 (UNIQUE student_id, source_sha256)."""

    def __init__(self, session_id: int, thread_id: str):
        super().__init__(f"File đã nộp (trùng sha256), buổi {session_id}, thread {thread_id}")
        self.session_id, self.thread_id = session_id, thread_id


class DateOrderLocked(Exception):
    """Session date earlier than one already committed: Elo updates run in date order."""

    def __init__(self, held_on: str, last_committed: str):
        super().__init__(f"Ngày học {held_on} sớm hơn buổi đã ghi {last_committed}")
        self.held_on, self.last_committed = held_on, last_committed


class CatalogError(ValueError):
    """Bad KC catalog data; `cycle` holds the prerequisite loop (codes) when there is one."""

    def __init__(self, message: str, cycle: list[str] | None = None):
        super().__init__(message)
        self.cycle = cycle


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dicts(cur: sqlite3.Cursor) -> list[dict]:
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def connect(db_path: Path, readonly: bool = False) -> sqlite3.Connection:
    """New connection, foreign keys on. No implicit transactions: writes go through write_tx.

    Never share one connection between concurrent threads; one owner may hand it to another thread
    (FastAPI runs a sync dependency and its endpoint on different threadpool threads).
    """
    opts = {"isolation_level": None, "timeout": 5, "check_same_thread": False}
    if readonly:
        conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True, **opts)
    else:
        conn = sqlite3.connect(db_path, **opts)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def write_tx(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """BEGIN IMMEDIATE … COMMIT / ROLLBACK.

    Takes the write lock up front, so a second writer waits up to `timeout` instead of failing
    with SQLITE_BUSY when a deferred transaction tries to upgrade its read lock (`with conn:`).
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def _script_tx(conn: sqlite3.Connection, sql: str) -> None:
    # executescript opens no transaction of its own, so wrap the whole file in one.
    try:
        conn.executescript(f"BEGIN IMMEDIATE;\n{sql}\nCOMMIT;")
    except sqlite3.Error:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


def create_schema(conn: sqlite3.Connection) -> None:
    """Baseline schema.sql (user_version 0) in one transaction."""
    conn.execute("PRAGMA journal_mode = WAL")  # cannot change inside a transaction
    body = re.sub(r"(?m)^PRAGMA .*$", "", SCHEMA.read_text(encoding="utf-8"))
    _script_tx(conn, body)


def schema_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def _migration_files(migrations_dir: Path) -> list[tuple[int, Path]]:
    return sorted((int(p.stem), p) for p in migrations_dir.glob("[0-9][0-9][0-9].sql"))


def latest_version(migrations_dir: Path = MIGRATIONS) -> int:
    return max((n for n, _ in _migration_files(migrations_dir)), default=0)


def migrate(db_path: Path, backup_dir: Path, migrations_dir: Path = MIGRATIONS, *, backup_first: bool = True) -> int:
    """Apply pending NNN.sql in order, one transaction each. Caller holds runner.lock."""
    with closing(connect(db_path)) as conn:
        version = schema_version(conn)
        pending = [(n, p) for n, p in _migration_files(migrations_dir) if n > version]
        if pending and backup_first:
            backup(db_path, backup_dir)
        for n, p in pending:
            try:
                _script_tx(conn, f"{p.read_text(encoding='utf-8')}\nPRAGMA user_version = {n};")
            except sqlite3.Error as e:
                raise MigrationError(f"{p.name}: {e}") from e
        return schema_version(conn)


def init_db(db_path: Path, backup_dir: Path, migrations_dir: Path = MIGRATIONS) -> int:
    """Create the schema if the DB is empty, then migrate. Returns user_version."""
    with closing(connect(db_path)) as conn:
        fresh = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table'").fetchone() is None
        if fresh:
            create_schema(conn)
    return migrate(db_path, backup_dir, migrations_dir, backup_first=not fresh)


def backup(db_path: Path, backup_dir: Path, keep_recent: int = 30, keep_monthly: bool = True) -> Path:
    """Online copy to backup_dir/tutor-<yyyy-mm-dd>-<hhmmss>.db (C-29), then prune (S8)."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    stem = f"tutor-{datetime.now():%Y-%m-%d-%H%M%S}"
    dst, n = backup_dir / f"{stem}.db", 1
    while dst.exists():
        n += 1
        dst = backup_dir / f"{stem}-{n}.db"
    with closing(connect(db_path)) as src, closing(sqlite3.connect(dst)) as out:
        src.backup(out)
        out.execute("PRAGMA journal_mode = DELETE")  # backup = 1 self-contained file
    _prune(backup_dir, keep_recent, keep_monthly)
    return dst


def _prune(backup_dir: Path, keep_recent: int, keep_monthly: bool) -> None:
    """Keep the newest `keep_recent` + the newest of every month; other names are never touched."""
    files = []
    for p in backup_dir.iterdir():
        if m := _BACKUP_RE.match(p.name):
            files.append((p.name[6:23], int(m[2] or 1), m[1], p))
    files.sort(reverse=True)
    keep = {f[3] for f in files[:keep_recent]}
    if keep_monthly:
        months: set[str] = set()
        for _, _, month, p in files:
            if month not in months:
                months.add(month)
                keep.add(p)
    for *_, p in files:
        if p not in keep:
            p.unlink()


def row_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in TABLES}


# ---------------------------------------------------------------- catalog (KC, prerequisites)
KC_FIELDS = ("code", "name", "description", "parent_code", "lop")


def read_catalog(kc_csv: str, prereq_csv: str) -> tuple[list[dict], list[tuple[str, str]]]:
    """Parse kc.csv / kc_prereq.csv text (BOM allowed); a missing column is a CatalogError, not a crash."""

    def rows(text: str, need: tuple[str, ...], name: str) -> list[dict]:
        r = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
        if missing := [c for c in need if c not in (r.fieldnames or [])]:
            raise CatalogError(f"{name} thiếu cột: {', '.join(missing)}")
        return list(r)

    kcs = [{k: (r[k] or "").strip() for k in KC_FIELDS} for r in rows(kc_csv, KC_FIELDS, "kc.csv")]
    pre = [
        ((r["kc_code"] or "").strip(), (r["prereq_code"] or "").strip())
        for r in rows(prereq_csv, ("kc_code", "prereq_code"), "kc_prereq.csv")
    ]
    return kcs, pre


def _find_cycle(edges: dict[str, set[str]], start: str | None = None) -> list[str] | None:
    """kc -> prerequisites. Returns one loop as [a, b, …, a] (searched from `start` first), or None."""
    state: dict[str, int] = {}
    stack: list[str] = []

    def dfs(n: str) -> list[str] | None:
        state[n] = 1
        stack.append(n)
        for m in sorted(edges.get(n, ())):
            if state.get(m) == 1:
                return stack[stack.index(m) :] + [m]
            if m not in state and (c := dfs(m)):
                return c
        stack.pop()
        state[n] = 2
        return None

    for n in ([start] if start else []) + sorted(edges):
        if n not in state and (c := dfs(n)):
            return c
    return None


def _edges(conn: sqlite3.Connection) -> dict[str, set[str]]:
    edges: dict[str, set[str]] = {}
    for a, b in conn.execute(
        "SELECT k.code, p.code FROM kc_prereq r JOIN kc k ON k.id = r.kc_id JOIN kc p ON p.id = r.prereq_id"
    ):
        edges.setdefault(a, set()).add(b)
    return edges


def import_catalog(conn: sqlite3.Connection, kcs: list[dict], prereqs: list[tuple[str, str]], *, apply: bool) -> dict:
    """Preview (apply=False) or apply in one transaction: new KC, changed KC, new prerequisite pairs."""
    with write_tx(conn):
        have = {r["code"]: r for r in _dicts(conn.execute(
            "SELECT k.code, k.name, k.description, k.lop, p.code AS parent_code"
            " FROM kc k LEFT JOIN kc p ON p.id = k.parent_id"
        ))}  # fmt: skip
        codes = [k["code"] for k in kcs]
        if dup := sorted({c for c in codes if codes.count(c) > 1}):
            raise CatalogError(f"Mã KC trùng: {', '.join(dup)}")
        known = set(have) | set(codes)
        for k in kcs:
            if not k["code"] or not k["name"] or not k["description"]:
                raise CatalogError(f"KC thiếu code / name / description: {k}")
            if k["parent_code"] and k["parent_code"] not in known:
                raise CatalogError(f"{k['code']}: parent_code lạ {k['parent_code']}")
            if k["lop"] and not k["lop"].isdigit():
                raise CatalogError(f"{k['code']}: lop phải là số")
        edges = _edges(conn)
        new_pre = []
        for a, b in prereqs:
            if a not in known or b not in known:
                raise CatalogError(f"Tiên quyết có mã lạ: {a} -> {b}")
            if a == b:
                raise CatalogError(f"KC tự làm tiên quyết của chính nó: {a}", [a, a])
            if b not in edges.get(a, set()):
                new_pre.append([a, b])
                edges.setdefault(a, set()).add(b)
        if cycle := _find_cycle(edges):
            raise CatalogError(f"Tiên quyết tạo vòng: {' -> '.join(cycle)}", cycle)

        def norm(k: dict) -> tuple:
            return (k["name"], k["description"], k["parent_code"] or None, int(k["lop"]) if k["lop"] else None)

        def norm_db(r: dict) -> tuple:
            return (r["name"], r["description"], r["parent_code"], r["lop"])

        new_kc = [k["code"] for k in kcs if k["code"] not in have]
        changed = [k["code"] for k in kcs if k["code"] in have and norm(k) != norm_db(have[k["code"]])]
        if apply:
            by = {k["code"]: k for k in kcs}
            for c in new_kc:
                k = by[c]
                conn.execute(
                    "INSERT INTO kc (code, name, description, lop) VALUES (?, ?, ?, ?)",
                    (c, k["name"], k["description"], int(k["lop"]) if k["lop"] else None),
                )
            for c in changed:
                k = by[c]
                conn.execute(
                    "UPDATE kc SET name = ?, description = ?, lop = ?,"
                    " embedding = CASE WHEN description = ? THEN embedding END WHERE code = ?",
                    (k["name"], k["description"], int(k["lop"]) if k["lop"] else None, k["description"], c),
                )
            for k in kcs:
                conn.execute(
                    "UPDATE kc SET parent_id = (SELECT id FROM kc WHERE code = ?) WHERE code = ?",
                    (k["parent_code"] or None, k["code"]),
                )
            conn.executemany(
                "INSERT INTO kc_prereq (kc_id, prereq_id)"
                " SELECT a.id, b.id FROM kc a, kc b WHERE a.code = ? AND b.code = ?",
                new_pre,
            )
        return {"new_kc": new_kc, "changed_kc": changed, "new_prereq": new_pre}


def export_catalog(conn: sqlite3.Connection) -> tuple[str, str]:
    """kc.csv and kc_prereq.csv text, same columns as the import."""
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(KC_FIELDS)
    for r in conn.execute(
        "SELECT k.code, k.name, k.description, coalesce(p.code, ''), coalesce(k.lop, '')"
        " FROM kc k LEFT JOIN kc p ON p.id = k.parent_id ORDER BY k.id"
    ):
        w.writerow(r)
    pre = io.StringIO()
    w = csv.writer(pre, lineterminator="\n")
    w.writerow(("kc_code", "prereq_code"))
    for a, b in sorted((a, b) for a, bs in _edges(conn).items() for b in bs):
        w.writerow((a, b))
    return out.getvalue(), pre.getvalue()


def list_kc(conn: sqlite3.Connection) -> list[dict]:
    rows = _dicts(conn.execute(
        "SELECT k.id, k.code, k.name, k.description, k.parent_id, k.lop, k.embedding IS NOT NULL AS embedded"
        " FROM kc k ORDER BY k.id"
    ))  # fmt: skip
    pre: dict[int, list[int]] = {}
    for a, b in conn.execute("SELECT kc_id, prereq_id FROM kc_prereq ORDER BY kc_id, prereq_id"):
        pre.setdefault(a, []).append(b)
    for r in rows:
        r["prereq_ids"] = pre.get(r["id"], [])
    return rows


def add_kc(conn: sqlite3.Connection, *, code: str, name: str, description: str, parent_id: int | None = None,
           lop: int | None = None) -> int:  # fmt: skip
    if not code.strip() or not name.strip() or not description.strip():
        raise CatalogError("KC cần code, name, description")
    with write_tx(conn):
        _check_parent(conn, None, parent_id)
        try:
            cur = conn.execute(
                "INSERT INTO kc (code, name, description, parent_id, lop) VALUES (?, ?, ?, ?, ?)",
                (code.strip(), name.strip(), description.strip(), parent_id, lop),
            )
        except sqlite3.IntegrityError as e:
            raise CatalogError(f"Không thêm được KC {code}: {e}") from e
        return cur.lastrowid


def _check_parent(conn: sqlite3.Connection, kc_id: int | None, parent_id: int | None) -> None:
    """Two levels only: a parent is a group (no parent itself); a KC with children stays a group."""
    if parent_id is None:
        return
    row = conn.execute("SELECT parent_id FROM kc WHERE id = ?", (parent_id,)).fetchone()
    if row is None or parent_id == kc_id or row[0] is not None:
        raise CatalogError("Nhóm cha phải là một nhóm KC có sẵn (KC không có nhóm cha), khác chính nó")
    if kc_id is not None and conn.execute("SELECT 1 FROM kc WHERE parent_id = ?", (kc_id,)).fetchone():
        raise CatalogError("KC này đang là nhóm có KC con, không chuyển vào nhóm khác được")


def update_kc(conn: sqlite3.Connection, kc_id: int, **fields) -> None:
    """name / description / parent_id / lop. A new description clears the embedding (06 must re-embed)."""
    allowed = {k: v for k, v in fields.items() if k in ("name", "description", "parent_id", "lop")}
    with write_tx(conn):
        old = conn.execute("SELECT description FROM kc WHERE id = ?", (kc_id,)).fetchone()
        if old is None:
            raise NotFound(f"KC {kc_id}")
        if "parent_id" in allowed:
            _check_parent(conn, kc_id, allowed["parent_id"])
        for k, v in allowed.items():
            conn.execute(f"UPDATE kc SET {k} = ? WHERE id = ?", (v, kc_id))
        if "description" in allowed and allowed["description"] != old[0]:
            conn.execute("UPDATE kc SET embedding = NULL, embed_model = NULL WHERE id = ?", (kc_id,))


def add_prereq(conn: sqlite3.Connection, kc_id: int, prereq_id: int) -> None:
    with write_tx(conn):
        code = dict(conn.execute("SELECT id, code FROM kc WHERE id IN (?, ?)", (kc_id, prereq_id)).fetchall())
        if len(code) < (1 if kc_id == prereq_id else 2):
            raise NotFound("KC")
        if kc_id == prereq_id:
            raise CatalogError("KC không thể là tiên quyết của chính nó", [code[kc_id], code[kc_id]])
        edges = _edges(conn)
        edges.setdefault(code[kc_id], set()).add(code[prereq_id])
        if cycle := _find_cycle(edges, code[kc_id]):
            raise CatalogError(f"Tiên quyết tạo vòng: {' -> '.join(cycle)}", cycle)
        conn.execute("INSERT OR IGNORE INTO kc_prereq (kc_id, prereq_id) VALUES (?, ?)", (kc_id, prereq_id))


def remove_prereq(conn: sqlite3.Connection, kc_id: int, prereq_id: int) -> None:
    with write_tx(conn):
        conn.execute("DELETE FROM kc_prereq WHERE kc_id = ? AND prereq_id = ?", (kc_id, prereq_id))


# ---------------------------------------------------------------- students
def _check_student(name: str | None, grade: int | None) -> None:
    if name is not None and not name.strip():
        raise ValueError("Tên học sinh không được trống")
    if grade is not None and not 1 <= grade <= 12:
        raise ValueError("Lớp phải từ 1 đến 12")


def add_student(conn: sqlite3.Connection, *, name: str, grade: int | None = None, note: str | None = None) -> int:
    _check_student(name, grade)
    with write_tx(conn):
        return conn.execute(
            "INSERT INTO student (name, grade, note) VALUES (?, ?, ?)", (name.strip(), grade, note)
        ).lastrowid


def update_student(conn: sqlite3.Connection, student_id: int, **fields) -> None:
    allowed = {k: v for k, v in fields.items() if k in ("name", "grade", "note")}
    _check_student(allowed.get("name"), allowed.get("grade"))
    with write_tx(conn):
        if conn.execute("SELECT 1 FROM student WHERE id = ?", (student_id,)).fetchone() is None:
            raise NotFound(f"HS {student_id}")
        for k, v in allowed.items():
            conn.execute(f"UPDATE student SET {k} = ? WHERE id = ?", (v.strip() if k == "name" else v, student_id))


def archive_student(conn: sqlite3.Connection, student_id: int) -> str:
    with write_tx(conn):
        if conn.execute("SELECT 1 FROM student WHERE id = ?", (student_id,)).fetchone() is None:
            raise NotFound(f"HS {student_id}")
        at = now()
        conn.execute("UPDATE student SET archived_at = coalesce(archived_at, ?) WHERE id = ?", (at, student_id))
        return conn.execute("SELECT archived_at FROM student WHERE id = ?", (student_id,)).fetchone()[0]


def list_students(conn: sqlite3.Connection, include_archived: bool = False) -> list[dict]:
    rows = _dicts(conn.execute(
        "SELECT id, name, grade, note, created_at, archived_at FROM student"
        + ("" if include_archived else " WHERE archived_at IS NULL") + " ORDER BY id"
    ))  # fmt: skip
    for r in rows:
        r["code"] = student_code(r["id"])
    return rows


def get_student(conn: sqlite3.Connection, student_id: int) -> dict:
    rows = _dicts(conn.execute("SELECT id, name, grade, note, archived_at FROM student WHERE id = ?", (student_id,)))
    if not rows:
        raise NotFound(f"HS {student_id}")
    return rows[0] | {"code": student_code(student_id)}


# ---------------------------------------------------------------- bank
def add_bank_problem(
    conn: sqlite3.Connection,
    *,
    ref: str,
    statement: str,
    solution: str,
    source: str,
    delta: float | None,
    tags: list[tuple[int, int, str]],
    rubric_items: list[dict],
) -> int | None:
    """Approved problem + KC tags (kc_id, step_idx, evidence) + rubric v1. None if ref already exists."""
    with write_tx(conn):
        if conn.execute("SELECT 1 FROM problem WHERE ref = ?", (ref,)).fetchone():
            return None
        at = now()
        pid = conn.execute(
            "INSERT INTO problem (ref, statement_latex, solution_latex, source, delta, difficulty_approved_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (ref, statement, solution, source, delta, at if delta is not None else None),
        ).lastrowid
        conn.executemany(
            "INSERT INTO problem_kc (problem_id, kc_id, step_idx, evidence_latex, approved_at) VALUES (?, ?, ?, ?, ?)",
            [(pid, k, i, ev, at) for k, i, ev in tags],
        )
        conn.execute(
            "INSERT INTO rubric (problem_id, version, items_json, max_score, approved_at) VALUES (?, 1, ?, ?, ?)",
            (pid, json.dumps(rubric_items, ensure_ascii=False), sum(i["points"] for i in rubric_items), at),
        )
        return pid


def bank_problems(conn: sqlite3.Connection) -> list[dict]:
    """Every problem with whether it has an approved rubric (01 Ingest context)."""
    return _dicts(conn.execute(
        "SELECT p.id, p.ref, p.statement_latex, EXISTS (SELECT 1 FROM rubric r WHERE r.problem_id = p.id) AS has_rubric"
        " FROM problem p ORDER BY p.ref"
    ))  # fmt: skip


def candidate_problems(conn: sqlite3.Connection, kc_id: int) -> list[dict]:
    """Problems tagged with a KC that have an approved rubric and δ (SDD v0.2 §8.6)."""
    return _dicts(conn.execute(
        "SELECT p.id, p.ref, p.delta FROM problem p JOIN problem_kc pk ON pk.problem_id = p.id"
        " WHERE pk.kc_id = ? AND p.delta IS NOT NULL AND EXISTS (SELECT 1 FROM rubric r WHERE r.problem_id = p.id)"
        " GROUP BY p.id ORDER BY p.delta",
        (kc_id,),
    ))  # fmt: skip


def problem_detail(conn: sqlite3.Connection, problem_id: int) -> dict:
    """Problem + its approved KCs + latest approved rubric (None if none) for the 02 · 03 · 04 lane."""
    rows = _dicts(conn.execute(
        "SELECT id, ref, statement_latex, solution_latex FROM problem WHERE id = ?", (problem_id,)
    ))  # fmt: skip
    if not rows:
        raise NotFound(f"bài {problem_id}")
    p = rows[0]
    p["kcs"] = _dicts(conn.execute(
        "SELECT DISTINCT k.id, k.code, k.name FROM problem_kc pk JOIN kc k ON k.id = pk.kc_id"
        " WHERE pk.problem_id = ? ORDER BY k.id",
        (problem_id,),
    ))  # fmt: skip
    r = conn.execute(
        "SELECT id, version, items_json, max_score FROM rubric WHERE problem_id = ? ORDER BY version DESC LIMIT 1",
        (problem_id,),
    ).fetchone()
    p["rubric"] = {"id": r[0], "version": r[1], "items": json.loads(r[2]), "max_score": r[3]} if r else None
    return p


def error_codes(conn: sqlite3.Connection, *, active_only: bool = False) -> list[dict]:
    where = " WHERE active = 1" if active_only else ""
    return _dicts(conn.execute(
        f"SELECT code, category, description, example, active FROM error_code{where} ORDER BY code"
    ))  # fmt: skip


# ---------------------------------------------------------------- error codes (P2-T07; 03 reads active ones)
ERROR_CATEGORIES = ("computational", "conceptual", "notational", "presentation", "other")


def _error_code(conn: sqlite3.Connection, code: str) -> dict:
    rows = _dicts(conn.execute(
        "SELECT code, category, description, example, active FROM error_code WHERE code = ?", (code,)
    ))  # fmt: skip
    if not rows:
        raise NotFound(f"mã lỗi {code}")
    return rows[0]


def add_error_code(conn: sqlite3.Connection, *, code: str, category: str, description: str,
                   example: str | None = None) -> dict:  # fmt: skip
    code, description = code.strip(), description.strip()
    if category not in ERROR_CATEGORIES:
        raise ValueError(f"Nhóm lỗi phải là một trong: {', '.join(ERROR_CATEGORIES)}")
    if not re.fullmatch(rf"{category}\.[a-z][a-z0-9_]*", code):
        raise ValueError(f"Mã phải có dạng {category}.<tên con> (chữ thường a–z, số, dấu _)")
    if not description:
        raise ValueError("Mô tả mã lỗi không được trống")
    with write_tx(conn):
        if conn.execute("SELECT 1 FROM error_code WHERE code = ?", (code,)).fetchone():
            raise ValueError(f"Mã {code} đã có")
        conn.execute(
            "INSERT INTO error_code (code, category, description, example) VALUES (?, ?, ?, ?)",
            (code, category, description, (example or "").strip() or None),
        )
        return _error_code(conn, code)


def update_error_code(conn: sqlite3.Connection, code: str, *, description: str | None = None,
                      example: str | None = None, active: bool | None = None) -> dict:  # fmt: skip
    """None = unchanged; example "" clears it. No delete: old mistakes still reference the code."""
    if description is not None and not description.strip():
        raise ValueError("Mô tả mã lỗi không được trống")
    with write_tx(conn):
        _error_code(conn, code)
        if active is not None and not active and code == "other.unclear":
            raise ValueError("other.unclear khoá, không tắt được")
        if description is not None:
            conn.execute("UPDATE error_code SET description = ? WHERE code = ?", (description.strip(), code))
        if example is not None:
            conn.execute("UPDATE error_code SET example = ? WHERE code = ?", (example.strip() or None, code))
        if active is not None:
            conn.execute("UPDATE error_code SET active = ? WHERE code = ?", (int(active), code))
        return _error_code(conn, code)


def error_code_mistakes(conn: sqlite3.Connection, code: str) -> list[dict]:
    """Mistakes in effect (mistake_current) carrying the code, newest session first."""
    _error_code(conn, code)
    rows = _dicts(conn.execute(
        "SELECT m.id, s.id AS session_id, s.thread_id, s.student_id, s.held_on, p.ref, m.step_idx, m.status,"
        " m.description FROM mistake_current m JOIN attempt a ON a.id = m.attempt_id"
        " JOIN session s ON s.id = a.session_id JOIN problem p ON p.id = a.problem_id"
        " WHERE m.code = ? ORDER BY s.held_on DESC, m.id DESC",
        (code,),
    ))  # fmt: skip
    for r in rows:
        r["student_code"] = student_code(r["student_id"])
    return rows


def export_error_codes(conn: sqlite3.Connection) -> str:
    """error_code.csv (C-30: export only; codes are edited in the app, never imported)."""
    out = io.StringIO()
    w = csv.DictWriter(out, ("code", "category", "description", "example", "active"), lineterminator="\n")
    w.writeheader()
    w.writerows(error_codes(conn))
    return out.getvalue()


def recent_mistakes(conn: sqlite3.Connection, student_id: int, limit: int = 5) -> list[dict]:
    """Latest approved mistakes of a student, any KC (C-14; SDD v0.2 §8.6)."""
    return _dicts(conn.execute(
        "SELECT m.code, m.kc_id, m.description, s.held_on FROM mistake_current m"
        " JOIN attempt a ON a.id = m.attempt_id JOIN session s ON s.id = a.session_id"
        " WHERE s.student_id = ? ORDER BY s.held_on DESC, m.id DESC LIMIT ?",
        (student_id, limit),
    ))  # fmt: skip


# ---------------------------------------------------------------- sessions (G1 commit nodes only)
def commit_session_start(
    conn: sqlite3.Connection,
    *,
    student_id: int,
    held_on: str,
    source_path: str,
    source_kind: str,
    sha256: str,
    thread_id: str,
) -> int:
    """① in one transaction: duplicate check, date-order check, session row (running)."""
    with write_tx(conn):
        st = conn.execute("SELECT archived_at FROM student WHERE id = ?", (student_id,)).fetchone()
        if st is None or st[0]:
            raise NotFound(f"HS {student_id}")
        if dup := conn.execute(
            "SELECT id, thread_id FROM session WHERE student_id = ? AND source_sha256 = ?", (student_id, sha256)
        ).fetchone():
            raise DuplicateSubmission(*dup)
        last = conn.execute(
            "SELECT max(held_on) FROM session WHERE student_id = ? AND status = 'committed'", (student_id,)
        ).fetchone()[0]
        if last and held_on < last:
            raise DateOrderLocked(held_on, last)
        return conn.execute(
            "INSERT INTO session (student_id, held_on, source_path, source_kind, source_sha256, thread_id, status)"
            " VALUES (?, ?, ?, ?, ?, ?, 'running')",
            (student_id, held_on, source_path, source_kind, sha256, thread_id),
        ).lastrowid


def commit_session_status(conn: sqlite3.Connection, session_id: int, status: str) -> None:
    """running / awaiting_review / failed. A committed session never changes back."""
    with write_tx(conn):
        conn.execute("UPDATE session SET status = ? WHERE id = ? AND status <> 'committed'", (status, session_id))


def delete_uncommitted_session(conn: sqlite3.Connection, session_id: int) -> int:
    """C-15: drop a cancelled G1 session that has no attempt yet. Returns rows deleted (0 or 1)."""
    with write_tx(conn):
        return conn.execute(
            "DELETE FROM session WHERE id = ? AND status <> 'committed'"
            " AND NOT EXISTS (SELECT 1 FROM attempt WHERE session_id = session.id)", (session_id,)
        ).rowcount  # fmt: skip


def thread_id_taken(conn: sqlite3.Connection, thread_id: str) -> bool:
    return conn.execute("SELECT 1 FROM session WHERE thread_id = ?", (thread_id,)).fetchone() is not None


def list_sessions(conn: sqlite3.Connection, *, student_id: int | None = None, month: str | None = None,
                  status: str | None = None) -> list[dict]:  # fmt: skip
    conds = {"student_id = ?": student_id, "substr(held_on, 1, 7) = ?": month, "status = ?": status}
    conds = {k: v for k, v in conds.items() if v is not None}
    where = (" WHERE " + " AND ".join(conds)) if conds else ""
    rows = _dicts(conn.execute(
        "SELECT id, student_id, held_on, source_path, source_kind, source_sha256, thread_id, status, created_at,"
        f" committed_at FROM session{where} ORDER BY held_on DESC, id DESC",
        tuple(conds.values()),
    ))  # fmt: skip
    for r in rows:
        r["student_code"] = student_code(r["student_id"])
    return rows


def submitted_sha256(conn: sqlite3.Connection) -> dict[str, list[int]]:
    """sha256 -> student ids that already submitted that file (inbox screen)."""
    out: dict[str, list[int]] = {}
    for sha, sid in conn.execute("SELECT source_sha256, student_id FROM session"):
        out.setdefault(sha, []).append(sid)
    return out


MISTAKE_COLS = ("step_idx", "code", "kc_id", "description", "evidence_latex", "confidence", "verifier_verdict",
                "verifier_reason", "status", "llm_json", "teacher_note", "reviewed_at")  # fmt: skip


def _insert_mistake(conn: sqlite3.Connection, attempt_id: int, m: dict) -> None:
    row = m | {"llm_json": None if m["llm_json"] is None else json.dumps(m["llm_json"], ensure_ascii=False)}
    conn.execute(
        f"INSERT INTO mistake (attempt_id, {', '.join(MISTAKE_COLS)}) VALUES (?{', ?' * len(MISTAKE_COLS)})",
        (attempt_id, *(row[c] for c in MISTAKE_COLS)),
    )


def _receipt(conn: sqlite3.Connection, session_id: int) -> dict:
    """Rows commit ② added for one session, read back from tutor.db (so a rerun returns the same receipt)."""
    at = conn.execute("SELECT committed_at FROM session WHERE id = ?", (session_id,)).fetchone()[0]
    by_status = dict(conn.execute(
        "SELECT m.status, count(*) FROM mistake m JOIN attempt a ON a.id = m.attempt_id"
        " WHERE a.session_id = ? AND m.supersedes_id IS NULL GROUP BY m.status", (session_id,)
    ).fetchall())  # fmt: skip
    # a new rubric version is written exactly for the attempts whose no_rubric flag was answered at step 3 (C-16)
    rubric = conn.execute(
        "SELECT count(*) FROM attempt a WHERE a.session_id = ? AND EXISTS"
        " (SELECT 1 FROM json_each(a.flags_json) f WHERE json_extract(f.value, '$.type') = 'no_rubric')", (session_id,)
    ).fetchone()[0]  # fmt: skip
    return {
        "session_id": session_id, "committed_at": at,
        "attempt": conn.execute("SELECT count(*) FROM attempt WHERE session_id = ?", (session_id,)).fetchone()[0],
        "mistake": sum(by_status.values()), "rubric": rubric,
        "by_status": {s: by_status.get(s, 0) for s in ("confirmed", "edited", "rejected", "added")},
    }  # fmt: skip


def commit_session(conn: sqlite3.Connection, session_id: int, *, transcript: str, review_seconds: int | None,
                   attempts: list[dict]) -> dict:  # fmt: skip
    """② in one transaction: rubrics approved at step 3 (C-16), attempts, mistakes, session → committed.

    attempts: {seq, problem_id, rubric_id | None, rubric {items, max_score} (new version when rubric_id is None),
    solution_latex, steps, flags, grade_items, score, max_score, mistakes: [MISTAKE_COLS row, llm_json as dict]}.
    Already committed → the first receipt, nothing written.
    """
    with write_tx(conn):
        st = conn.execute("SELECT status FROM session WHERE id = ?", (session_id,)).fetchone()
        if st is None:
            raise NotFound(f"buổi {session_id}")
        if st[0] == "committed":
            return _receipt(conn, session_id)
        ts = now()
        for a in attempts:
            rubric_id = a["rubric_id"]
            if rubric_id is None:
                v = conn.execute("SELECT coalesce(max(version), 0) + 1 FROM rubric WHERE problem_id = ?",
                                 (a["problem_id"],)).fetchone()[0]  # fmt: skip
                rubric_id = conn.execute(
                    "INSERT INTO rubric (problem_id, version, items_json, max_score, approved_at)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (a["problem_id"], v, json.dumps(a["rubric"]["items"], ensure_ascii=False),
                     a["rubric"]["max_score"], ts),
                ).lastrowid  # fmt: skip
            attempt_id = conn.execute(
                "INSERT INTO attempt (session_id, seq, problem_id, rubric_id, solution_latex, steps_json, flags_json,"
                " grade_json, score, max_score, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (session_id, a["seq"], a["problem_id"], rubric_id, a["solution_latex"],
                 json.dumps(a["steps"], ensure_ascii=False), json.dumps(a["flags"], ensure_ascii=False),
                 json.dumps(a["grade_items"], ensure_ascii=False), a["score"], a["max_score"], ts),
            ).lastrowid  # fmt: skip
            for m in a["mistakes"]:
                _insert_mistake(conn, attempt_id, m | {"reviewed_at": ts})
        conn.execute(
            "UPDATE session SET status = 'committed', committed_at = ?, transcript_latex = ?, review_seconds = ?"
            " WHERE id = ?", (ts, transcript, review_seconds, session_id)
        )  # fmt: skip
        return _receipt(conn, session_id)


def session_detail(conn: sqlite3.Connection, session_id: int) -> dict:
    """A session with its attempts (problem ref, rubric, grade) and every mistake row, llm_json parsed (Buổi học)."""
    rows = _dicts(conn.execute("SELECT * FROM session WHERE id = ?", (session_id,)))
    if not rows:
        raise NotFound(f"buổi {session_id}")
    s = rows[0] | {"student_code": student_code(rows[0]["student_id"])}
    s["attempts"] = _dicts(conn.execute(
        "SELECT a.*, p.ref, r.version AS rubric_version, r.items_json AS rubric_items FROM attempt a"
        " JOIN problem p ON p.id = a.problem_id JOIN rubric r ON r.id = a.rubric_id"
        " WHERE a.session_id = ? ORDER BY a.seq, a.id", (session_id,)
    ))  # fmt: skip
    for a in s["attempts"]:
        a["steps"], a["flags"], a["grade"] = (json.loads(a.pop(k)) for k in ("steps_json", "flags_json", "grade_json"))
        a["rubric"] = {
            "id": a["rubric_id"],
            "version": a.pop("rubric_version"),
            "items": json.loads(a.pop("rubric_items")),
        }
        a["mistakes"] = _dicts(
            conn.execute("SELECT * FROM mistake WHERE attempt_id = ? ORDER BY step_idx, id", (a["id"],))
        )
        for m in a["mistakes"]:
            m["llm_json"] = m["llm_json"] and json.loads(m["llm_json"])
    return s
