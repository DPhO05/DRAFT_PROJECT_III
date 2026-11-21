"""P9-T20: reviewed G1 sessions become draft tasks; the data dir is only read (design T16, decision 8A)."""

import json
import sqlite3
from contextlib import closing
from datetime import date

from tests.assistant_fix import CALC, SWAP, _problem_of_grade, world
from tests.db.test_profile_repo import commit, mk, start
from tests.eval import harvest, run
from tutor.db import repo, seed_dummy

ROOT = run.ROOT

GAP = "presentation.logic_gap"
FULL = "Nguyễn Văn An"
PLAIN = "Nguyen Van An"


def tex(ref: str) -> str:
    return f"% Bài làm của {FULL}, {PLAIN}\n\\begin{{problem}}[{ref}]\n$2x = 4$\n$x = 2$\n$x = 3$\n\\end{{problem}}\n"


def reviewed(paths, *plans: list[tuple[str, str, dict]]) -> None:
    """One grade-9 student and one committed session per plan of (code, status, extra row fields); conn closed."""
    repo.init_db(paths.tutor_db, paths.backup)
    with closing(repo.connect(paths.tutor_db)) as conn:
        seed_dummy.seed(conn, run.BANK)
        sid = repo.add_student(conn, name=FULL, grade=9)
        pid, kc = _problem_of_grade(conn, 9)
        ref = conn.execute("SELECT ref FROM problem WHERE id = ?", (pid,)).fetchone()[0]
        for n, plan in enumerate(plans):
            rows = [
                mk(code, kc, status) | {"step_idx": 1, "llm_json": None if status == "added" else {}} | extra
                for code, status, extra in plan
            ]
            session_id = start(conn, sid, f"2026-10-{10 + n:02d}")
            commit(conn, session_id, [(pid, rows)])
            f = paths.inbox / f"s{n}.tex"
            f.write_text(tex(ref), encoding="utf-8")
            conn.execute("UPDATE session SET source_path = ? WHERE id = ?", (f"inbox/{f.name}", session_id))


def go(paths, tmp_path):
    out = tmp_path / "out"
    return harvest.main(["--data", str(paths.root), "--out", str(out)]), out / date.today().isoformat()


def labels_of(day):
    return json.loads((day / "g1" / "labels.json").read_text(encoding="utf-8"))


def test_reviewed_session_becomes_one_draft_task(paths, tmp_path):
    reviewed(paths, [(CALC, "rejected", {}), (SWAP, "edited", {}), (GAP, "added", {})])
    code, day = go(paths, tmp_path)
    assert code == 0
    assert len(list((day / "g1").glob("*.tex"))) == 1
    ((name, lab),) = labels_of(day).items()
    assert (day / "g1" / name).is_file() and name.endswith(".tex")
    (p,) = lab["problems"]
    assert [m["code"] for m in p["mistakes"]] == [SWAP, GAP]
    assert (p["seq"], p["has_id"], p["mistakes"][0]["propagates_to"]) == (1, True, [])
    assert (lab["source"], lab["status"], lab["student_code"]) == ("production", "draft", "HS-01")
    assert lab["signals"] == {"confirmed": 0, "edited": 1, "rejected": 1, "added": 1}


def test_untouched_session_is_not_harvested(paths, tmp_path):
    repo.init_db(paths.tutor_db, paths.backup)
    with closing(repo.connect(paths.tutor_db)) as conn:
        world(conn)
    code, day = go(paths, tmp_path)
    prod = json.loads((day / "production.json").read_text(encoding="utf-8"))
    assert code == 0 and (prod["sessions"], prod["harvested"]) == (3, 0)
    assert not (day / "g1").exists()


def test_open_app_is_refused(paths, tmp_path, capsys):
    repo.init_db(paths.tutor_db, paths.backup)
    writer = repo.connect(paths.tutor_db)
    try:
        world(writer)
        assert paths.tutor_db.with_name("tutor.db-wal").stat().st_size > 0
        code, day = go(paths, tmp_path)
    finally:
        writer.close()
    assert code == 2 and not (tmp_path / "out").exists()
    assert "Đóng app trước khi gom: còn file -wal" in capsys.readouterr().out


