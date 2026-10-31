"""CLI `tutor`: commands equivalent to the app's buttons (SDD monolith §5.5)."""

import json
import re
import threading
import time
import urllib.request
import webbrowser
from contextlib import closing
from datetime import date
from pathlib import Path
from typing import Annotated

import typer
import uvicorn
from filelock import FileLock, Timeout

from tutor import config, devfake, llm
from tutor.api.app import create_app
from tutor.db import repo, seed_dummy
from tutor.graphs import session, threads
from tutor.graphs.runner import Runner, ThreadNotFound

cli = typer.Typer(no_args_is_help=True, add_completion=False)


@cli.callback()
def _root() -> None:
    """Trợ lý gia sư Toán."""


def _alive(url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{url}api/health", timeout=1) as r:
            return json.load(r).get("status") == "ok"
    except (OSError, ValueError):
        return False


def _open_when_up(url: str) -> None:
    for _ in range(50):
        if _alive(url):
            webbrowser.open(url)
            return
        time.sleep(0.2)


FakeLLM = Annotated[bool, typer.Option("--fake-llm", help="Dev / test: không gọi Anthropic, output giả")]


@cli.command("app")
def app_cmd(
    port: Annotated[int | None, typer.Option(help="Cổng (mặc định app.port trong settings.json)")] = None,
    data_dir: Annotated[Path | None, typer.Option(help="Thư mục dữ liệu (mặc định TUTOR_DATA hoặc ./data)")] = None,
    no_browser: Annotated[bool, typer.Option(help="Không tự mở trình duyệt")] = False,
    fake_llm: FakeLLM = False,
) -> None:
    """Mở app ở http://127.0.0.1:<cổng>."""
    paths = config.paths(data_dir)
    paths.root.mkdir(parents=True, exist_ok=True)
    try:
        port = port or config.load(paths.settings)["app"]["port"]
    except config.SettingsError:
        port = port or config.defaults()["app"]["port"]
    url = f"http://127.0.0.1:{port}/"
    # Only the runner.lock holder may run graphs or migrate the DB (ADR-M05).
    lock = FileLock(paths.runner_lock)
    try:
        lock.acquire(timeout=0)
    except Timeout:
        if _alive(url):
            typer.echo(f"App đang chạy ở {url}")
            if not no_browser:
                webbrowser.open(url)
            raise typer.Exit(0) from None
        typer.echo(f"{paths.runner_lock} đang bị giữ: lệnh CLI đang chạy hoặc app mở ở cổng khác. Chờ xong rồi mở lại.")
        raise typer.Exit(2) from None
    try:
        paths.ensure()
        try:
            repo.init_db(paths.tutor_db, paths.backup)
        except repo.MigrationError as e:
            typer.echo(f"Nâng cấp tutor.db lỗi, giữ bản cũ (sao lưu trong {paths.backup}): {e}")
            raise typer.Exit(1) from None
        app = create_app(paths, port=port, fake_llm=fake_llm)
        if not no_browser:
            threading.Thread(target=_open_when_up, args=(url,), daemon=True).start()
        typer.echo(f"Mở {url}  (Ctrl+C để tắt)")
        uvicorn.run(app, host="127.0.0.1", port=port, workers=1, log_level="warning")
    finally:
        lock.release()


DataDir = Annotated[Path | None, typer.Option(help="Thư mục dữ liệu (mặc định TUTOR_DATA hoặc ./data)")]


def _hold_lock(paths: config.DataPaths) -> FileLock:
    """Graph-running commands need runner.lock; exit 2 when the app (or another command) holds it."""
    paths.root.mkdir(parents=True, exist_ok=True)
    lock = FileLock(paths.runner_lock)
    try:
        lock.acquire(timeout=0)
    except Timeout:
        typer.echo(
            f"{paths.runner_lock} đang bị giữ: app đang mở (dùng app) hoặc lệnh khác đang chạy. Tắt rồi thử lại."
        )
        raise typer.Exit(2) from None
    paths.ensure()
    repo.init_db(paths.tutor_db, paths.backup)
    return lock


def _runner(paths: config.DataPaths, fake_llm: bool) -> Runner:
    """The same graphs and hooks the app's runner has, inside this command's process."""
    try:
        settings = config.load(paths.settings)
    except config.SettingsError:
        settings = config.defaults()
    llm.configure(paths.logs / "llm.jsonl", devfake.models() if fake_llm else settings["models"])
    if fake_llm:
        llm.set_backend(devfake.DevFakeLLM())
    runner = Runner(paths, {session.GRAPH: session.build(paths)})
    runner.on_fail(session.GRAPH, session.on_fail(paths))
    runner.pending_fn(session.GRAPH, session.pending(paths))
    runner.recover_on_startup()
    return runner


@cli.command("ingest")
def ingest_cmd(
    student: Annotated[str, typer.Argument(help="Mã HS (HS-03) hoặc id (3)")],
    file: Annotated[str, typer.Argument(help="File .tex trong data/inbox/")],
    held_on: Annotated[str, typer.Option("--date", help="Ngày học YYYY-MM-DD")] = date.today().isoformat(),
    data_dir: DataDir = None,
    fake_llm: FakeLLM = False,
) -> None:
    """Nộp bài và chạy G1 tới DỪNG (= Buổi học › Bắt đầu xử lý)."""
    paths = config.paths(data_dir)
    lock = _hold_lock(paths)
    try:
        m = re.fullmatch(r"(?:HS-)?0*(\d+)", student.strip(), re.I)
        if not m:
            typer.echo(f"Mã HS không hợp lệ: {student}")
            raise typer.Exit(1)
        f = Path(file)
        rel = f.resolve().relative_to(paths.inbox.resolve()).as_posix() if f.is_file() else file
        runner = _runner(paths, fake_llm)
        try:
            try:
                out = session.submit(paths, runner, student_id=int(m[1]), held_on=held_on, rel_path=rel)
            except (repo.DuplicateSubmission, repo.DateOrderLocked, repo.NotFound, ValueError) as e:
                typer.echo(f"Không nộp được: {e}")
                raise typer.Exit(1) from None
            typer.echo(f"{out['thread_id']}: buổi {out['session_id']}, đang chạy 01 Ingest…")
            row = runner.wait(out["thread_id"], timeout=900)
            st = runner.state(out["thread_id"])
            res = st.get("ingest") or {}
            typer.echo(f"{row['status']} ở {row['node']}: {len(res.get('attempts', []))} bài, "
                       f"{len(st.get('proposals', []))} đề xuất lỗi")  # fmt: skip
            for flag in res.get("flags", []):
                if not flag["resolved"]:
                    typer.echo(f"  cờ {flag['type']}: {flag['detail']}")
            if row["error"]:
                typer.echo(f"  lỗi: {row['error']}")
                raise typer.Exit(1)
        finally:
            runner.close()
    finally:
        lock.release()


def _ask_card(p: dict) -> dict | None:
    """One card: A / E / R, N adds a missed mistake first, Q pauses. Returns the decision, None on Q."""
    v = p.get("verifier") or {}
    typer.echo(f"\n{p['pid']} · bài {p['attempt_seq']} · bước {p['step_idx']} · {p['code']} · KC {p['kc_id']}"
               f" · tin cậy {p['confidence']}")  # fmt: skip
    typer.echo(f"  03: {p['description']}\n  bằng chứng: {p['evidence_latex']}")
    typer.echo(f"  04: {v.get('verdict')} — {v.get('reason')}" + (f" (gợi ý {v['suggested_code']})" if
               v.get("suggested_code") else ""))  # fmt: skip
    while True:
        k = typer.prompt("A đồng ý / E sửa / R bỏ / N thêm lỗi sót / Q tạm dừng").strip().upper()
        if k in ("A", "R"):
            note = typer.prompt("Ghi chú", default="", show_default=False) if k == "R" else ""
            return {"action": "accept" if k == "A" else "reject"} | ({"teacher_note": note} if note else {})
        if k == "E":
            code = typer.prompt("Mã lỗi", default=p["code"])
            kc = typer.prompt("kc_id (- = không gắn KC)", default="" if p["kc_id"] is None else str(p["kc_id"]),
                              show_default=False)  # fmt: skip
            desc = typer.prompt("Mô tả", default=p["description"])
            kc_id = None if kc in ("", "-") else int(kc) if kc.isdigit() else kc  # not a number → stays undecided
            return {"action": "edit", "code": code, "kc_id": kc_id, "description": desc}
        if k == "N":
            return {"add": {"action": "add", "attempt_seq": typer.prompt("Bài", default=p["attempt_seq"], type=int),
                            "step_idx": typer.prompt("Bước", type=int), "code": typer.prompt("Mã lỗi"),
                            "description": typer.prompt("Mô tả")}}  # fmt: skip
        if k == "Q":
            return None


@cli.command("review")
def review_cmd(
    thread_id: Annotated[str | None, typer.Argument(help="Thread cần duyệt; bỏ trống = in hàng đợi")] = None,
    data_dir: DataDir = None,
    fake_llm: FakeLLM = False,
) -> None:
    """Hộp duyệt trên terminal: in hàng đợi, hoặc duyệt lỗi G1 (A / E / R / N) rồi commit ② (= Ghi vào tutor.db)."""
    paths = config.paths(data_dir)
    lock = _hold_lock(paths)
    try:
        runner = _runner(paths, fake_llm)
        try:
            if thread_id is None:
                q = threads.queue(runner.list_threads())
                typer.echo(f"{len(q)} thread chờ duyệt" if q else "Không có gì chờ duyệt.")
                for t in q:
                    n = len(runner.state(t["thread_id"]).get("proposals") or [])
                    lock_note = f"  KHOÁ: {t['lock_reason']}" if t["locked"] else ""
                    typer.echo(f"  {t['thread_id']}  {t['graph']}  {t['subject']}  {t['node']}  {n} thẻ{lock_note}")
                return
            _review_g1(runner, thread_id)
        finally:
            runner.close()
    finally:
        lock.release()


def _review_g1(runner: Runner, thread_id: str) -> None:
    try:
        row = runner.get(thread_id)
    except ThreadNotFound:
        typer.echo(f"Không có thread {thread_id}")
        raise typer.Exit(1) from None
    if row["graph"] != session.GRAPH or row["status"] != "awaiting_review" or row["node"] not in (
        "gate_review", "gate_confirm_commit"):  # fmt: skip
        typer.echo(f"{thread_id}: {row['status']} ở {row['node']} — CLI chỉ duyệt lỗi G1; việc khác làm trong app")
        raise typer.Exit(1)
    if row["node"] == "gate_confirm_commit":
        return _confirm_commit(runner, thread_id)
    saved = json.loads(row["decisions_json"] or "{}")
    cards = dict(saved.get("cards") or {}) if isinstance(saved, dict) else {}
    secs, t0 = (saved.get("review_seconds") or 0) if isinstance(saved, dict) else 0, time.monotonic()
    props = runner.state(thread_id)["proposals"]
    todo = [p for p in props if p["pid"] not in cards]
    typer.echo(f"{thread_id}: {len(props)} thẻ, còn {len(todo)} chưa quyết")
    paused = False
    for p in todo:
        while (d := _ask_card(p)) and "add" in d:
            cards[f"n{sum(k.startswith('n') for k in cards) + 1}"] = d["add"]
        if d is None:
            paused = True
            break
        cards[p["pid"]] = d
    decisions = {"cards": cards, "review_seconds": secs + round(time.monotonic() - t0)}
    left = runner.save_decisions(thread_id, decisions)
    if paused or left:
        typer.echo(
            f"Tạm dừng: đã lưu quyết định, còn {left} mục chưa quyết / chưa hợp lệ."
            f" Duyệt tiếp: tutor review {thread_id}"
        )
        return
    try:
        threads.resume(runner, thread_id)
    except threads.ThreadLocked as e:
        typer.echo(f"Đã lưu quyết định nhưng chưa ghi được: {e}")
        raise typer.Exit(1) from None
    row = runner.wait(thread_id, timeout=300)
    if (row["status"], row["node"]) == ("awaiting_review", "gate_confirm_commit"):
        return _confirm_commit(runner, thread_id)
    _echo_result(runner, thread_id, row)


MISCON_LABELS = (("new", "Lỗi lặp mới ghi nhận"), ("again", "Lỗi cũ gặp lại"), ("resolved", "Lỗi đã hết"))
CODE_LABELS = (("repeat", "So với buổi trước, lỗi lặp lại"), ("new", "So với buổi trước, lỗi mới"),
               ("gone", "So với buổi trước, lỗi không còn"))  # fmt: skip


def _echo_preview(pv: dict) -> None:
    typer.echo("\nXem trước (chưa lưu):")
    for k in pv["kcs"]:
        typer.echo(f"  {k['kc']}: {k['before']} → {k['after']} ({k['trend']})")
    if not pv["kcs"]:
        typer.echo("  Không có kỹ năng nào được cập nhật")
    for part, labels in (("miscon", MISCON_LABELS), ("codes", CODE_LABELS)):
        for key, label in labels:
            if pv[part][key]:
                typer.echo(f"  {label}:" + "".join(f"\n    - {x}" for x in pv[part][key]))
    w = pv["writes"]
    typer.echo(f"  Sẽ ghi: +{w['attempt']} attempt · +{w['mistake']} mistake · +{w['rubric']} rubric"
               f" · +{w['skill_event']} skill_event · cập nhật {w['skill_state']} skill_state"
               f" · cập nhật {w['misconception_log']} misconception_log")  # fmt: skip


def _confirm_commit(runner: Runner, thread_id: str) -> None:
    """At gate_confirm_commit: show the preview, ask. y runs commit ②, N leaves the thread at the gate.
    A stale bounce (another session of the student saved first) lands back here with a fresh preview."""
    while True:
        _echo_preview(runner.state(thread_id)["preview"])
        if not typer.confirm("Lưu kết quả?", default=False):
            typer.echo(f"Đang chờ Lưu kết quả. Lưu sau: tutor review {thread_id}")
            return
        try:
            threads.resume(runner, thread_id)
        except threads.ThreadLocked as e:
            typer.echo(f"Chưa lưu được: {e}")
            raise typer.Exit(1) from None
        row = runner.wait(thread_id, timeout=300)
        if (row["status"], row["node"]) != ("awaiting_review", "gate_confirm_commit"):
            return _echo_result(runner, thread_id, row)
        typer.echo("Hồ sơ của HS đã đổi (buổi khác vừa lưu), đã tính lại:")


def _echo_result(runner: Runner, thread_id: str, row: dict) -> None:
    if row["status"] != "committed":
        typer.echo(f"{row['status']} ở {row['node']}: {row['error']}")
        raise typer.Exit(1)
    rec = runner.state(thread_id)["receipt"]
    typer.echo(f"committed: 1 transaction · +{rec['attempt']} attempt · +{rec['mistake']} mistake"
               f" · +{rec['rubric']} rubric · +{rec['skill_event']} skill_event · sao lưu {rec['backup']}")  # fmt: skip


@cli.command("seed-dummy")
def seed_cmd(
    dev: Annotated[bool, typer.Option("--dev", help="Bắt buộc: chỉ cho dev / test (C-32)")] = False,
    bank: Annotated[Path, typer.Option(help="Thư mục ngân hàng dummy")] = Path("data/dummy/bank"),
    data_dir: DataDir = None,
) -> None:
    """Nạp ngân hàng dummy (310 bài, nhãn của người soạn) vào tutor.db."""
    if not dev:
        typer.echo("Chỉ dùng cho dev / test: thêm --dev (C-32)")
        raise typer.Exit(1)
    paths = config.paths(data_dir)
    lock = _hold_lock(paths)
    try:
        with closing(repo.connect(paths.tutor_db)) as conn:
            out = seed_dummy.seed(conn, bank)
        typer.echo(f"Đã thêm {out['problems_added']} bài; tutor.db: {out['problem']} bài, {out['kc']} KC")
    finally:
        lock.release()


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
