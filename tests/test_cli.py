"""MONO-P0-01: `tutor app` = 1 process on 127.0.0.1 holding data/runner.lock."""

import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

import pytest
from filelock import FileLock
from typer.testing import CliRunner

from tests.db.test_profile_repo import D1, D2, WRONG, bank, commit, mk, skill_rows, start  # noqa: F401
from tutor import cli, config
from tutor.db import repo
from tutor.graphs.runner import Runner

TUTOR = [str(Path(sys.executable).with_name("tutor"))]
REPO = Path(__file__).resolve().parents[1]
BANK = REPO / "data" / "dummy" / "bank"


def clean_env(environ) -> dict:
    return {k: v for k, v in environ.items() if not k.startswith(("ANTHROPIC", "OPENAI"))}


# C-34: a child process must never find a real key: not in the developer's shell, and not in the repo .env,
# which `tutor` loads from its cwd, so children start in an empty directory.
ENV = clean_env(os.environ)
_CWD = tempfile.TemporaryDirectory(prefix="tutor-child-")
CHILD = {"env": ENV, "cwd": _CWD.name}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def health(port: int) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=0.5) as r:
            return json.load(r)
    except OSError:
        return None


def run(*args: str, timeout: float = 15) -> subprocess.CompletedProcess:
    return subprocess.run(TUTOR + list(args), capture_output=True, text=True, timeout=timeout, **CHILD)


@pytest.fixture
def running_app(tmp_path):
    port, data = free_port(), tmp_path / "data"
    p = subprocess.Popen(TUTOR + ["app", "--no-browser", "--port", str(port), "--data-dir", str(data)], **CHILD)
    try:
        for _ in range(100):
            if health(port):
                break
            time.sleep(0.1)
        yield port, data
    finally:
        p.terminate()
        p.wait(10)


def test_app_starts_creates_data_and_serves_health(running_app):
    port, data = running_app
    assert health(port)["db"] == "ok"
    for name in ("tutor.db", "runner.lock", "inbox/bank", "out", "logs/app.log", "logs/chat", "backup"):
        assert (data / name).exists(), name
    with closing(sqlite3.connect(data / "tutor.db")) as c:
        assert c.execute("SELECT count(*) FROM kc").fetchone()[0] == 74


def test_second_app_does_not_start_another_process(running_app):
    port, data = running_app
    r = run("app", "--no-browser", "--port", str(port), "--data-dir", str(data))
    assert r.returncode == 0
    assert "đang chạy" in r.stdout


def fake_health(body: dict):
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from threading import Thread

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            raw = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    Thread(target=srv.serve_forever, daemon=True).start()
    return srv


@pytest.mark.parametrize("who", ["other_app", "other_data"])
def test_port_held_by_someone_else_exits_2_without_browser(tmp_path, monkeypatch, who):
    data = tmp_path / "data"
    data.mkdir()
    body = {"status": "ok"} if who == "other_app" else {"status": "ok", "app": "tutor", "data_dir": str(tmp_path / "x")}
    srv = fake_health(body)
    opened = []
    monkeypatch.setattr(cli.webbrowser, "open", opened.append)
    try:
        with FileLock(data / "runner.lock"):
            port = str(srv.server_address[1])
            r = CliRunner().invoke(cli.cli, ["app", "--port", port, "--data-dir", str(data)])
    finally:
        srv.shutdown()
    assert r.exit_code == 2 and not opened
    assert "Traceback" not in r.output and "Cổng" in r.output


def test_port_taken_with_lock_free_exits_2_in_words(tmp_path, monkeypatch):
    srv = fake_health({"status": "ok", "app": "tutor", "data_dir": str(tmp_path / "elsewhere")})
    opened = []
    monkeypatch.setattr(cli.webbrowser, "open", opened.append)
    try:
        r = CliRunner().invoke(
            cli.cli, ["app", "--port", str(srv.server_address[1]), "--data-dir", str(tmp_path / "d")]
        )
    finally:
        srv.shutdown()
    assert r.exit_code == 2 and not opened and "Cổng" in r.output and "Traceback" not in r.output
    assert not (tmp_path / "d" / "tutor.db").exists()
    assert FileLock(tmp_path / "d" / "runner.lock").acquire(timeout=0)  # the lock was released


