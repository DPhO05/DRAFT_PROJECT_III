"""The only module that writes tutor.db: connect, init, migrate, backup, reads, writes."""

import csv
import io
import json
import re
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path

from tutor.config import THETA0, student_code
from tutor.services import elo, latex
from tutor.services.bank import level_delta, rubric_items
from tutor.services.search import items_by_id

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


class BackupCorrupt(ValueError):
    """The chosen backup file cannot be read as a tutor.db (422)."""

    def __init__(self):
        super().__init__("Bản sao lưu này bị hỏng, không khôi phục được.")


class BackupTooNew(ValueError):
    """The backup was written by a newer app than this one (422): restoring it would leave a DB this app cannot read."""

    def __init__(self):
        super().__init__("Bản sao lưu này của bản app mới hơn, cập nhật app trước.")


class NotRestored(Exception):
    """Restore stopped before tutor.db moved: a file could not be read or written (500 restore_failed)."""


class RestoreFailed(Exception):
    """Restore failed after tutor.db was touched; `safety` holds the data from before it (500 restore_failed)."""

    def __init__(self, safety: str):
        super().__init__(f"Chưa khôi phục được. Dữ liệu trước khi khôi phục nằm ở {safety}.")
        self.safety = safety


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


class WorksheetExists(Exception):
    """The student already has a live sheet for this date and the new one is different (409 worksheet_exists)."""

    def __init__(self, for_date: str, n_problems: int):
        super().__init__(f"Ngày {for_date} đã có phiếu {n_problems} bài")
        self.for_date, self.n_problems = for_date, n_problems


class ReportApproved(Exception):
    """The period already has an approved report (409 already_committed, C-44)."""

    def __init__(self, report_id: int, approved_at: str):
        super().__init__("Kỳ này đã duyệt báo cáo: mỗi kỳ chỉ duyệt một lần")
        self.report_id, self.approved_at = report_id, approved_at


class StaleProfile(Exception):
    """The student's skill_* prior changed since the preview was computed (another session committed first)."""


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
    try:
        with closing(connect(db_path)) as src, closing(sqlite3.connect(dst)) as out:
            src.backup(out)
            out.execute("PRAGMA journal_mode = DELETE")  # backup = 1 self-contained file
    except BaseException:
        with suppress(OSError):  # a failed copy must not stay in the list; a read-only folder must not hide why
            dst.unlink(missing_ok=True)
        raise
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


def read_backup(backup_dir: Path, name: str) -> sqlite3.Connection:
    """Backup `name` loaded into memory (caller closes it). NotFound, BackupCorrupt or BackupTooNew when unusable."""
    src = backup_dir / name
    if not _BACKUP_RE.fullmatch(name) or not src.is_file():
        raise NotFound(f"Bản sao lưu {name}")
    mem = sqlite3.connect(":memory:")
    try:
        with closing(connect(src, readonly=True)) as f:
            f.backup(mem)
        ok = mem.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        if not ok or mem.execute("SELECT 1 FROM sqlite_master WHERE name = 'student'").fetchone() is None:
            raise BackupCorrupt
    except sqlite3.OperationalError as e:  # locked, unreadable: not a damaged file
        mem.close()
        raise NotRestored("Không đọc được bản sao lưu này (ổ lỗi hoặc không đọc được), chưa khôi phục gì.") from e
    except (sqlite3.DatabaseError, BackupCorrupt) as e:
        mem.close()
        raise BackupCorrupt from e
    if schema_version(mem) > latest_version():
        mem.close()
        raise BackupTooNew
    return mem


def _set_aside(db_path: Path, companions: dict[str, bytes]) -> str:
    """Move an unreadable tutor.db and its -wal / -shm to tutor.db.broken-<time>, a name no prune pattern matches.

    The -wal / -shm copies are written before tutor.db moves, so a full disk stops with tutor.db still in place."""
    stamp, n = f"{datetime.now():%Y%m%d-%H%M%S}", 1
    kept = db_path.with_name(f"{db_path.name}.broken-{stamp}")
    while kept.exists():
        n += 1
        kept = db_path.with_name(f"{db_path.name}.broken-{stamp}-{n}")
    written = []
    try:
        for suffix, data in companions.items():
            written.append(kept.with_name(kept.name + suffix))
            written[-1].write_bytes(data)
        if db_path.exists():
            db_path.rename(kept)
    except OSError as e:
        for p in written:
            with suppress(OSError):
                p.unlink(missing_ok=True)
        raise NotRestored("Không giữ lại được dữ liệu cũ (ổ đầy hoặc không ghi được), chưa khôi phục gì.") from e
    for suffix in ("-wal", "-shm"):
        db_path.with_name(db_path.name + suffix).unlink(missing_ok=True)
    return kept.name


