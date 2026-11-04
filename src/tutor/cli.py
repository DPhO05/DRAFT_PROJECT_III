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
from tutor.agents.a08_recommender import select
from tutor.api.app import create_app
from tutor.db import repo, seed_dummy
from tutor.graphs import bank as bank_graph
from tutor.graphs import report as report_graph
from tutor.graphs import session, threads, worksheet
from tutor.graphs.registry import make_runner
from tutor.graphs.runner import Runner, ThreadNotFound, UndecidedItems
from tutor.services import facts
from tutor.services.bank import LEVEL_DELTA

cli = typer.Typer(no_args_is_help=True, add_completion=False)
bank_cli = typer.Typer(no_args_is_help=True, add_completion=False, help="Ngân hàng bài")
cli.add_typer(bank_cli, name="bank")


@cli.callback()
def _root() -> None:
    """Trợ lý gia sư Toán."""
    config.load_env(config.ENV_FILE)


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


def _runner(paths: config.DataPaths, fake_llm: bool) -> Runner:
    """The same graphs and hooks the app's runner has, inside this command's process."""
    try:
        settings = config.load(paths.settings)
    except config.SettingsError:
        settings = config.defaults()
    llm.configure(paths.logs / "llm.jsonl", devfake.models() if fake_llm else settings["models"])
    if fake_llm:
        llm.set_backend(devfake.DevFakeLLM())
    runner = make_runner(paths)
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
    """Hộp duyệt trên terminal: in hàng đợi, duyệt lỗi G1 (A / E / R / N) → xem trước tiến bộ → Lưu kết quả,
    chọn kỹ năng cho bài vừa nạp (G2) → Lưu vào ngân hàng, duyệt phiếu bài tập (G4) → Tạo phiếu, hoặc báo cáo
    kỳ (G5) → Duyệt báo cáo."""
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
            graph = next((t["graph"] for t in runner.list_threads() if t["thread_id"] == thread_id), None)
            if graph == bank_graph.GRAPH:
                _review_g2(paths, runner, thread_id)
            elif graph == worksheet.GRAPH:
                _review_g4(paths, runner, thread_id)
            elif graph == report_graph.GRAPH:
                _review_g5(paths, runner, thread_id)
            else:
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
        t = next(t for t in threads.annotate(runner.list_threads()) if t["thread_id"] == thread_id)
        if t["locked"]:
            typer.echo(f"Chưa lưu được: {t['lock_reason']}")
            raise typer.Exit(1)
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


@bank_cli.command("import")
def bank_import_cmd(
    file: Annotated[str, typer.Argument(help="File .tex trong data/inbox/bank/")],
    data_dir: DataDir = None,
) -> None:
    """Đọc file bài có nhãn và chạy G2 tới DỪNG (= Ngân hàng › Nạp bài). Chưa ghi gì vào ngân hàng."""
    paths = config.paths(data_dir)
    lock = _hold_lock(paths)
    try:
        folder, f = (paths.inbox / "bank").resolve(), Path(file)
        rel = f.resolve().relative_to(folder).as_posix() if f.is_file() and f.resolve().is_relative_to(folder) else file
        runner = _runner(paths, False)
        try:
            try:
                out = bank_graph.start_import(paths, runner, file=rel)
            except ValueError as e:
                typer.echo(f"Không nạp được: {e}")
                raise typer.Exit(1) from None
            tid = out["thread_id"]
            row = runner.wait(tid, timeout=300)
            if row["status"] != "awaiting_review":
                typer.echo(f"{tid}: {row['status']} ở {row['node']}: {row['error']}")
                raise typer.Exit(1)
            items = runner.state(tid)["items"]
            valid = [i for i in items if not i["invalid"] and not i["existing"]]
            n_need = sum(bool(i["needs"]) for i in valid)
            n_read = sum(not i["invalid"] for i in items)
            typer.echo(f"{n_read} bài · {len(valid) - n_need} đã có kỹ năng và mức · {n_need} cần chọn"
                       f" · {sum(i['existing'] for i in items)} đã có")  # fmt: skip
            for i in items:
                if i["invalid"]:
                    typer.echo(f"  bỏ qua {i['ref'] or '(không có mã)'}: {i['invalid']}")
            typer.echo(f"Duyệt: tutor review {tid}")
        finally:
            runner.close()
    finally:
        lock.release()