def test_rates_on_the_temp_db(paths, tmp_path):
    reviewed(
        paths,
        [
            (CALC, "confirmed", {}),
            (SWAP, "edited", {}),
            (GAP, "rejected", {}),
            ("computational.final_answer", "added", {}),
        ],
        [(CALC, "confirmed", {}), (SWAP, "confirmed", {})],
        [(CALC, "confirmed", {})],
    )
    _, day = go(paths, tmp_path)
    prod = json.loads((day / "production.json").read_text(encoding="utf-8"))
    assert prod["sessions"] == 3 and prod["harvested"] == 1
    assert prod["proposals"] == {"confirmed": 4, "edited": 1, "rejected": 1, "added": 1}
    assert prod["rates"] == {"kept": 0.667, "edited": 0.167, "rejected": 0.167, "added": 0.167}
    assert prod["created"].endswith("Z")


def test_rates_with_nothing_are_null():
    assert harvest.rates({"confirmed": 0, "edited": 0, "rejected": 0, "added": 0}) == {
        "kept": None, "edited": None, "rejected": None, "added": None,
    }  # fmt: skip


def prod_of(day):
    return json.loads((day / "production.json").read_text(encoding="utf-8"))


def tasks_of(day, sub):
    return json.loads((day / sub / "tasks.json").read_text(encoding="utf-8"))


def student(paths) -> int:
    repo.init_db(paths.tutor_db, paths.backup)
    with closing(repo.connect(paths.tutor_db)) as conn:
        return repo.add_student(conn, name=FULL, grade=9)


def threads(paths, *rows: tuple[str, str, str | None, str | None]) -> None:
    """checkpoints.db with the runner's table and one row per (thread_id, status, error, input_json)."""
    ddl = (ROOT / "src/tutor/graphs/runner.py").read_text(encoding="utf-8").split('_SCHEMA = """')[1].split('"""')[0]
    with closing(sqlite3.connect(paths.checkpoints_db)) as c:
        c.execute(ddl)
        for tid, status, err, inp in rows:
            c.execute(
                "INSERT INTO tutor_thread (thread_id, graph, student_id, held_on, status, error, input_json,"
                " created_at, updated_at) VALUES (?, 'G1', 1, '2026-10-21', ?, ?, ?, 't', 't')",
                (tid, status, err, inp),
            )
        c.commit()


def report_row(paths, start: str, writer: list[dict], approved: list[dict]) -> None:
    with closing(repo.connect(paths.tutor_db)) as conn:
        repo.commit_report(conn, student_id=1, period_kind="week", period_start=start, facts=[], text_md=start,
                           audit={"writer": writer, "approved": approved})  # fmt: skip


def w(status: str, text: str = "Câu.", flag: str | None = None) -> dict:
    return {"i": 0, "text": text, "facts": [], "status": status, "flag": flag, "detail": flag and "chi tiết"}