def test_port_with_non_http_service_exits_2_in_words(tmp_path, monkeypatch):
    import socket as sk
    from threading import Thread

    srv = sk.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen()

    def junk():
        while True:
            try:
                c, _ = srv.accept()
            except OSError:
                return
            c.sendall(b"junk\r\n\r\n")
            c.close()

    Thread(target=junk, daemon=True).start()
    monkeypatch.setattr(cli.webbrowser, "open", lambda u: pytest.fail("opened a browser"))
    try:
        r = CliRunner().invoke(cli.cli, ["app", "--port", str(srv.getsockname()[1]), "--data-dir", str(tmp_path / "d")])
    finally:
        srv.close()
    assert r.exit_code == 2 and "Cổng" in r.output
    assert "Traceback" not in r.output


def test_same_app_same_data_opens_browser(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    srv = fake_health({"status": "ok", "app": "tutor", "data_dir": str(data.resolve())})
    opened = []
    monkeypatch.setattr(cli.webbrowser, "open", opened.append)
    try:
        with FileLock(data / "runner.lock"):
            r = CliRunner().invoke(cli.cli, ["app", "--port", str(srv.server_address[1]), "--data-dir", str(data)])
    finally:
        srv.shutdown()
    assert r.exit_code == 0 and len(opened) == 1


def test_health_names_app_and_data_dir(running_app):
    port, data = running_app
    h = health(port)
    assert h["app"] == "tutor" and h["data_dir"] == str(data.resolve())


def test_lock_held_by_cli_command_exits_2(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    with FileLock(data / "runner.lock"):
        r = run("app", "--no-browser", "--port", str(free_port()), "--data-dir", str(data))
    assert r.returncode == 2
    assert "runner.lock" in r.stdout
    assert not (data / "tutor.db").exists()  # never migrate without the lock


def test_db_endpoint_under_parallel_requests(running_app):
    # Under load the threadpool runs a sync dependency and its endpoint on different threads.
    port, _ = running_app

    def get(_):
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/backup", timeout=5) as r:
            return json.load(r)["total"]

    with ThreadPoolExecutor(16) as ex:
        assert list(ex.map(get, range(64))) == [166] * 64  # 18 error codes + 74 KC + 74 prerequisites


FIX = Path(__file__).resolve().parent / "fixtures" / "submissions"


def test_seed_needs_dev_flag(tmp_path):
    r = run("seed-dummy", "--data-dir", str(tmp_path / "d"))
    assert r.returncode == 1 and "--dev" in r.stdout


def test_env_file_read_by_cli(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-test\n", encoding="utf-8")
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setenv("OPENAI_API_KEY", "")  # records the original so the key set below is undone
    monkeypatch.delenv("OPENAI_API_KEY")
    out = CliRunner().invoke(cli.cli, ["seed-dummy", "--data-dir", str(tmp_path / "d")])
    assert os.environ["OPENAI_API_KEY"] == "sk-test" and "sk-test" not in out.output


# What `tutor app` and every graph command do at start, run for real in a child: the child then lists which API-key
# variables it holds (names only, never values), like tests/ui/check_v3.py KEY_PROBE.
DATA_PROBE = (
    "import os, sys, uvicorn; from pathlib import Path; from tutor import cli, config; "
    "uvicorn.run = lambda *a, **k: None; "  # app_cmd builds the app and returns, nothing listens
    "data = Path(sys.argv[2]); "
    "{call}; "
    "print('KEYS', *[k for k in os.environ if k.startswith(('ANTHROPIC', 'OPENAI'))])"
)
CALLS = {
    "app": "cli.app_cmd(port=1, data_dir=data, no_browser=True, fake_llm=True)",
}


@pytest.mark.parametrize("call", CALLS)
def test_app_reads_data_env(tmp_path, call):
    data = config.paths(tmp_path / "data").ensure()
    repo.init_db(data.tutor_db, data.backup)

    def names() -> list[str]:
        r = subprocess.run([sys.executable, "-c", DATA_PROBE.format(call=CALLS[call]), "-", str(data.root)],
                           capture_output=True, text=True, timeout=60, **CHILD)  # fmt: skip
        assert r.returncode == 0, r.stderr[-500:]
        assert "sk-test-" not in r.stdout + r.stderr
        return r.stdout.splitlines()[-1].split()[1:]  # app_cmd prints its own line first

    assert names() == []  # control: the child's cwd is empty and its env has no key
    (data.root / ".env").write_text("OPENAI_API_KEY=sk-test-" + "c" * 30 + "\n", encoding="utf-8")
    assert names() == ["OPENAI_API_KEY"]
    assert not (Path(CHILD["cwd"]) / ".env").exists()


PROBE = "import os; from tutor import config; config.load_env(config.ENV_FILE); print('OPENAI_API_KEY' in os.environ)"


def sees_key(**kw) -> str:
    r = subprocess.run([sys.executable, "-I", "-c", PROBE], capture_output=True, text=True, timeout=30, **kw)
    return r.stdout.strip()


def test_children_never_see_a_key(tmp_path):
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-fake\n", encoding="utf-8")
    assert sees_key(cwd=tmp_path, env=ENV) == "True"  # control: a child that starts next to a .env loads it
    assert sees_key(**CHILD) == "False"
    assert not (Path(CHILD["cwd"]) / ".env").exists() and Path(CHILD["cwd"]).resolve() != REPO
    assert clean_env({"OPENAI_API_KEY": "x", "ANTHROPIC_API_KEY": "y", "PATH": "p"}) == {"PATH": "p"}


def test_restore_while_app_runs_exits_2(running_app):
    port, data = running_app
    r = run("restore", "tutor-2026-10-20-120000.db", "--data-dir", str(data))
    assert r.returncode == 2 and "runner.lock" in r.stdout


def test_restore_cli(paths, conn):
    repo.add_student(conn, name="An", grade=8)
    b = repo.backup(paths.tutor_db, paths.backup)
    repo.add_student(conn, name="Bình", grade=8)
    r = CliRunner().invoke(cli.cli, ["restore", b.name, "--data-dir", str(paths.root)])
    assert r.exit_code == 0, r.output
    safety = next(p.name for p in paths.backup.glob("tutor-*.db") if p != b)
    assert r.output.strip() == f"Đã khôi phục {b.name} (bản hiện tại: {safety})"
    assert repo.row_counts(conn)["student"] == 1


def test_restore_cli_on_a_new_mac_has_no_old_data_to_name(tmp_path, paths):
    src = tmp_path / "src.db"
    repo.init_db(src, tmp_path / "bk")
    b = repo.backup(src, paths.backup)
    r = CliRunner().invoke(cli.cli, ["restore", b.name, "--data-dir", str(paths.root)])
    assert r.exit_code == 0, r.output
    assert r.output.strip() == f"Đã khôi phục {b.name} (máy chưa có dữ liệu cũ)"
    assert list(paths.backup.iterdir()) == [b]


def test_restore_cli_refusals(paths, conn):
    b = repo.backup(paths.tutor_db, paths.backup)
    r = CliRunner().invoke(cli.cli, ["restore", "../tutor.db", "--data-dir", str(paths.root)])
    assert r.exit_code == 1 and "Không có bản sao lưu" in r.output, r.output
    rn = Runner(paths, {})
    rn._set("g1-hs01-20261020", create=True, graph="G1", status="awaiting_review", student_id=1)
    rn.close()
    r = CliRunner().invoke(cli.cli, ["restore", b.name, "--data-dir", str(paths.root)])
    assert r.exit_code == 1 and "g1-hs01-20261020" in r.output and "Duyệt hoặc huỷ trong app trước" in r.output
    assert list(paths.backup.iterdir()) == [b]  # refused before any safety backup


def garbage_over_tutor_db(paths):
    """A backup with 1 student and 1 unsaved session, then tutor.db, tutor.db-wal and tutor.db-shm overwritten."""
    repo.init_db(paths.tutor_db, paths.backup)
    with closing(repo.connect(paths.tutor_db)) as c:
        repo.add_student(c, name="An", grade=8)
        sid = repo.commit_session_start(c, student_id=1, held_on="2026-10-20", source_path="s01.tex",
                                        source_kind="tex", sha256="a" * 64, thread_id="g1-hs01-20261020")  # fmt: skip
        repo.commit_session_status(c, sid, "awaiting_review")
    b = repo.backup(paths.tutor_db, paths.backup)
    for suffix, data in (("", b"not a database " * 2000), ("-wal", b"wal"), ("-shm", b"shm")):
        paths.tutor_db.with_name(f"tutor.db{suffix}").write_bytes(data)
    return b


def test_restore_cli_recovers_an_unreadable_tutor_db(paths):
    b = garbage_over_tutor_db(paths)
    r = CliRunner().invoke(cli.cli, ["restore", b.name, "--data-dir", str(paths.root)])
    assert r.exit_code == 0, r.output
    kept = next(p for p in paths.root.iterdir() if re.fullmatch(r"tutor\.db\.broken-\d{8}-\d{6}", p.name))
    assert r.output.strip() == f"Đã khôi phục {b.name} (bản hiện tại: {kept.name})"
    assert kept.read_bytes() == b"not a database " * 2000
    assert (kept.with_name(kept.name + "-wal").read_bytes(), kept.with_name(kept.name + "-shm").read_bytes()) == (
        b"wal", b"shm")  # fmt: skip
    with closing(repo.connect(paths.tutor_db)) as c:
        with closing(sqlite3.connect(b)) as src:
            assert repo.row_counts(c) == repo.row_counts(src) | {"session": 0}


def waiting_g1_thread(paths, status="awaiting_review"):
    rn = Runner(paths, {})
    rn._set("g1-hs01-20261020", create=True, graph="G1", status=status, student_id=1)
    rn.close()


def test_restore_cli_refusal_points_to_drop_unfinished(paths):
    b = garbage_over_tutor_db(paths)
    waiting_g1_thread(paths)
    r = CliRunner().invoke(cli.cli, ["restore", b.name, "--data-dir", str(paths.root)])
    assert r.exit_code == 1 and "g1-hs01-20261020" in r.output
    assert r.output.strip().splitlines()[-1] == (
        "Duyệt hoặc huỷ trong app trước. Nếu app không mở được: chạy lại với --drop-unfinished (các việc này sẽ mất)."
    )
    assert paths.tutor_db.read_bytes() == b"not a database " * 2000 and list(paths.backup.iterdir()) == [b]


@pytest.mark.parametrize("status", ["awaiting_review", "running"])  # a "running" row is a dead process's leftover
def test_restore_cli_drop_unfinished_recovers_an_unopenable_app(paths, status):
    b = garbage_over_tutor_db(paths)
    waiting_g1_thread(paths, status)
    r = CliRunner().invoke(cli.cli, ["restore", b.name, "--data-dir", str(paths.root), "--drop-unfinished"])
    assert r.exit_code == 0, r.output
    kept = next(p for p in paths.root.iterdir() if re.fullmatch(r"tutor\.db\.broken-\d{8}-\d{6}", p.name))
    assert kept.read_bytes() == b"not a database " * 2000  # the old data is still kept
    with closing(repo.connect(paths.tutor_db)) as c, closing(sqlite3.connect(b)) as src:
        assert repo.row_counts(c) == repo.row_counts(src) | {"session": 0}
    rn = Runner(paths, {})
    try:
        assert rn.list_threads() == []
    finally:
        rn.close()


def test_restore_cli_old_schema_keeps_the_chosen_backup(tmp_path, paths):
    old = tmp_path / "old"
    old.mkdir()
    for n in ("001", "002"):
        shutil.copy(repo.MIGRATIONS / f"{n}.sql", old / f"{n}.sql")
    repo.init_db(paths.tutor_db, paths.backup, old)  # pending migrations: init_db would back up and prune first
    with closing(repo.connect(paths.tutor_db)) as c:
        repo.add_student(c, name="An", grade=8)
    oldest = repo.backup(paths.tutor_db, paths.backup).rename(paths.backup / "tutor-2020-01-01-000000.db")
    for day in range(2, 32):
        shutil.copy(oldest, paths.backup / f"tutor-2020-01-{day:02d}-000000.db")
    r = CliRunner().invoke(cli.cli, ["restore", oldest.name, "--data-dir", str(paths.root)])
    assert r.exit_code == 0, r.output
    with closing(repo.connect(paths.tutor_db)) as c:
        assert repo.schema_version(c) == repo.latest_version() and repo.row_counts(c)["student"] == 1


def test_restore_cli_corrupt_backup_says_so(paths, conn):
    bad = paths.backup / "tutor-2026-10-20-120000.db"
    bad.write_bytes(b"not a database " * 200)
    r = CliRunner().invoke(cli.cli, ["restore", bad.name, "--data-dir", str(paths.root)])
    assert r.exit_code == 1 and "Bản sao lưu này bị hỏng, không khôi phục được." in r.output
    assert "Traceback" not in r.output and list(paths.backup.iterdir()) == [bad]


def test_restore_cli_failure_names_the_safety_file(paths, conn, monkeypatch):
    repo.add_student(conn, name="An", grade=8)
    b = repo.backup(paths.tutor_db, paths.backup)
    repo.add_student(conn, name="Bình", grade=8)

    def boom(*a, **kw):
        raise repo.MigrationError("004.sql: gài lỗi")

    monkeypatch.setattr(repo, "migrate", boom)
    r = CliRunner().invoke(cli.cli, ["restore", b.name, "--data-dir", str(paths.root)])
    safety = next(p.name for p in paths.backup.iterdir() if p != b)
    assert r.exit_code == 1 and safety in r.output and "Traceback" not in r.output
    assert r.output.splitlines()[-1].strip() == "(MigrationError: 004.sql: gài lỗi)"  # the cause, for the installer
    assert repo.row_counts(conn)["student"] == 2


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file modes")
def test_restore_cli_unwritable_backup_folder_leaves_tutor_db_alone(paths, conn):
    repo.add_student(conn, name="An", grade=8)
    b = repo.backup(paths.tutor_db, paths.backup)
    repo.add_student(conn, name="Bình", grade=8)
    db_bytes = paths.tutor_db.read_bytes()
    paths.backup.chmod(0o555)
    try:
        r = CliRunner().invoke(cli.cli, ["restore", b.name, "--data-dir", str(paths.root)])
    finally:
        paths.backup.chmod(0o755)
    lines = r.output.splitlines()
    assert r.exit_code == 1 and "Traceback" not in r.output
    assert lines[0] == "Không sao lưu được dữ liệu hiện tại (ổ đầy hoặc không ghi được), chưa khôi phục gì."
    assert lines[1].strip().startswith("(OperationalError: ")
    assert paths.tutor_db.read_bytes() == db_bytes and not list(paths.root.glob("tutor.db.broken*"))


def test_restore_cli_refuses_a_backup_of_a_newer_app(paths, conn):
    repo.add_student(conn, name="An", grade=8)
    b = repo.backup(paths.tutor_db, paths.backup)
    with closing(sqlite3.connect(b)) as c:
        c.execute(f"PRAGMA user_version = {repo.latest_version() + 1}")
    db_bytes = paths.tutor_db.read_bytes()
    r = CliRunner().invoke(cli.cli, ["restore", b.name, "--data-dir", str(paths.root)])
    assert r.exit_code == 1 and r.output.strip() == "Bản sao lưu này của bản app mới hơn, cập nhật app trước."
    assert paths.tutor_db.read_bytes() == db_bytes and list(paths.backup.iterdir()) == [b]
