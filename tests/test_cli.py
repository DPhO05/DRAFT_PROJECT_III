"""MONO-P0-01: `tutor app` = 1 process on 127.0.0.1 holding data/runner.lock."""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from filelock import FileLock

TUTOR = [str(Path(sys.executable).with_name("tutor"))]
# C-34: a child process must never find a real key, even if the developer's shell has one.
ENV = {k: v for k, v in os.environ.items() if not k.startswith("ANTHROPIC")}


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
    return subprocess.run(TUTOR + list(args), capture_output=True, text=True, timeout=timeout, env=ENV)


@pytest.fixture
def running_app(tmp_path):
    port, data = free_port(), tmp_path / "data"
    p = subprocess.Popen(TUTOR + ["app", "--no-browser", "--port", str(port), "--data-dir", str(data)], env=ENV)
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
    for name in ("tutor.db", "runner.lock", "inbox/bank", "out", "logs/app.log", "backup"):
        assert (data / name).exists(), name


def test_second_app_does_not_start_another_process(running_app):
    port, data = running_app
    r = run("app", "--no-browser", "--port", str(port), "--data-dir", str(data))
    assert r.returncode == 0
    assert "đang chạy" in r.stdout


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
        assert list(ex.map(get, range(64))) == [18] * 64


FIX = Path(__file__).resolve().parent / "fixtures" / "submissions"


def test_seed_needs_dev_flag(tmp_path):
    r = run("seed-dummy", "--data-dir", str(tmp_path / "d"))
    assert r.returncode == 1 and "--dev" in r.stdout


def test_ingest_runs_g1_in_process(tmp_path):
    data = tmp_path / "data"
    assert run("seed-dummy", "--dev", "--data-dir", str(data), timeout=60).returncode == 0
    from contextlib import closing

    from tutor.db import repo

    with closing(repo.connect(data / "tutor.db")) as c:
        repo.add_student(c, name="An", grade=8)
    (data / "inbox" / "s01.tex").write_bytes((FIX / "s01.tex").read_bytes())
    r = run("ingest", "HS-01", "s01.tex", "--date", "2026-10-20", "--data-dir", str(data), "--fake-llm", timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "g1-hs01-20261020" in r.stdout and "awaiting_review ở gate_review: 5 bài, 5 đề xuất lỗi" in r.stdout
    r = run("ingest", "1", "s01.tex", "--date", "2026-10-21", "--data-dir", str(data), "--fake-llm")
    assert r.returncode == 1 and "trùng" in r.stdout


def test_ingest_while_app_holds_lock_exits_2(running_app):
    port, data = running_app
    (data / "inbox" / "x.tex").write_text("\\begin{problem}[A]\nx\n\\end{problem}\n", encoding="utf-8")
    r = run("ingest", "1", "x.tex", "--data-dir", str(data))
    assert r.returncode == 2 and "runner.lock" in r.stdout


def test_review_queue_then_review_commits(tmp_path):
    data = tmp_path / "data"
    assert run("seed-dummy", "--dev", "--data-dir", str(data), timeout=60).returncode == 0
    from contextlib import closing

    from tutor.db import repo

    with closing(repo.connect(data / "tutor.db")) as c:
        repo.add_student(c, name="An", grade=8)
    (data / "inbox" / "s01.tex").write_bytes((FIX / "s01.tex").read_bytes())
    r = run("ingest", "HS-01", "s01.tex", "--date", "2026-10-20", "--data-dir", str(data), "--fake-llm", timeout=60)
    tid = "g1-hs01-20261020"
    r = run("review", "--data-dir", str(data))
    assert r.returncode == 0 and tid in r.stdout and "5 thẻ" in r.stdout, r.stdout + r.stderr
    # card 1: add a missed mistake, then accept; 2: edit code; 3: reject; 4: pause (saved, nothing written)
    script = "N\n1\n1\nother.unclear\nsót bước\nA\nE\npresentation.format\n\n\nR\n\nQ\n"
    r = subprocess.run(TUTOR + ["review", tid, "--data-dir", str(data)], input=script, capture_output=True,
                       text=True, timeout=60, env=ENV)  # fmt: skip
    assert r.returncode == 0 and "đã lưu" in r.stdout, r.stdout + r.stderr
    with closing(repo.connect(data / "tutor.db")) as c:
        assert c.execute("SELECT status FROM session").fetchone()[0] == "awaiting_review"
    r = subprocess.run(TUTOR + ["review", tid, "--data-dir", str(data)], input="A\nA\n", capture_output=True,
                       text=True, timeout=60, env=ENV)  # fmt: skip
    assert r.returncode == 0 and "committed" in r.stdout and "+5 attempt" in r.stdout, r.stdout + r.stderr
    with closing(repo.connect(data / "tutor.db")) as c:
        assert c.execute("SELECT status FROM session").fetchone()[0] == "committed"
        got = sorted(x[0] for x in c.execute("SELECT status FROM mistake"))
    assert got == ["added", "confirmed", "confirmed", "confirmed", "edited", "rejected"]