def chat_log(paths, *rows: dict) -> None:
    f = paths.logs / "chat" / "2026-10-21-1.jsonl"
    f.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def llm_log(paths, *rows: dict) -> None:
    (paths.logs / "llm.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_failed_thread_becomes_a_flow_task(paths, tmp_path):
    student(paths)
    threads(
        paths,
        ("g1-hs01-20261021", "failed", f"Lỗi với {FULL}", json.dumps({"source_path": "inbox/a.tex"})),
        ("g1-hs01-20261022", "committed", None, None),
    )
    code, day = go(paths, tmp_path)
    assert code == 0 and prod_of(day)["failed_threads"] == 1
    (t,) = tasks_of(day, "failed")
    assert (t["thread_id"], t["graph"], t["student_code"], t["held_on"]) == (
        "g1-hs01-20261021",
        "G1",
        "HS-01",
        "2026-10-21",
    )
    assert (t["error"], t["source_path"]) == ("Lỗi với HS-01", "inbox/a.tex")
    assert (t["source"], t["status"]) == ("production", "draft")


def test_flagged_report_becomes_a_09_task(paths, tmp_path):
    student(paths)
    clean = [{"i": 0, "flag": None, "why": ""}]
    report_row(paths, "2026-10-05", [w("ok"), w("dropped", f"{FULL} giỏi", "number")], clean)
    report_row(paths, "2026-10-12", [w("ok"), w("ok")], clean)
    _, day = go(paths, tmp_path)
    (t,) = tasks_of(day, "09")
    assert (t["code"], t["period_kind"], t["period_start"]) == ("HS-01", "week", "2026-10-05")
    assert [r["status"] for r in t["writer"]] == ["dropped"] and t["approved"] == []
    assert prod_of(day)["report_flagged_rate"] == 0.25  # 1 dropped of 4 writer rows
    assert (t["source"], t["status"]) == ("production", "draft")


def test_approved_row_with_a_flag_is_a_09_task(paths, tmp_path):
    student(paths)
    report_row(paths, "2026-10-05", [w("ok")], [{"i": 0, "flag": "tone", "why": "Giọng"}])
    _, day = go(paths, tmp_path)
    (t,) = tasks_of(day, "09")
    assert t["writer"] == [] and t["approved"][0]["flag"] == "tone" and prod_of(day)["report_flagged_rate"] == 0


def test_chat_warning_and_reject_become_00_tasks(paths, tmp_path):
    student(paths)
    chat_log(
        paths,
        {"id": "m1", "role": "user", "text": "Điểm của HS-01?"},
        {"id": "m2", "role": "assistant", "text": "9", "events": [{"type": "warning", "kind": "unverified_number"}]},
        {"id": "m3", "role": "user", "text": f"Chấm bài {FULL}"},
        {"id": "m4", "role": "assistant", "text": "", "events": [{"type": "approval", "name": "start_grading"}]},
        {"id": "m5", "role": "user", "text": "", "decision": "reject"},
    )
    _, day = go(paths, tmp_path)
    warned, rejected = tasks_of(day, "00")
    assert (warned["id"], warned["text"], warned["forbid"]) == ("2026-10-21-1-m2", "Điểm của HS-01?", [])
    assert (rejected["id"], rejected["forbid"]) == ("2026-10-21-1-m5", ["start_grading"])
    assert warned["expect"] == rejected["expect"] == [] and rejected["text"] == "Chấm bài HS-01"
    assert prod_of(day)["unverified_rate"] == 1 / 2


def test_schema_error_row_becomes_a_component_task(paths, tmp_path):
    base = {"graph": "G1", "model": "m", "input_tokens": 1_000_000, "output_tokens": 0}
    llm_log(
        paths,
        base
        | {"agent": "03", "prompt_version": "03-aa", "thread_id": "t1", "result": "schema_error", "user": f"Đề {FULL}"},
        base | {"agent": "03", "thread_id": "t1", "result": "ok", "user": "x"},
        base | {"agent": "02", "thread_id": "t2", "result": "ok", "user": "x"},
        base | {"agent": "04", "thread_id": "t2", "result": "ok", "user": "x"},
        {"agent": "00", "thread_id": None, "graph": None, "result": "ok", "input_tokens": 1_000_000},
    )
    student(paths)
    _, day = go(paths, tmp_path)
    (t,) = tasks_of(day, "component")
    assert (t["agent"], t["prompt_version"], t["thread_id"], t["user"]) == ("03", "03-aa", "t1", "Đề HS-01")
    assert prod_of(day)["usd_per_session"] == 10.0  # 4 G1 rows of 5 USD each, 2 threads


def test_missing_sources_give_null_rates(paths, tmp_path):
    student(paths)
    code, day = go(paths, tmp_path)
    prod = prod_of(day)
    assert code == 0
    keys = ("failed_threads", "report_flagged_rate", "unverified_rate", "usd_per_session")
    assert [prod[k] for k in keys] == [None] * 4
    assert not any((day / d).exists() for d in ("failed", "09", "00", "component"))


def test_checkpoints_without_the_table_gives_null(paths, tmp_path):
    student(paths)
    sqlite3.connect(paths.checkpoints_db).close()
    _, day = go(paths, tmp_path)
    assert prod_of(day)["failed_threads"] is None


def test_cost_uses_the_saved_prices(paths, tmp_path):
    student(paths)
    row = {"agent": "03", "graph": "G1", "thread_id": "t", "model": "m", "input_tokens": 1_000_000, "result": "ok"}
    llm_log(paths, row)
    paths.settings.write_text(json.dumps({"price_by_model": {"m": {"input_per_mtok": 1}}}), encoding="utf-8")
    _, day = go(paths, tmp_path)
    assert prod_of(day)["usd_per_session"] == 1.0


def test_slugged_name_in_a_path_is_hidden(paths, tmp_path):
    student(paths)
    threads(
        paths,
        (
            "t1",
            "failed",
            "Không đọc inbox/Nguyen_Van_An.tex",
            json.dumps({"source_path": "inbox/nguyen-van-an.tex"}),
        ),
        ("t2", "failed", "x", json.dumps({"source_path": "inbox/nguyenvanan.tex"})),
        ("t3", "failed", "x", json.dumps({"source_path": "inbox/b.tex"})),
    )
    _, day = go(paths, tmp_path)
    got = [(t["source_path"], t["error"]) for t in tasks_of(day, "failed")]
    assert got == [("<đã che>", "Không đọc <đã che>"), ("<đã che>", "x"), ("inbox/b.tex", "x")]
    for f in (tmp_path / "out").rglob("*"):
        if f.is_file():
            text = f.read_text(encoding="utf-8").lower()
            assert "nguyen-van-an" not in text and "nguyen_van_an" not in text and "nguyenvanan" not in text, f.name


def test_open_checkpoints_is_refused(paths, tmp_path, capsys):
    student(paths)
    paths.checkpoints_db.with_name("checkpoints.db-wal").write_bytes(b"x")
    code, _ = go(paths, tmp_path)
    assert code == 2 and not (tmp_path / "out").exists()
    assert "Đóng app trước khi gom" in capsys.readouterr().out


def test_no_full_name_in_any_output(paths, tmp_path):
    note = {"description": f"{PLAIN} quên đổi dấu"}
    reviewed(paths, [(SWAP, "edited", note)])
    threads(paths, ("t", "failed", f"{FULL} lỗi", json.dumps({"source_path": "inbox/a.tex"})))
    report_row(paths, "2026-10-05", [w("dropped", f"{FULL} giỏi", "number")], [])
    chat_log(
        paths,
        {"id": "m1", "role": "user", "text": f"Điểm của {FULL}?"},
        {"id": "m2", "role": "assistant", "text": "9", "events": [{"type": "warning", "kind": "unverified_number"}]},
    )
    llm_log(paths, {"agent": "03", "graph": "G1", "thread_id": "t", "result": "retry", "user": f"Đề {PLAIN}"})
    assert FULL in next(paths.inbox.glob("s0.tex")).read_text(encoding="utf-8")
    _, day = go(paths, tmp_path)
    files = [f for f in (tmp_path / "out").rglob("*") if f.is_file()]
    assert len(files) == 7
    for f in files:
        text = f.read_text(encoding="utf-8")
        assert FULL not in text and PLAIN not in text, f.name
    ((_, lab),) = labels_of(day).items()
    assert lab["student_name"] is None


def test_the_data_dir_is_not_modified(paths, tmp_path):
    reviewed(paths, [(SWAP, "edited", {})])

    def snap():
        return {f: f.stat().st_mtime_ns for f in paths.root.rglob("*")}

    before = snap()
    assert go(paths, tmp_path)[0] == 0
    assert snap() == before


def test_harvested_drafts_run_as_a_local_set(paths, tmp_path, monkeypatch):
    reviewed(paths, [(SWAP, "edited", {}), (CALC, "added", {"step_idx": 2})])
    _, day = go(paths, tmp_path)
    sets = tmp_path / "sets.json"
    sets.write_text(
        json.dumps({"drafts": {"dir": str(day / "g1"), "split": "dev", "source": "production"}}), encoding="utf-8"
    )
    monkeypatch.setattr(run, "LOCAL_SETS", sets)
    got = run.load_sets()["drafts"]
    res = run.evaluate(run.oracle, work=tmp_path / "work", runs=1, fix=run.ROOT / got["dir"])
    assert res["errors"] == []
    assert res["metrics"]["per_run"][0]["recall"] == 1