def _into(dst_path: Path, src: sqlite3.Connection) -> None:
    with closing(connect(dst_path)) as dst:
        src.backup(dst)
        dst.execute("PRAGMA journal_mode = WAL")  # a destination already in WAL keeps it; a new file does not


def restore(db_path: Path, backup_dir: Path, name: str) -> dict:
    """Put backup `name` back as tutor.db. Caller holds runner.lock and has checked no thread is unfinished (R7).

    The chosen file is read into memory first: the safety backup below runs `_prune`, which may delete that very file,
    and a bad file must fail before anything moves. An unreadable tutor.db cannot be backed up, so it is set aside.
    """
    with closing(read_backup(backup_dir, name)) as mem:
        # closing a connection to an unreadable file deletes its -wal / -shm, so hold their bytes for _set_aside
        companions = {
            x: p.read_bytes() for x in ("-wal", "-shm") if (p := db_path.with_name(db_path.name + x)).exists()
        }
        safety = None  # a missing tutor.db (new Mac) holds nothing to keep, and connect() would make an empty one
        if db_path.exists():
            try:
                safety = backup(db_path, backup_dir)
            except (sqlite3.OperationalError, OSError) as e:  # locked, disk full, folder not writable: tutor.db is fine
                raise NotRestored(
                    "Không sao lưu được dữ liệu hiện tại (ổ đầy hoặc không ghi được), chưa khôi phục gì."
                ) from e
            except sqlite3.DatabaseError:  # not a database / malformed: it cannot be backed up, so keep it aside
                safety = db_path.with_name(_set_aside(db_path, companions))
        try:
            _into(db_path, mem)
            migrate(db_path, backup_dir, backup_first=False)
            with closing(connect(db_path)) as conn:
                with write_tx(conn):  # attempts are written only at commit ②: a session without one saved nothing
                    dropped = conn.execute(
                        "DELETE FROM session WHERE status <> 'committed'"
                        " AND NOT EXISTS (SELECT 1 FROM attempt WHERE session_id = session.id)"
                    ).rowcount  # fmt: skip
                rows = sum(row_counts(conn).values())
        except Exception as e:
            if safety is None:  # nothing was there before: leave nothing half-restored
                for x in ("", "-wal", "-shm"):
                    db_path.with_name(db_path.name + x).unlink(missing_ok=True)
                raise NotRestored("Chưa khôi phục được. Máy này chưa có dữ liệu nào nên không mất gì.") from e
            # shortcut: a set-aside file is not copied back (it was unreadable); the restored copy stays
            if safety.parent == backup_dir:
                with suppress(sqlite3.Error), closing(connect(safety, readonly=True)) as f:
                    _into(db_path, f)
            raise RestoreFailed(safety.name) from e
    return {"restored": name, "safety_backup": safety and safety.name, "rows": rows, "sessions_dropped": dropped}


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


def ensure_catalog(conn: sqlite3.Connection, kc_csv: Path, prereq_csv: Path) -> int:
    """First run: load the default catalog into an empty `kc` table. Returns the KC added; 0 when KC exist."""
    if conn.execute("SELECT 1 FROM kc").fetchone():
        return 0
    kcs, pre = read_catalog(kc_csv.read_text("utf-8-sig"), prereq_csv.read_text("utf-8-sig"))
    return len(import_catalog(conn, kcs, pre, apply=True)["new_kc"])


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
                    "UPDATE kc SET name = ?, description = ?, lop = ? WHERE code = ?",
                    (k["name"], k["description"], int(k["lop"]) if k["lop"] else None, c),
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
        "SELECT k.id, k.code, k.name, k.description, k.parent_id, k.lop"
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
    """name / description / parent_id / lop."""
    allowed = {k: v for k, v in fields.items() if k in ("name", "description", "parent_id", "lop")}
    with write_tx(conn):
        if conn.execute("SELECT 1 FROM kc WHERE id = ?", (kc_id,)).fetchone() is None:
            raise NotFound(f"KC {kc_id}")
        if "parent_id" in allowed:
            _check_parent(conn, kc_id, allowed["parent_id"])
        for k, v in allowed.items():
            conn.execute(f"UPDATE kc SET {k} = ? WHERE id = ?", (v, kc_id))


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