def _ask_kc(ref: str, by_code: dict[str, int]) -> list[int]:
    """KC ids typed as codes; blank = leave this problem for later."""
    while True:
        typed = typer.prompt(f"{ref}: Mã kỹ năng (cách nhau dấu phẩy)", default="", show_default=False)
        codes = [c.strip() for c in typed.split(",") if c.strip()]
        if bad := [c for c in codes if c not in by_code]:
            typer.echo(f"  Không có mã: {', '.join(bad)}")
            continue
        return [by_code[c] for c in codes]


def _ask_level() -> str | None:
    """A level word, or None to keep what the file says."""
    while True:
        level = typer.prompt("Mức (dễ / vừa / khó, trống = chưa có mức)", default="", show_default=False).strip()
        if level in ("", *LEVEL_DELTA):
            return level or None
        typer.echo("  Chỉ nhận: dễ, vừa, khó")


def _review_g2(paths: config.DataPaths, runner: Runner, thread_id: str) -> None:
    row = runner.get(thread_id)
    if row["status"] != "awaiting_review":
        typer.echo(f"{thread_id}: {row['status']} ở {row['node']} — chưa duyệt được")
        raise typer.Exit(1)
    with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
        by_code = {k["code"]: k["id"] for k in repo.list_kc(conn)}
    saved = json.loads(row["decisions_json"] or "{}")
    answers = dict(saved.get("items") or {}) if isinstance(saved, dict) else {}
    items = runner.state(thread_id)["items"]
    ready = {r["ref"] for r in bank_graph.final_items(items, {"items": answers}, set(by_code.values()))[0]}
    for it in items:
        if it["invalid"] or it["existing"] or it["ref"] in ready:
            continue
        typer.echo(f"\n{it['ref']}: {it['statement_latex'][:120]}")
        if not (ids := _ask_kc(it["ref"], by_code)):
            continue
        answers[it["ref"]] = {"kc_ids": ids}
        if level := _ask_level():
            answers[it["ref"]]["level"] = level
    left = runner.save_decisions(thread_id, {"items": answers})
    if left:
        typer.echo(
            f"Tạm dừng: đã lưu quyết định, còn {left} bài chưa chọn kỹ năng. Duyệt tiếp: tutor review {thread_id}"
        )
        return
    if not typer.confirm("Lưu vào ngân hàng?", default=False):
        typer.echo(f"Chưa lưu. Lưu sau: tutor review {thread_id}")
        return
    try:
        runner.resume(thread_id)
    except UndecidedItems as e:
        typer.echo(f"Chưa lưu được: {e}")
        raise typer.Exit(1) from None
    row = runner.wait(thread_id, timeout=300)
    if row["status"] != "committed":
        typer.echo(f"{row['status']} ở {row['node']}: {row['error']}")
        raise typer.Exit(1)
    rec = runner.state(thread_id)["receipt"]
    typer.echo(f"Đã thêm {rec['added']} bài (bỏ qua {rec['skipped_existing']} bài đã có)")


BUCKET_WORDS = {"review": "ôn lại", "zpd": "vừa sức", "challenge": "thử thách", None: "thêm"}


