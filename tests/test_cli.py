"""MONO-P0-01: `tutor app` = 1 process on 127.0.0.1 holding data/runner.lock."""

import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from filelock import FileLock
from typer.testing import CliRunner

from tests.assistant_fix import world
from tests.db.test_profile_repo import D1, D2, WRONG, bank, commit, mk, skill_rows, start  # noqa: F401
from tests.fakes import FakeLLM
from tests.graphs.test_report import writer
from tutor import cli, config, llm
from tutor.db import repo
from tutor.graphs.registry import make_runner
from tutor.graphs.runner import Runner
from tutor.services import elo

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


def test_env_file_read_by_cli(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-test\n", encoding="utf-8")
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setenv("OPENAI_API_KEY", "")  # records the original so the key set below is undone
    monkeypatch.delenv("OPENAI_API_KEY")
    out = CliRunner().invoke(cli.cli, ["seed-dummy", "--data-dir", str(tmp_path / "d")])
    assert os.environ["OPENAI_API_KEY"] == "sk-test" and "sk-test" not in out.output


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


def test_ingest_runs_g1_in_process(tmp_path):
    data = tmp_path / "data"
    assert run("seed-dummy", "--dev", "--bank", str(BANK), "--data-dir", str(data), timeout=60).returncode == 0
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
    assert run("seed-dummy", "--dev", "--bank", str(BANK), "--data-dir", str(data), timeout=60).returncode == 0
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
                       text=True, timeout=60, **CHILD)  # fmt: skip
    assert r.returncode == 0 and "đã lưu" in r.stdout, r.stdout + r.stderr
    with closing(repo.connect(data / "tutor.db")) as c:
        assert c.execute("SELECT status FROM session").fetchone()[0] == "awaiting_review"
    r = subprocess.run(TUTOR + ["review", tid, "--data-dir", str(data)], input="A\nA\nn\n", capture_output=True,
                       text=True, timeout=60, **CHILD)  # fmt: skip
    assert r.returncode == 0 and "Lưu kết quả?" in r.stdout, r.stdout + r.stderr  # N: preview shown, then asked
    assert "Xem trước" in r.stdout
    assert f"Đang chờ Lưu kết quả. Lưu sau: tutor review {tid}" in r.stdout, r.stdout + r.stderr
    with closing(repo.connect(data / "tutor.db")) as c:  # stopped before commit ②
        assert c.execute("SELECT status FROM session").fetchone()[0] == "awaiting_review"
        assert c.execute("SELECT count(*) FROM mistake").fetchone()[0] == 0
    with closing(sqlite3.connect(data / "checkpoints.db")) as c:  # the keys typed above became these decisions
        row = c.execute("SELECT node, decisions_json FROM tutor_thread").fetchone()
    assert row[0] == "gate_confirm_commit"
    cards = json.loads(row[1])["cards"]
    assert {k: v["action"] for k, v in cards.items()} == {
        "n1": "add", "p1": "accept", "p2": "edit", "p3": "reject", "p4": "accept", "p5": "accept"}  # fmt: skip
    assert (cards["n1"]["code"], cards["n1"]["description"]) == ("other.unclear", "sót bước")
    assert cards["p2"]["code"] == "presentation.format"
    # at the preview: no cards asked again, straight to the question; N keeps the gate
    r = subprocess.run(TUTOR + ["review", tid, "--data-dir", str(data)], input="n\n", capture_output=True,
                       text=True, timeout=60, **CHILD)  # fmt: skip
    assert r.returncode == 0 and "Xem trước" in r.stdout and "Lưu kết quả?" in r.stdout, r.stdout + r.stderr
    assert "A đồng ý" not in r.stdout and f"Đang chờ Lưu kết quả. Lưu sau: tutor review {tid}" in r.stdout
    r = subprocess.run(TUTOR + ["review", tid, "--data-dir", str(data)], input="y\n", capture_output=True,
                       text=True, timeout=60, **CHILD)  # fmt: skip
    assert r.returncode == 0 and "committed" in r.stdout and "+5 attempt" in r.stdout, r.stdout + r.stderr
    assert "skill_event" in r.stdout and "Đang chờ" not in r.stdout
    with closing(repo.connect(data / "tutor.db")) as c:
        assert c.execute("SELECT status FROM session").fetchone()[0] == "committed"
        got = sorted(x[0] for x in c.execute("SELECT status FROM mistake"))
    assert got == ["added", "confirmed", "confirmed", "confirmed", "edited", "rejected"]