def unarchive_student(conn: sqlite3.Connection, student_id: int) -> None:
    with write_tx(conn):
        if conn.execute("UPDATE student SET archived_at = NULL WHERE id = ?", (student_id,)).rowcount == 0:
            raise NotFound(f"HS {student_id}")


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
def _insert_problem(
    conn: sqlite3.Connection,
    *,
    ref: str,
    statement: str,
    solution: str,
    source: str,
    delta: float | None,
    tags: list[tuple[int, int, str]],
    rubric_items: list[dict],
) -> int:
    """Rows of one approved problem; the caller owns the transaction and checked that ref is free."""
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
        return _insert_problem(
            conn, ref=ref, statement=statement, solution=solution, source=source, delta=delta, tags=tags,
            rubric_items=rubric_items,
        )  # fmt: skip


def import_bank(conn: sqlite3.Connection, items: list[dict]) -> dict:
    """G2 commit: every item (keys of _insert_problem) in one transaction; a ref that is already there is skipped."""
    added = 0
    with write_tx(conn):
        for it in items:
            if conn.execute("SELECT 1 FROM problem WHERE ref = ?", (it["ref"],)).fetchone() is None:
                _insert_problem(conn, **it)
                added += 1
    return {"added": added, "skipped_existing": len(items) - added}


def bank_problems(conn: sqlite3.Connection) -> list[dict]:
    """Every problem with whether it has an approved rubric (01 Ingest context)."""
    return _dicts(conn.execute(
        "SELECT p.id, p.ref, p.statement_latex, EXISTS (SELECT 1 FROM rubric r WHERE r.problem_id = p.id) AS has_rubric"
        " FROM problem p ORDER BY p.ref"
    ))  # fmt: skip


def bank_created_at(conn: sqlite3.Connection) -> dict[str, str]:
    """ref → created_at of every problem."""
    return dict(conn.execute("SELECT ref, created_at FROM problem"))


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


def problem_view(conn: sqlite3.Connection, problem_id: int) -> dict:
    """problem_detail + the grid card fields + source, has_attempts and the solution split into paragraphs."""
    detail = problem_detail(conn, problem_id)
    source = conn.execute("SELECT source FROM problem WHERE id = ?", (problem_id,)).fetchone()[0]
    attempted = conn.execute("SELECT EXISTS (SELECT 1 FROM attempt WHERE problem_id = ?)", (problem_id,)).fetchone()[0]
    sol = detail["solution_latex"]
    return {
        **items_by_id(conn, [problem_id])[0],
        **detail,
        "source": source,
        "has_attempts": bool(attempted),
        "solution_steps": [s.latex for s in latex.split_steps(sol, 0, len(sol), by="paragraph")],
    }


def problem_tech(conn: sqlite3.Connection, problem_id: int) -> dict:
    """The numbers behind a problem's level, and the replay command for every student who attempted it."""
    row = conn.execute(
        "SELECT delta, difficulty_approved_at FROM problem WHERE id = ?", (problem_id,)
    ).fetchone()  # fmt: skip
    if row is None:
        raise NotFound(f"bài {problem_id}")
    students = conn.execute(
        "SELECT DISTINCT s.student_id FROM attempt a JOIN session s ON s.id = a.session_id"
        " WHERE a.problem_id = ? ORDER BY 1",
        (problem_id,),
    )  # fmt: skip
    return {
        "delta": row[0],
        "difficulty_approved_at": row[1],
        "replay_hint": [f"Dựng lại hồ sơ {student_code(sid)} (menu ⚙)" for (sid,) in students],
    }