@cli.command("worksheet")
def worksheet_cmd(
    student: Annotated[str, typer.Argument(help="Mã HS (HS-03) hoặc id (3)")],
    for_date: Annotated[str, typer.Argument(help="Ngày buổi học sau YYYY-MM-DD")],
    refs: Annotated[list[str] | None, typer.Argument(help="Mã bài; bỏ trống = chọn theo tiến bộ của HS")] = None,
    data_dir: DataDir = None,
) -> None:
    """Dựng phiếu bài tập nháp và DỪNG (= Trợ lý › phiếu nháp). Chưa ghi gì vào tutor.db."""
    paths = config.paths(data_dir)
    lock = _hold_lock(paths)
    try:
        m = re.fullmatch(r"(?:HS-)?0*([0-9]{1,9})", student.strip(), re.I)
        if not m:
            typer.echo(f"Mã HS không hợp lệ: {student}")
            raise typer.Exit(1)
        sid, code = int(m[1]), config.student_code(int(m[1]))
        try:
            reco = config.load(paths.settings)["reco"]
        except config.SettingsError:
            reco = config.defaults()["reco"]
        runner = _runner(paths, False)
        try:
            try:
                if refs:
                    items, warnings = [{"ref": r} for r in refs], []
                else:
                    with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
                        repo.get_student(conn, sid)
                        ranked = select.rank_problems(conn, sid, reco["n_problems"], reco=reco, today=date.today())
                    items, warnings = ranked["items"], ranked["warnings"]
                out = worksheet.propose(paths, runner, student_id=sid, for_date=for_date, items=items,
                                        warnings=warnings)  # fmt: skip
            except repo.NotFound:
                typer.echo(f"Không có {code}")
                raise typer.Exit(1) from None
            except ValueError as e:
                typer.echo(f"Không dựng được phiếu: {e}")
                raise typer.Exit(1) from None
            tid = out["thread_id"]
            _echo_sheet(runner, paths, tid)
            typer.echo(f"Duyệt: tutor review {tid}")
        finally:
            runner.close()
    finally:
        lock.release()


def _echo_sheet(runner: Runner, paths: config.DataPaths, thread_id: str, decisions: object = None) -> list:
    """Print the draft with the saved decisions applied; returns its refs (empty when it cannot be made)."""
    state = runner.state(thread_id)
    _, refs, _ = worksheet.plan(state, decisions)
    with closing(repo.connect(paths.tutor_db, readonly=True)) as conn:
        ok, bad = worksheet.resolve(conn, refs, state["reasons"])
    typer.echo(f"Phiếu {config.student_code(state['student_id'])} · {date.fromisoformat(state['for_date']):%d/%m/%Y}")
    for n, o in enumerate(ok, 1):
        typer.echo(f"{n}. {o['ref']} · {BUCKET_WORDS[o['bucket']]} · {o['reason']}")
    for b in bad:
        typer.echo(f"  {b['ref']}: {b['why']}")
    for w in state["warnings"]:
        typer.echo(f"  Lưu ý: {w}")
    return [] if bad else refs


def _review_g4(paths: config.DataPaths, runner: Runner, thread_id: str) -> None:
    row = runner.get(thread_id)
    if row["status"] != "awaiting_review":
        typer.echo(f"{thread_id}: {row['status']} ở {row['node']} — chưa duyệt được")
        raise typer.Exit(1)
    saved = json.loads(row["decisions_json"]) if row["decisions_json"] else None
    try:
        for_date, _, _ = worksheet.plan(runner.state(thread_id), saved)
        refs = _echo_sheet(runner, paths, thread_id, saved)
    except ValueError as e:
        typer.echo(f"Phiếu chưa hợp lệ, sửa trong app: {e}")
        raise typer.Exit(1) from None
    if not refs:
        typer.echo("Phiếu cần ít nhất 1 bài và không có bài lỗi: sửa trong app")
        raise typer.Exit(1)
    if not typer.confirm("Tạo phiếu?", default=False):
        typer.echo(f"Chưa tạo. Tạo sau: tutor review {thread_id}")
        return
    try:
        try:
            runner.resume(thread_id)
        except repo.WorksheetExists as e:
            if not typer.confirm(f"Ngày này đã có phiếu {e.n_problems} bài. Tạo phiếu mới thay thế? Phiếu cũ vẫn giữ",
                                 default=False):  # fmt: skip
                typer.echo(f"Chưa tạo. Tạo sau: tutor review {thread_id}")
                return
            runner.save_decisions(thread_id, {"for_date": for_date, "refs": refs, "replace": True})
            runner.resume(thread_id)
    except UndecidedItems as e:
        typer.echo(f"Chưa tạo được: {e}")
        raise typer.Exit(1) from None
    row = runner.wait(thread_id, timeout=300)
    if row["status"] != "committed":
        typer.echo(f"{row['status']} ở {row['node']}: {row['error']}")
        raise typer.Exit(1)
    n, code = runner.state(thread_id)["receipt"]["n_problems"], config.student_code(row["student_id"])
    typer.echo(f"Đã tạo phiếu {n} bài: {paths.out / f'phieu-{code}-{for_date}.tex'}")