def replay(paths, *args):
    return CliRunner().invoke(cli.cli, ["replay", *args, "--data-dir", str(paths.root)])


def backups(paths):
    return list(paths.backup.glob("tutor-*.db"))


@pytest.fixture
def committed(conn, bank):  # noqa: F811
    """HS-01 with two committed sessions on KC 'Chuyển vế': right, then wrong."""
    sid = repo.add_student(conn, name="An")
    for day, work in ((D1, [(bank["p1"], [])]), (D2, [(bank["p1"], [mk(WRONG, bank["k1"])])])):
        commit(conn, start(conn, sid, day), work)
    return sid


def test_replay_after_commit_changes_nothing(paths, conn, committed):
    before, n = skill_rows(conn), len(backups(paths))
    r = replay(paths, "1")
    assert r.exit_code == 0, r.output
    assert r.output.strip() == "Đã dựng lại HS-01: 2 sự kiện, 0 kỹ năng đổi mức"
    assert skill_rows(conn) == before
    assert len(backups(paths)) == n + 1


def test_replay_after_delta_change_matches_hand_calc(paths, conn, bank, committed):  # noqa: F811
    old = conn.execute("SELECT theta FROM skill_state").fetchone()[0]
    conn.execute("UPDATE problem SET delta = 0.6 WHERE id = ?", (bank["p1"],))
    r = replay(paths, "hs-01")
    assert r.exit_code == 0, r.output
    _, t1 = elo.update(0.0, 0.6, 1)
    _, t2 = elo.update(t1, 0.6, 0)
    new = conn.execute("SELECT theta FROM skill_state").fetchone()[0]
    assert new == pytest.approx(t2) and new != pytest.approx(old)


def test_replay_lists_level_changes_by_kc_name(paths, conn, committed):
    conn.execute("UPDATE skill_state SET theta = 5")
    r = replay(paths, "HS-01")
    assert r.exit_code == 0, r.output
    assert r.output.splitlines() == ["Đã dựng lại HS-01: 2 sự kiện, 1 kỹ năng đổi mức",
                                     "Chuyển vế: vững → đang hình thành"]  # fmt: skip


@pytest.mark.parametrize("status", ["running", "awaiting_review", "failed"])
def test_replay_refused_while_g1_waiting(paths, conn, committed, status):
    conn.execute("UPDATE skill_state SET theta = 5")
    before, n = skill_rows(conn), len(backups(paths))
    rn = Runner(paths, {})
    rn._set("g1-hs01-20261110", create=True, graph="G1", status=status, student_id=committed)
    rn.close()
    r = replay(paths, "1")
    assert r.exit_code == 1
    assert "HS-01 còn buổi chưa lưu: g1-hs01-20261110" in r.output
    assert skill_rows(conn) == before and len(backups(paths)) == n


def test_replay_rejects_unknown_invalid_or_archived_student(paths, conn, committed):
    for arg in ("99", "abc"):
        assert replay(paths, arg).exit_code == 1, arg
    for arg in ("99999999999999999999", "١"):  # beyond 9 digits / non-ASCII digit: refused before any DB lookup
        r = replay(paths, arg)
        assert r.exit_code == 1 and r.output.strip() == f"Mã HS không hợp lệ: {arg}", arg
    repo.archive_student(conn, committed)
    assert replay(paths, "1").exit_code == 1
    assert not backups(paths)


