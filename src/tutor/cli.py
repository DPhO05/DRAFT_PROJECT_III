"""CLI `tutor`: commands equivalent to the app's buttons (SDD monolith §5.5)."""

import json
import threading
import time
import urllib.request
import webbrowser
from contextlib import closing
from pathlib import Path
from typing import Annotated

import typer
import uvicorn
from filelock import FileLock, Timeout

from tutor import config
from tutor.api.app import create_app
from tutor.db import repo, seed_dummy
from tutor.graphs import threads
from tutor.graphs.registry import make_runner

cli = typer.Typer(no_args_is_help=True, add_completion=False)


@cli.callback()
def _root() -> None:
    """Trợ lý gia sư Toán."""
    config.load_env(config.ENV_FILE)


def _health(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(f"{url}api/health", timeout=1) as r:
            body = json.load(r)
    except (OSError, ValueError):
        return None
    return body if isinstance(body, dict) else None


def _alive(url: str, paths: config.DataPaths) -> bool:
    """True only for the tutor app serving this data folder."""
    h = _health(url)
    return bool(h) and h.get("app") == "tutor" and h.get("data_dir") == str(paths.root.resolve())


def _open_when_up(url: str, paths: config.DataPaths) -> None:
    for _ in range(50):
        if _alive(url, paths):
            webbrowser.open(url)
            return
        time.sleep(0.2)


# shortcut: the default catalog ships in data/dummy/bank; move it into src/tutor if the app is ever installed as a
# wheel.
DEFAULT_CATALOG = Path(__file__).resolve().parents[2] / "data" / "dummy" / "bank"

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
    config.load_env(paths.root / ".env")  # after the cwd .env (_root): a variable already set wins
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
        if _alive(url, paths):
            typer.echo(f"App đang chạy ở {url}")
            if not no_browser:
                webbrowser.open(url)
            raise typer.Exit(0) from None
        if _health(url):
            typer.echo(
                f"Cổng {port} đang có chương trình khác hoặc app mở với dữ liệu ở thư mục khác. Tắt nó rồi mở lại."
            )
        else:
            typer.echo(
                f"{paths.runner_lock} đang bị giữ: lệnh khác đang chạy hoặc app mở ở cổng khác. Chờ xong rồi mở lại."
            )
        raise typer.Exit(2) from None
    try:
        paths.ensure()
        try:
            repo.init_db(paths.tutor_db, paths.backup)
        except repo.MigrationError as e:
            typer.echo(f"Nâng cấp tutor.db lỗi, giữ bản cũ (sao lưu trong {paths.backup}): {e}")
            raise typer.Exit(1) from None
        with closing(repo.connect(paths.tutor_db)) as conn:
            repo.ensure_catalog(conn, DEFAULT_CATALOG / "kc.csv", DEFAULT_CATALOG / "kc_prereq.csv")
        app = create_app(paths, port=port, fake_llm=fake_llm)
        if not no_browser:
            threading.Thread(target=_open_when_up, args=(url, paths), daemon=True).start()
        typer.echo(f"Mở {url}  (Ctrl+C để tắt)")
        uvicorn.run(app, host="127.0.0.1", port=port, workers=1, log_level="warning")
    finally:
        lock.release()


DataDir = Annotated[Path | None, typer.Option(help="Thư mục dữ liệu (mặc định TUTOR_DATA hoặc ./data)")]


def _hold_lock(paths: config.DataPaths, init: bool = True) -> FileLock:
    """Graph-running commands need runner.lock; exit 2 when the app (or another command) holds it.

    `init=False` leaves tutor.db alone: `tutor restore` must work when it cannot be opened or migrated."""
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
    if init:
        repo.init_db(paths.tutor_db, paths.backup)
    return lock


@cli.command("restore")
def restore_cmd(
    name: Annotated[str, typer.Argument(help="Tên file trong data/backup/, ví dụ tutor-2026-10-20-093000.db")],
    drop_unfinished: Annotated[
        bool, typer.Option("--drop-unfinished", help="Bỏ các việc chưa xong (mất phần làm dở) thay vì từ chối")
    ] = False,
    data_dir: DataDir = None,
) -> None:
    """Khôi phục tutor.db từ một bản sao lưu (= ⚙ Sao lưu › Khôi phục). Bản hiện tại được sao lưu trước."""
    paths = config.paths(data_dir)
    lock = _hold_lock(paths, init=False)
    try:
        runner = make_runner(paths)
        try:
            out = threads.restore(runner, paths, name, drop_unfinished=drop_unfinished)
        except repo.NotFound:
            typer.echo(f"Không có bản sao lưu {name} trong {paths.backup}")
            raise typer.Exit(1) from None
        except (repo.BackupCorrupt, repo.BackupTooNew) as e:
            typer.echo(str(e))
            raise typer.Exit(1) from None
        except (repo.NotRestored, repo.RestoreFailed) as e:
            typer.echo(str(e))
            typer.echo(f"  ({type(e.__cause__).__name__}: {e.__cause__})")  # for whoever installs and diagnoses
            raise typer.Exit(1) from None
        except threads.Unfinished as e:
            for t in e.threads:
                typer.echo(f"  {t['thread_id']} ({t['graph']}, {t['status']})")
            typer.echo(
                "Duyệt hoặc huỷ trong app trước. Nếu app không mở được: chạy lại với --drop-unfinished"
                " (các việc này sẽ mất)."
            )
            raise typer.Exit(1) from None
        finally:
            runner.close()
        was = f"bản hiện tại: {out['safety_backup']}" if out["safety_backup"] else "máy chưa có dữ liệu cũ"
        typer.echo(f"Đã khôi phục {name} ({was})")
    finally:
        lock.release()


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