@cli.command("report")
def report_cmd(
    student: Annotated[str, typer.Argument(help="Mã HS (HS-03) hoặc id (3)")],
    kind: Annotated[str, typer.Argument(help="Loại kỳ: day / week / month")],
    start: Annotated[str, typer.Argument(help="Ngày bắt đầu kỳ YYYY-MM-DD (tuần: thứ Hai, tháng: ngày 1)")],
    data_dir: DataDir = None,
    fake_llm: FakeLLM = False,
) -> None:
    """Làm báo cáo kỳ nháp và DỪNG (= Báo cáo › Tạo báo cáo). Chưa ghi gì vào tutor.db."""
    paths = config.paths(data_dir)
    lock = _hold_lock(paths)
    try:
        m = re.fullmatch(r"(?:HS-)?0*([0-9]{1,9})", student.strip(), re.I)
        if not m:
            typer.echo(f"Mã HS không hợp lệ: {student}")
            raise typer.Exit(1)
        sid, code = int(m[1]), config.student_code(int(m[1]))
        runner = _runner(paths, fake_llm)
        try:
            try:
                out = report_graph.start(paths, runner, student_id=sid, period_kind=kind, period_start=start,
                                         today=date.today())  # fmt: skip
            except repo.NotFound:
                typer.echo(f"Không có {code}")
                raise typer.Exit(1) from None
            except facts.NotReady as e:
                typer.echo("Chưa làm được báo cáo: kỳ này chưa có buổi nào đã duyệt")
                for p in e.detail["pending"]:
                    typer.echo(f"  Buổi {date.fromisoformat(p['held_on']):%d/%m} còn chờ duyệt: "
                               f"tutor review {p['thread_id']}")  # fmt: skip
                if prev := e.detail["previous_start"]:
                    typer.echo(f"  Kỳ trước có buổi đã duyệt: tutor report {code} {kind} {prev}")
                raise typer.Exit(1) from None
            except repo.ReportApproved as e:
                typer.echo(str(e))
                raise typer.Exit(1) from None
            except ValueError as e:
                typer.echo(f"Không làm được báo cáo: {e}")
                raise typer.Exit(1) from None
            tid = out["thread_id"]
            row = runner.wait(tid, timeout=900)
            if row["status"] != "awaiting_review":
                typer.echo(f"{tid}: {row['status']} ở {row['node']}: {row['error']}")
                raise typer.Exit(1)
            _echo_report(runner, tid)
            typer.echo(f"Duyệt: tutor review {tid}")
        finally:
            runner.close()
    finally:
        lock.release()


def _echo_report(runner: Runner, thread_id: str, decisions: object = None) -> list[dict]:
    """Print each sentence of the draft (saved decisions applied) and its flag; returns them."""
    typer.echo(runner.get(thread_id)["subject"])
    shown = report_graph.sentences(runner.state(thread_id), decisions)
    for n, s in enumerate(shown, 1):
        typer.echo(f"{n}. {s['text']}" + (f"\n  ⚠ {s['why']}" if s["why"] else ""))
    return shown