def update_problem_labels(conn: sqlite3.Connection, problem_id: int, **fields) -> None:
    """kc_ids / level / rubric_items. Applies from now on: old skill_event and attempt.rubric_id stay as they are."""
    if unknown := fields.keys() - {"kc_ids", "level", "rubric_items"}:
        raise ValueError(f"Không sửa được: {', '.join(sorted(unknown))}")
    kc_ids = fields.get("kc_ids")
    if "kc_ids" in fields and (not isinstance(kc_ids, list) or not kc_ids):
        raise ValueError("Chọn ít nhất 1 kỹ năng")
    delta = level_delta(fields["level"]) if "level" in fields else None
    items = rubric_items(fields["rubric_items"]) if "rubric_items" in fields else None
    with write_tx(conn):
        if conn.execute("SELECT 1 FROM problem WHERE id = ?", (problem_id,)).fetchone() is None:
            raise NotFound(f"bài {problem_id}")
        at = now()
        if kc_ids:
            kc_ids = list(dict.fromkeys(kc_ids))
            marks = ", ".join("?" * len(kc_ids))
            if conn.execute(f"SELECT count(*) FROM kc WHERE id IN ({marks})", kc_ids).fetchone()[0] != len(kc_ids):
                raise ValueError("Có kỹ năng không tồn tại")
            conn.execute("DELETE FROM problem_kc WHERE problem_id = ?", (problem_id,))
            conn.executemany(
                "INSERT INTO problem_kc (problem_id, kc_id, step_idx, evidence_latex, approved_at)"
                " VALUES (?, ?, 0, NULL, ?)",
                [(problem_id, k, at) for k in kc_ids],
            )
        if "level" in fields:
            conn.execute(
                "UPDATE problem SET delta = ?, difficulty_approved_at = ? WHERE id = ?",
                (delta, at if delta is not None else None, problem_id),
            )
        if items:
            conn.execute(
                "INSERT INTO rubric (problem_id, version, items_json, max_score, approved_at)"
                " VALUES (?, (SELECT COALESCE(MAX(version), 0) + 1 FROM rubric WHERE problem_id = ?), ?, ?, ?)",
                (problem_id, problem_id, json.dumps(items, ensure_ascii=False), sum(i["points"] for i in items), at),
            )


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
        "skill_event": conn.execute(
            "SELECT count(*) FROM skill_event e JOIN attempt a ON a.id = e.attempt_id WHERE a.session_id = ?",
            (session_id,)
        ).fetchone()[0],
        "by_status": {s: by_status.get(s, 0) for s in ("confirmed", "edited", "rejected", "added")},
    }  # fmt: skip


def profile_prior(conn: sqlite3.Connection, student_id: int) -> dict:
    """Prior for `elo.profile`: stored skill_state / misconception_log + codes of the latest committed session."""
    skills = _dicts(conn.execute(
        "SELECT kc_id, theta, n_attempts, correct_streak FROM skill_state WHERE student_id = ? ORDER BY kc_id",
        (student_id,)
    ))  # fmt: skip
    miscon = _dicts(conn.execute(
        "SELECT code, kc_id, first_seen, last_seen, count, resolved_at FROM misconception_log"
        " WHERE student_id = ? ORDER BY code, kc_id", (student_id,)
    ))  # fmt: skip
    codes = conn.execute(
        "SELECT DISTINCT m.code FROM mistake_current m JOIN attempt a ON a.id = m.attempt_id WHERE a.session_id ="
        " (SELECT id FROM session WHERE student_id = ? AND status = 'committed'"
        "  ORDER BY held_on DESC, committed_at DESC, id DESC LIMIT 1) ORDER BY m.code", (student_id,)
    ).fetchall()  # fmt: skip
    return {"skills": skills, "miscon": miscon, "prev_codes": [c for (c,) in codes]}


def profile_problems(conn: sqlite3.Connection, problem_ids: list[int]) -> dict[int, dict]:
    """{problem_id: {delta (NULL -> 0, C-19), kcs: [kc_id]}} for the Elo update."""
    if not problem_ids:
        return {}
    marks = ", ".join("?" * len(problem_ids))
    out = {
        pid: {"delta": d, "kcs": []}
        for pid, d in conn.execute(f"SELECT id, coalesce(delta, 0) FROM problem WHERE id IN ({marks})", problem_ids)
    }
    for pid, kc in conn.execute(
        f"SELECT DISTINCT problem_id, kc_id FROM problem_kc WHERE problem_id IN ({marks}) ORDER BY kc_id", problem_ids
    ):  # fmt: skip
        out[pid]["kcs"].append(kc)
    return out