def test_bank_import_and_review(paths, conn):
    from tutor.db import seed_dummy

    root = Path(__file__).resolve().parent.parent
    seed_dummy.seed(conn, root / "data" / "dummy" / "bank")
    src = paths.inbox / "bank" / "mix.tex"
    src.write_bytes((root / "tests" / "fixtures" / "bank" / "import-mix.tex").read_bytes())
    before = repo.row_counts(conn)
    cli_run = CliRunner()
    r = cli_run.invoke(cli.cli, ["bank", "import", str(src), "--data-dir", str(paths.root)])
    assert r.exit_code == 0, r.output
    assert "5 bài · 1 đã có kỹ năng và mức · 3 cần chọn · 1 đã có" in r.output
    tid = r.output.split("Duyệt: tutor review ")[1].strip()
    assert tid.startswith("g2-mix-")
    assert repo.row_counts(conn) == before
    r = cli_run.invoke(cli.cli, ["bank", "import", "../tutor.db", "--data-dir", str(paths.root)])
    assert r.exit_code == 1 and "Chỉ nhận file .tex trong data/inbox/bank/" in r.output
    r = cli_run.invoke(
        cli.cli, ["review", tid, "--data-dir", str(paths.root)], input="8DS-HSBN-02\nvừa\n8DS-HSBN-01\n\nn\n"
    )
    assert r.exit_code == 0 and "Lưu vào ngân hàng?" in r.output and f"tutor review {tid}" in r.output, r.output
    assert repo.row_counts(conn) == before
    r = cli_run.invoke(cli.cli, ["review", tid, "--data-dir", str(paths.root)], input="y\n")
    assert r.exit_code == 0 and "Đã thêm 4 bài (bỏ qua 1 bài đã có)" in r.output, r.output
    assert conn.execute("SELECT delta FROM problem WHERE ref = '8DS-NEW-002'").fetchone() == (0.0,)
    assert conn.execute("SELECT delta FROM problem WHERE ref = '8DS-NEW-003'").fetchone() == (0.6,)
    assert repo.row_counts(conn)["problem"] == before["problem"] + 4


SHEET_LINE = re.compile(r"^(\d)\. (\S+) · (ôn lại|vừa sức|thử thách|thêm) · \S", re.M)


def test_worksheet_and_review(paths, conn):
    world(conn)
    before = repo.row_counts(conn)
    cli_run = CliRunner()
    r = cli_run.invoke(cli.cli, ["worksheet", "HS-01", "2026-10-24", "--data-dir", str(paths.root)])
    assert r.exit_code == 0, r.output
    assert [m[1] for m in SHEET_LINE.finditer(r.output)] == ["1", "2", "3", "4", "5", "6"], r.output
    tid = r.output.split("Duyệt: tutor review ")[1].strip()
    assert tid == "g4-hs01-20261024"
    assert repo.row_counts(conn) == before
    r = cli_run.invoke(cli.cli, ["review", tid, "--data-dir", str(paths.root)], input="n\n")
    assert r.exit_code == 0 and "Tạo phiếu?" in r.output and f"tutor review {tid}" in r.output, r.output
    assert repo.row_counts(conn) == before
    r = cli_run.invoke(cli.cli, ["review", tid, "--data-dir", str(paths.root)], input="y\n")
    out = paths.out / "phieu-HS-01-2026-10-24.tex"
    assert r.exit_code == 0 and f"Đã tạo phiếu 6 bài: {out}" in r.output, r.output
    assert out.is_file()
    assert conn.execute("SELECT count(*), count(bucket) FROM recommendation").fetchone() == (6, 6)
    r = cli_run.invoke(cli.cli, ["worksheet", "9", "2026-10-24", "--data-dir", str(paths.root)])
    assert r.exit_code == 1 and "Không có HS-09" in r.output
    r = cli_run.invoke(cli.cli, ["worksheet", "1", "24/10", "--data-dir", str(paths.root)])
    assert r.exit_code == 1 and "YYYY-MM-DD" in r.output