def _review_g5(paths: config.DataPaths, runner: Runner, thread_id: str) -> None:
    row = runner.get(thread_id)
    if row["status"] != "awaiting_review":
        typer.echo(f"{thread_id}: {row['status']} ở {row['node']} — chưa duyệt được")
        raise typer.Exit(1)
    try:
        shown = _echo_report(runner, thread_id, json.loads(row["decisions_json"]) if row["decisions_json"] else None)
    except ValueError as e:
        typer.echo(f"Bản nháp chưa hợp lệ, sửa trong app: {e}")
        raise typer.Exit(1) from None
    if not shown:
        typer.echo("Báo cáo cần ít nhất 1 câu: sửa trong app")
        raise typer.Exit(1)
    if not typer.confirm("Duyệt báo cáo?", default=False):
        typer.echo(f"Chưa duyệt. Duyệt sau: tutor review {thread_id}")
        return
    runner.resume(thread_id)
    row = runner.wait(thread_id, timeout=300)
    if row["status"] != "committed":
        typer.echo(f"{row['status']} ở {row['node']}: {row['error']}")
        raise typer.Exit(1)
    st = runner.state(thread_id)
    out = report_graph.report_file(paths, st["student_id"], st["period_kind"], st["period_start"])
    typer.echo(f"Đã duyệt báo cáo: {out}")


@cli.command("replay")
def replay_cmd(
    student: Annotated[str, typer.Argument(help="Mã HS (HS-03) hoặc id (3)")],
    data_dir: DataDir = None,
) -> None:
    """Dựng lại hồ sơ kỹ năng của 1 HS từ các buổi đã lưu (sau khi sửa độ khó bài / lỗi đã lưu). Sao lưu trước."""
    paths = config.paths(data_dir)
    lock = _hold_lock(paths)
    try:
        m = re.fullmatch(r"(?:HS-)?0*([0-9]{1,9})", student.strip(), re.I)
        if not m:
            typer.echo(f"Mã HS không hợp lệ: {student}")
            raise typer.Exit(1)
        sid = int(m[1])
        code = config.student_code(sid)
        with closing(repo.connect(paths.tutor_db)) as conn:
            try:
                archived = repo.get_student(conn, sid)["archived_at"]
            except repo.NotFound:
                typer.echo(f"Không có {code}")
                raise typer.Exit(1) from None
            if archived:
                typer.echo(f"{code} đã lưu trữ")
                raise typer.Exit(1)
            runner = _runner(paths, False)
            try:
                waiting = [t["thread_id"] for t in runner.list_threads(graph=session.GRAPH, student_id=sid)
                           if t["status"] in ("running", "awaiting_review", "failed")]  # fmt: skip
            finally:
                runner.close()
            if waiting:
                typer.echo(f"{code} còn buổi chưa lưu: {', '.join(waiting)}")
                raise typer.Exit(1)
            repo.backup(paths.tutor_db, paths.backup)
            out = repo.replay_student(conn, sid)
            names = {k["id"]: k["name"] for k in repo.list_kc(conn)}
        typer.echo(f"Đã dựng lại {code}: {out['events']} sự kiện, {len(out['level_changes'])} kỹ năng đổi mức")
        for c in out["level_changes"]:
            typer.echo(f"{names[c['kc_id']]}: {c['before']} → {c['after']}")
    finally:
        lock.release()


@cli.command("restore")
def restore_cmd(
    name: Annotated[str, typer.Argument(help="Tên file trong data/backup/, ví dụ tutor-2026-10-20-093000.db")],
    data_dir: DataDir = None,
) -> None:
    """Khôi phục tutor.db từ một bản sao lưu (= ⚙ Sao lưu › Khôi phục). Bản hiện tại được sao lưu trước."""
    paths = config.paths(data_dir)
    lock = _hold_lock(paths, init=False)
    try:
        runner = make_runner(paths)
        try:
            out = threads.restore(runner, paths, name)
        except repo.NotFound:
            typer.echo(f"Không có bản sao lưu {name} trong {paths.backup}")
            raise typer.Exit(1) from None
        except (repo.BackupCorrupt, repo.RestoreFailed) as e:
            typer.echo(str(e))
            raise typer.Exit(1) from None
        except threads.Unfinished as e:
            for t in e.threads:
                typer.echo(f"  {t['thread_id']} ({t['graph']}, {t['status']})")
            typer.echo("Duyệt hoặc huỷ trong app trước")
            raise typer.Exit(1) from None
        finally:
            runner.close()
        typer.echo(f"Đã khôi phục {name} (bản hiện tại: {out['safety_backup']})")
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