def _write_profile(conn: sqlite3.Connection, student_id: int, held_on: str, ts: str, profile: dict,
                   attempt_ids: dict[int, int]) -> None:  # fmt: skip
    """skill_event rows (seq → attempt id), skill_state and misconception_log upserts of one `elo.profile` result."""
    conn.executemany(
        "INSERT INTO skill_event (student_id, kc_id, attempt_id, outcome, p_expected, theta_before, theta_after,"
        " delta, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(student_id, e["kc_id"], attempt_ids[e["seq"]], e["outcome"], e["p_expected"], e["theta_before"],
          e["theta_after"], e["delta"], ts) for e in profile["events"]],
    )  # fmt: skip
    conn.executemany(
        "INSERT INTO skill_state (student_id, kc_id, theta, n_attempts, correct_streak, last_seen, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (student_id, kc_id) DO UPDATE SET theta = excluded.theta,"
        " n_attempts = excluded.n_attempts, correct_streak = excluded.correct_streak,"
        " last_seen = excluded.last_seen, updated_at = excluded.updated_at",
        [(student_id, s["kc_id"], s["theta"], s["n_attempts"], s["correct_streak"], held_on, ts)
         for s in profile["skills"]],
    )  # fmt: skip
    conn.executemany(
        "INSERT INTO misconception_log (student_id, code, kc_id, first_seen, last_seen, count, resolved_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (student_id, code, kc_id) DO UPDATE SET"
        " first_seen = excluded.first_seen, last_seen = excluded.last_seen, count = excluded.count,"
        " resolved_at = excluded.resolved_at",
        [(student_id, m["code"], m["kc_id"], m["first_seen"], m["last_seen"], m["count"], m["resolved_at"])
         for m in profile["miscon"]],
    )  # fmt: skip


def commit_session(conn: sqlite3.Connection, session_id: int, *, transcript: str, review_seconds: int | None,
                   attempts: list[dict], profile: dict | None = None, prior: dict | None = None) -> dict:  # fmt: skip
    """② in one transaction: rubrics approved at step 3 (C-16), attempts, mistakes, skill_*, session → committed.

    attempts: {seq, problem_id, rubric_id | None, rubric {items, max_score} (new version when rubric_id is None),
    solution_latex, steps, flags, grade_items, score, max_score, mistakes: [MISTAKE_COLS row, llm_json as dict]}.
    profile: the `elo.profile` result for these attempts; its events, skills and misconceptions are written too.
    prior: the `profile_prior` that result was computed over; if the student's prior differs now → StaleProfile.
    An earlier uncommitted session of the student → StaleProfile too (C-28 date order, also for reruns).
    Already committed → the first receipt, nothing written.
    """
    with write_tx(conn):
        st = conn.execute("SELECT status, student_id, held_on FROM session WHERE id = ?", (session_id,)).fetchone()
        if st is None:
            raise NotFound(f"buổi {session_id}")
        if st[0] == "committed":
            return _receipt(conn, session_id)
        if conn.execute("SELECT 1 FROM session WHERE student_id = ? AND held_on < ? AND status <> 'committed'",
                        (st[1], st[2])).fetchone():  # fmt: skip
            raise StaleProfile(f"buổi {session_id}: buổi sớm hơn của HS chưa lưu")
        if prior is not None and profile_prior(conn, st[1]) != prior:
            raise StaleProfile(f"buổi {session_id}: hồ sơ kỹ năng đã đổi từ lúc xem trước")
        ts, attempt_ids = now(), {}
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
            attempt_ids[a["seq"]] = attempt_id
            for m in a["mistakes"]:
                _insert_mistake(conn, attempt_id, m | {"reviewed_at": ts})
        if profile is not None:
            _write_profile(conn, st[1], st[2], ts, profile, attempt_ids)
        conn.execute(
            "UPDATE session SET status = 'committed', committed_at = ?, transcript_latex = ?, review_seconds = ?"
            " WHERE id = ?", (ts, transcript, review_seconds, session_id)
        )  # fmt: skip
        return _receipt(conn, session_id)