def test_worksheet_review_replace(paths, conn):
    world(conn)
    cli_run = CliRunner()

    def run(*args, input=None):
        return cli_run.invoke(cli.cli, [*args, "--data-dir", str(paths.root)], input=input)

    run("worksheet", "1", "2026-10-24")
    assert "Đã tạo phiếu 6 bài" in run("review", "g4-hs01-20261024", input="y\n").output
    r = run("worksheet", "HS-01", "2026-10-24", "8ds-hdt-001", "8DS-HDT-002")  # typed refs: any case, added by hand
    assert [m[2] for m in SHEET_LINE.finditer(r.output)] == ["8DS-HDT-001", "8DS-HDT-002"], r.output
    assert "Thầy/cô tự thêm" in r.output
    tid = r.output.split("Duyệt: tutor review ")[1].strip()
    assert tid == "g4-hs01-20261024-2"
    r = run("review", tid, input="y\nn\n")
    assert "Ngày này đã có phiếu 6 bài. Tạo phiếu mới thay thế? Phiếu cũ vẫn giữ" in r.output, r.output
    assert r.exit_code == 0 and "Đã tạo phiếu" not in r.output
    assert conn.execute("SELECT count(*) FROM recommendation WHERE status <> 'rejected'").fetchone()[0] == 6
    r = run("review", tid, input="y\ny\n")
    assert r.exit_code == 0 and "Đã tạo phiếu 2 bài" in r.output, r.output
    assert conn.execute("SELECT status, count(*) FROM recommendation GROUP BY status ORDER BY status").fetchall() == [
        ("added", 2), ("rejected", 6)]  # fmt: skip
    r = run("worksheet", "1", "2026-10-24", "nope-nope-1")
    assert "nope-nope-1".upper() in r.output and "không có trong ngân hàng" in r.output
    r = run("review", r.output.split("Duyệt: tutor review ")[1].strip(), input="y\n")
    assert r.exit_code == 1 and "Tạo phiếu?" not in r.output


def test_report_and_review(paths, conn):
    """R18: `tutor report` stops at the draft; `tutor review` shows each sentence and its flag, then approves."""
    world(conn)
    llm.set_backend(FakeLLM({"09": writer}))
    before = repo.row_counts(conn)
    cli_run = CliRunner()

    def run(*args, input=None):
        return cli_run.invoke(cli.cli, [*args, "--data-dir", str(paths.root)], input=input)

    r = run("report", "HS-01", "week", "2026-10-12")
    assert r.exit_code == 0, r.output
    assert re.search(r"^1\. Số buổi học: 1\.$", r.output, re.M) and "⚠" not in r.output, r.output
    tid = r.output.split("Duyệt: tutor review ")[1].strip()
    assert tid == "g5-hs01w-20261012" and repo.row_counts(conn) == before
    runner = make_runner(paths)
    runner.save_decisions(tid, {"sentences": [{"text": "Em làm 45 bài.", "facts": []}]})
    runner.close()
    r = run("review", tid, input="n\n")
    assert r.exit_code == 0 and "Duyệt báo cáo?" in r.output and f"tutor review {tid}" in r.output, r.output
    assert "1. Em làm 45 bài.\n  ⚠ Số “45” không có trong dữ liệu đã duyệt.\n" in r.output
    assert repo.row_counts(conn) == before
    r = run("review", tid, input="y\n")
    out = paths.out / "baocao-HS-01-week-2026-10-12.md"
    assert r.exit_code == 0 and f"Đã duyệt báo cáo: {out}" in r.output, r.output
    assert out.read_text(encoding="utf-8") == "Em làm 45 bài.\n"
    r = run("report", "1", "week", "2026-10-12")
    assert r.exit_code == 1 and "mỗi kỳ chỉ duyệt một lần" in r.output, r.output


def test_report_not_ready(paths, conn):
    world(conn)
    r = CliRunner().invoke(cli.cli, ["report", "HS-01", "week", "2026-10-19", "--data-dir", str(paths.root)])
    assert r.exit_code == 1 and "chưa có buổi nào đã duyệt" in r.output, r.output
    assert "tutor report HS-01 week 2026-10-12" in r.output
    r = CliRunner().invoke(cli.cli, ["report", "HS-01", "year", "2026-10-01", "--data-dir", str(paths.root)])
    assert r.exit_code == 1 and "Loại kỳ" in r.output, r.output
