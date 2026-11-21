"""P9-T20: reviewed G1 sessions become draft tasks; the data dir is only read (design T16, decision 8A)."""

import json
from contextlib import closing
from datetime import date

from tests.assistant_fix import CALC, SWAP, _problem_of_grade, world
from tests.db.test_profile_repo import commit, mk, start
from tests.eval import harvest, run
from tutor.db import repo, seed_dummy

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


def test_no_full_name_in_any_output(paths, tmp_path):
    note = {"description": f"{PLAIN} quên đổi dấu"}
    reviewed(paths, [(SWAP, "edited", note)])
    assert FULL in next(paths.inbox.glob("s0.tex")).read_text(encoding="utf-8")
    _, day = go(paths, tmp_path)
    files = [f for f in (tmp_path / "out").rglob("*") if f.is_file()]
    assert len(files) == 3
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