def worksheet_problem_ids(conn: sqlite3.Connection, student_id: int, for_date: str) -> list[int]:
    """Problems of the student's live sheet for the date, in sheet order; [] when there is none."""
    return [r[0] for r in conn.execute(
        "SELECT problem_id FROM recommendation WHERE student_id = ? AND for_date = ? AND status <> 'rejected'"
        " ORDER BY position, id", (student_id, for_date))]  # fmt: skip


def commit_worksheet(conn: sqlite3.Connection, *, student_id: int, for_date: str, items: list[dict],
                     replace: bool) -> dict:  # fmt: skip
    """G4 commit in one transaction: items = [{problem_id, kc_id, bucket, reason}] in sheet order.

    A live sheet for the date that has exactly these problems is a rerun: receipt, nothing written. A different
    one raises WorksheetExists, or with `replace` is marked rejected before the new rows go in (C-45).
    Returns {for_date, n_problems, replaced}."""
    if not items:
        raise ValueError("Phiếu cần ít nhất 1 bài")
    with write_tx(conn):
        live = worksheet_problem_ids(conn, student_id, for_date)
        if live == [i["problem_id"] for i in items]:
            # the rows a replace rejected carry the time the live rows were made
            again = conn.execute(
                "SELECT EXISTS (SELECT 1 FROM recommendation o WHERE o.student_id = ?1 AND o.for_date = ?2"
                " AND o.status = 'rejected' AND o.reviewed_at = (SELECT max(reviewed_at) FROM recommendation"
                " WHERE student_id = ?1 AND for_date = ?2 AND status <> 'rejected'))",
                (student_id, for_date),
            ).fetchone()[0]
            return {"for_date": for_date, "n_problems": len(live), "replaced": bool(again)}
        if live and not replace:
            raise WorksheetExists(for_date, len(live))
        ts = now()
        conn.execute("UPDATE recommendation SET status = 'rejected', reviewed_at = ? WHERE student_id = ?"
                     " AND for_date = ? AND status <> 'rejected'", (ts, student_id, for_date))  # fmt: skip
        conn.executemany(
            "INSERT INTO recommendation (student_id, for_date, problem_id, kc_id, bucket, reason, status, reviewed_at,"
            " position) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(student_id, for_date, i["problem_id"], i["kc_id"], i["bucket"], i["reason"],
              "approved" if i["bucket"] else "added", ts, n) for n, i in enumerate(items, 1)],
        )  # fmt: skip
        return {"for_date": for_date, "n_problems": len(items), "replaced": bool(live)}


def worksheets(conn: sqlite3.Connection, student_id: int) -> list[dict]:
    """The student's live sheets (not rejected) grouped by for_date, newest first, each item in sheet order."""
    rows = _dicts(conn.execute(
        "SELECT for_date, position, problem_id, reason, reviewed_at FROM recommendation"
        " WHERE student_id = ? AND status <> 'rejected' ORDER BY for_date DESC, position, id", (student_id,)
    ))  # fmt: skip
    cards = {c["id"]: c for c in items_by_id(conn, [r["problem_id"] for r in rows])}
    out: dict[str, dict] = {}
    for r in rows:
        c = cards[r["problem_id"]]
        sheet = out.setdefault(r["for_date"], {"student_id": student_id, "for_date": r["for_date"], "n_problems": 0,
                                               "created_at": r["reviewed_at"], "items": []})  # fmt: skip
        sheet["n_problems"] += 1
        sheet["items"].append({
            "position": r["position"], "ref": c["ref"], "problem_id": c["id"], "level": c["level"],
            "kcs": [k["name"] for k in c["kcs"]], "reason": r["reason"], "statement_latex": c["statement_latex"],
        })  # fmt: skip
    return list(out.values())


_PERIOD = "student_id = ? AND period_kind = ? AND period_start = ?"


def report_for(conn: sqlite3.Connection, student_id: int, period_kind: str, period_start: str) -> dict | None:
    """{id, approved_at} of the period's approved report, None when it has none."""
    rows = _dicts(conn.execute(f"SELECT id, approved_at FROM report WHERE {_PERIOD}",
                               (student_id, period_kind, period_start)))  # fmt: skip
    return rows[0] if rows else None


def commit_report(conn: sqlite3.Connection, *, student_id: int, period_kind: str, period_start: str, facts: list,
                  text_md: str, audit: dict) -> dict:  # fmt: skip
    """G5 commit in one transaction. The period's row with this same text is a rerun (file error): that row back;
    any other text raises ReportApproved (one approval per period). Returns {report_id, approved_at}."""
    with write_tx(conn):
        row = conn.execute(f"SELECT id, approved_at, text_md FROM report WHERE {_PERIOD}",
                           (student_id, period_kind, period_start)).fetchone()  # fmt: skip
        if row and row[2] == text_md:
            return {"report_id": row[0], "approved_at": row[1]}
        if row:
            raise ReportApproved(row[0], row[1])
        ts = now()
        rid = conn.execute(
            "INSERT INTO report (student_id, period_kind, period_start, facts_json, text_md, audit_json, approved_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (student_id, period_kind, period_start, json.dumps(facts, ensure_ascii=False), text_md,
             json.dumps(audit, ensure_ascii=False), ts),
        ).lastrowid  # fmt: skip
        return {"report_id": rid, "approved_at": ts}


_REPORT = "SELECT id, student_id, period_kind, period_start, approved_at"


def reports(conn: sqlite3.Connection, student_id: int | None = None) -> list[dict]:
    """Approved reports, newest first; one student's when student_id is given."""
    where, args = ("WHERE student_id = ?", (student_id,)) if student_id is not None else ("", ())
    return _dicts(conn.execute(f"{_REPORT} FROM report {where} ORDER BY approved_at DESC, id DESC", args))


def report(conn: sqlite3.Connection, report_id: int) -> dict:
    rows = _dicts(conn.execute(f"{_REPORT}, text_md FROM report WHERE id = ?", (report_id,)))
    if not rows:
        raise NotFound(f"báo cáo {report_id}")
    return rows[0]


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


def replay_student(conn: sqlite3.Connection, student_id: int) -> dict:
    """Rebuild skill_event / skill_state / misconception_log of one student from committed sessions, in one transaction.

    Sessions run in the order they were committed (held_on, committed_at, id), each through `elo.profile` and the
    same writer as commit ②. Returns the event count and the KCs whose level word changed.
    """
    with write_tx(conn):
        before = dict(conn.execute("SELECT kc_id, theta FROM skill_state WHERE student_id = ?", (student_id,)))
        for table in ("skill_event", "skill_state", "misconception_log"):
            conn.execute(f"DELETE FROM {table} WHERE student_id = ?", (student_id,))
        prior, events = elo.empty_prior(), 0
        # shortcut: committed_at has 1 s resolution, a same-second tie replays in id order;
        # store sub-second commit time if two commits per second become possible
        sessions = conn.execute(
            "SELECT id, held_on, committed_at FROM session WHERE student_id = ? AND status = 'committed'"
            " ORDER BY held_on, committed_at, id", (student_id,)
        ).fetchall()  # fmt: skip
        for sid, held_on, committed_at in sessions:
            rows = conn.execute("SELECT id, seq, problem_id FROM attempt_current WHERE session_id = ? ORDER BY seq",
                                (sid,)).fetchall()  # fmt: skip
            probs = profile_problems(conn, [pid for _, _, pid in rows])
            mistakes: dict[int, list[dict]] = {}
            for aid, code, kc in conn.execute(
                "SELECT m.attempt_id, m.code, m.kc_id FROM mistake_current m JOIN attempt_current a"
                " ON a.id = m.attempt_id WHERE a.session_id = ? ORDER BY m.id", (sid,)
            ):  # fmt: skip
                mistakes.setdefault(aid, []).append({"code": code, "kc_id": kc})
            attempts = [{"seq": seq, **probs[pid], "mistakes": mistakes.get(aid, [])} for aid, seq, pid in rows]
            out = elo.profile(prior, attempts, held_on)
            _write_profile(conn, student_id, held_on, committed_at, out, {seq: aid for aid, seq, _ in rows})
            prior, events = out["after"], events + len(out["events"])
        after = dict(conn.execute("SELECT kc_id, theta FROM skill_state WHERE student_id = ?", (student_id,)))
        changes = [
            {"kc_id": kc, "before": elo.level(before.get(kc, THETA0)), "after": elo.level(after.get(kc, THETA0))}
            for kc in sorted(before.keys() | after.keys())
        ]  # fmt: skip
        return {"events": events, "level_changes": [c for c in changes if c["before"] != c["after"]]}
