"""G4 worksheet (P6-T07): propose → DỪNG gate_worksheet → one transaction of recommendation rows, then the .tex."""

import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from tests.assistant_fix import world
from tests.fakes import FakeLLM
from tutor import llm
from tutor.db import repo
from tutor.graphs import worksheet
from tutor.graphs.registry import make_runner
from tutor.graphs.runner import UndecidedItems
from tutor.services import latex

DAY = "2026-10-24"
NO_KC = "9DS-NOKC-001"


@pytest.fixture
def g4(paths, conn):
    """(runner, conn, fake_llm, student id); the dummy bank plus a problem with no skill."""
    w = world(conn)
    conn.execute("INSERT INTO problem (ref, statement_latex, solution_latex) VALUES (?, 's', 's')", (NO_KC,))
    fake = FakeLLM({})
    llm.set_backend(fake)
    r = make_runner(paths)
    yield r, conn, fake, w["an"]
    r.close()


def refs(conn, n, skip=0):
    return [x[0] for x in conn.execute("SELECT ref FROM problem WHERE ref <> ? ORDER BY ref LIMIT ? OFFSET ?",
                                       (NO_KC, n, skip))]  # fmt: skip


def sheet(conn, sid, day=DAY):
    """Live rows of one sheet in position order: (ref, position, status, bucket)."""
    return conn.execute(
        "SELECT p.ref, r.position, r.status, r.bucket FROM recommendation r JOIN problem p ON p.id = r.problem_id"
        " WHERE r.student_id = ? AND r.for_date = ? AND r.status <> 'rejected' ORDER BY r.position",
        (sid, day),
    ).fetchall()


def draft(paths, r, sid, items, day=DAY):
    out = worksheet.propose(paths, r, student_id=sid, for_date=day, items=[{"ref": x} for x in items])
    r.wait(out["thread_id"])
    return out["thread_id"]


def create(paths, r, sid, items, day=DAY, replace=False):
    tid = draft(paths, r, sid, items, day)
    r.save_decisions(tid, {"for_date": day, "refs": items, "replace": replace})
    r.resume(tid)
    return tid, r.wait(tid)


def test_migration_003_keeps_rows(tmp_path):
    db, mig = tmp_path / "t.db", tmp_path / "mig"
    mig.mkdir()
    for n in ("001", "002"):
        shutil.copy(repo.MIGRATIONS / f"{n}.sql", mig)
    with closing(repo.connect(db)) as c:
        repo.create_schema(c)
    assert repo.migrate(db, tmp_path / "bk", mig) == 2
    with closing(repo.connect(db)) as c, repo.write_tx(c):
        c.execute("INSERT INTO student (id, name) VALUES (1, 'A')")
        c.execute("INSERT INTO kc (id, code, name, description) VALUES (1, 'K1', 'k1', 'd')")
        c.executemany("INSERT INTO problem (id, ref, statement_latex, solution_latex) VALUES (?, ?, 's', 's')",
                      [(1, "P-1"), (2, "P-2")])  # fmt: skip
        c.executemany(  # ids out of problem order: position follows id
            "INSERT INTO recommendation (id, student_id, for_date, problem_id, kc_id, status, reviewed_at)"
            " VALUES (?, 1, ?, ?, 1, 'approved', 't')",
            [(7, DAY, 1), (4, DAY, 2)],
        )
    shutil.copy(repo.MIGRATIONS / "003.sql", mig)  # later migrations (004+) are not under test here
    assert repo.migrate(db, tmp_path / "bk", mig) == 3
    with closing(repo.connect(db)) as c:
        assert c.execute("SELECT id, position FROM recommendation ORDER BY id").fetchall() == [(4, 1), (7, 2)]
        ins = (
            "INSERT INTO recommendation (student_id, for_date, problem_id, kc_id, status, reviewed_at)"
            " VALUES (1, ?, 1, 1, ?, 't')"
        )
        c.execute(ins, (DAY, "rejected"))
        with pytest.raises(sqlite3.IntegrityError):
            c.execute(ins, (DAY, "added"))
        c.execute(ins, ("2026-10-25", "added"))


def test_no_write_until_commit(g4, paths):
    r, conn, fake, sid = g4
    before = repo.row_counts(conn)
    tid = draft(paths, r, sid, refs(conn, 3))
    row = r.get(tid)
    assert (row["status"], row["node"], row["graph"]) == ("awaiting_review", "gate_worksheet", "G4")
    assert (row["subject"], row["student_id"]) == ("HS-01 · phiếu 24/10/2026", sid)
    assert tid == "g4-hs01-20261024"
    assert repo.row_counts(conn) == before
    assert fake.calls == []


def test_propose_reports_added_and_invalid_with_refs_uppercased(g4, paths):
    r, conn, _, sid = g4
    a = refs(conn, 1)[0]
    items = [{"ref": a.lower(), "bucket": "review", "reason": "Ôn lại."}, {"ref": "zzz-xxx-999"}, {"ref": a}]
    out = worksheet.propose(paths, r, student_id=sid, for_date=DAY, items=items, note="n", warnings=["w"])
    assert out["added"] == [a]
    assert out["invalid"] == [{"ref": "ZZZ-XXX-999", "why": "không có trong ngân hàng"}]
    st = r.wait(out["thread_id"]) and r.state(out["thread_id"])
    assert st["refs"] == [a.upper(), "ZZZ-XXX-999"]
    assert st["reasons"] == {a.upper(): {"bucket": "review", "reason": "Ôn lại."}}
    assert (st["note"], st["warnings"]) == ("n", ["w"])


@pytest.mark.parametrize(("day", "item"), [("2026-13-40", {"ref": "A"}), ("20261024", {"ref": "A"}),
                                           (DAY, {"ref": "A", "bucket": "easy"}), (DAY, {"ref": 5})])  # fmt: skip
def test_propose_rejects_bad_input_before_touching_threads(g4, paths, day, item):
    r, _, _, sid = g4
    with pytest.raises(ValueError):
        worksheet.propose(paths, r, student_id=sid, for_date=day, items=[item])
    assert r.list_threads() == []


def test_duplicate_and_no_kc_block(g4, paths):
    r, conn, _, sid = g4
    a, b = refs(conn, 2)
    tid = draft(paths, r, sid, [a])
    bad = [a, b, a, NO_KC, "9ZZ-XXX-999"]
    ok, invalid = worksheet.resolve(conn, bad, {})
    assert [o["ref"] for o in ok] == [a, b]
    assert invalid == [
        {"ref": a, "why": "đã có trong phiếu"},
        {"ref": NO_KC, "why": "bài chưa gắn kỹ năng"},
        {"ref": "9ZZ-XXX-999", "why": "không có trong ngân hàng"},
    ]
    assert r.save_decisions(tid, {"for_date": DAY, "refs": bad, "replace": False}) == 1
    with pytest.raises(UndecidedItems) as e:
        r.resume(tid)
    assert e.value.n == 1


@pytest.mark.parametrize(
    "decisions",
    [
        {"refs": []},
        {"for_date": "2026-13-40"},
        {"for_date": "20261024"},
        {"refs": "ABC"},
        {"refs": [1]},
        {"replace": "no"},
        ["refs"],
    ],
)
def test_malformed_decisions_stay_undecided(g4, paths, decisions):
    r, conn, _, sid = g4
    tid = draft(paths, r, sid, refs(conn, 2))
    assert r.save_decisions(tid, decisions) == 1


def test_commit_order_and_file(g4, paths):
    r, conn, _, sid = g4
    a, b, c = refs(conn, 3)
    items = [{"ref": a, "bucket": "zpd", "reason": "Vừa sức."}, {"ref": b, "bucket": "review", "reason": "Ôn lại."}]
    out = worksheet.propose(paths, r, student_id=sid, for_date=DAY, items=items)
    tid = out["thread_id"]
    r.wait(tid)
    got = worksheet.add_refs(paths, r, tid, [c.lower(), a])  # a repeats, c is typed in lower case
    assert got == {"thread_id": tid, "added": [c], "invalid": []}
    assert worksheet.add_refs(paths, r, tid, ["9zz-xxx-999"])["invalid"] == [
        {"ref": "9ZZ-XXX-999", "why": "không có trong ngân hàng"}]  # fmt: skip
    r.save_decisions(tid, {"for_date": DAY, "refs": [c, a, b], "replace": False})
    r.resume(tid)
    row = r.wait(tid)
    assert row["status"] == "committed", row["error"]
    assert sheet(conn, sid) == [(c, 1, "added", None), (a, 2, "approved", "zpd"), (b, 3, "approved", "review")]
    main = conn.execute(
        "SELECT r.kc_id = (SELECT kc_id FROM problem_kc WHERE problem_id = r.problem_id ORDER BY step_idx, kc_id"
        " LIMIT 1), r.reason FROM recommendation r JOIN problem p ON p.id = r.problem_id WHERE p.ref IN (?, ?, ?)"
        " ORDER BY r.position", (c, a, b),
    ).fetchall()  # fmt: skip
    assert main == [(1, "Thầy/cô tự thêm"), (1, "Vừa sức."), (1, "Ôn lại.")]
    assert r.state(tid)["receipt"] == {"for_date": DAY, "n_problems": 3, "replaced": False}
    f = paths.out / "phieu-HS-01-2026-10-24.tex"
    text = f.read_text(encoding="utf-8")
    assert text.splitlines()[0] == "% Phiếu bài tập HS-01 · 24/10/2026"
    assert [p.ref for p in latex.split_problems(text)] == [c, a, b]
    assert "solution" not in text


def test_add_refs_needs_an_open_draft(g4, paths):
    r, conn, _, sid = g4
    tid, row = create(paths, r, sid, refs(conn, 2))
    assert row["status"] == "committed"
    with pytest.raises(ValueError):
        worksheet.add_refs(paths, r, tid, refs(conn, 1, skip=5))


def test_same_date_needs_replace(g4, paths):
    r, conn, _, sid = g4
    a, b, c, d = refs(conn, 4)
    create(paths, r, sid, [a, b, c])
    tid = draft(paths, r, sid, [b, d])  # b repeats sheet 1
    r.save_decisions(tid, {"for_date": DAY, "refs": [b, d], "replace": False})
    with pytest.raises(repo.WorksheetExists) as e:
        r.resume(tid)
    assert (e.value.for_date, e.value.n_problems) == (DAY, 3)
    assert [x[0] for x in sheet(conn, sid)] == [a, b, c]

    # a failure after the old rows were rejected rolls the rejection back too
    pid, kc = conn.execute(
        "SELECT problem_id, kc_id FROM problem_kc WHERE problem_id = (SELECT id FROM problem WHERE ref = ?)", (d,)
    ).fetchone()
    ok, bad_kc = {"problem_id": pid, "kc_id": kc, "bucket": None, "reason": "x"}, {"problem_id": pid, "kc_id": 99999}
    with pytest.raises(sqlite3.IntegrityError):
        repo.commit_worksheet(conn, student_id=sid, for_date=DAY, replace=True, items=[ok, ok | bad_kc])
    assert [x[0] for x in sheet(conn, sid)] == [a, b, c]

    r.save_decisions(tid, {"for_date": DAY, "refs": [b, d], "replace": True})
    r.resume(tid)
    row = r.wait(tid)
    assert row["status"] == "committed", row["error"]
    assert r.state(tid)["receipt"] == {"for_date": DAY, "n_problems": 2, "replaced": True}
    assert [x[0] for x in sheet(conn, sid)] == [b, d]
    old = conn.execute("SELECT count(*) FROM recommendation WHERE status = 'rejected'").fetchone()[0]
    assert old == 3
    again = repo.commit_worksheet(conn, student_id=sid, for_date=DAY, replace=True, items=[
        {"problem_id": p, "kc_id": k, "bucket": None, "reason": "x"}
        for p, k in conn.execute("SELECT problem_id, kc_id FROM recommendation WHERE status <> 'rejected'"
                                 " ORDER BY position")])  # fmt: skip
    assert again == {"for_date": DAY, "n_problems": 2, "replaced": True}
    assert conn.execute("SELECT count(*) FROM recommendation").fetchone()[0] == 5


def test_other_date_or_student_is_not_a_clash(g4, paths):
    r, conn, _, sid = g4
    items = refs(conn, 2)
    create(paths, r, sid, items)
    assert create(paths, r, sid, items, day="2026-10-31")[1]["status"] == "committed"
    other = repo.add_student(conn, name="Phạm Thị Dung", grade=9)
    assert create(paths, r, other, items)[1]["status"] == "committed"


def test_rerun_after_file_error(g4, paths, monkeypatch):
    r, conn, _, sid = g4
    items = refs(conn, 3)
    tid = draft(paths, r, sid, items)
    real = Path.write_text

    def boom(self, *a, **k):
        if self.suffix == ".tex":
            raise OSError("disk full")
        return real(self, *a, **k)

    monkeypatch.setattr(Path, "write_text", boom)
    r.resume(tid)
    row = r.wait(tid)
    assert (row["status"], row["node"]) == ("failed", "commit") and "disk full" in row["error"]
    assert len(sheet(conn, sid)) == 3  # rows first, file second
    monkeypatch.setattr(Path, "write_text", real)
    r.resume(tid)
    row = r.wait(tid)
    assert row["status"] == "committed", row["error"]
    assert [x[0] for x in sheet(conn, sid)] == items
    assert conn.execute("SELECT count(*) FROM recommendation").fetchone()[0] == 3
    assert (paths.out / "phieu-HS-01-2026-10-24.tex").is_file()
    assert r.state(tid)["receipt"] == {"for_date": DAY, "n_problems": 3, "replaced": False}


def test_one_draft_per_student(g4, paths):
    r, conn, _, sid = g4
    first = worksheet.propose(paths, r, student_id=sid, for_date=DAY, items=[{"ref": x} for x in refs(conn, 3)])
    assert first["existing"] is False
    r.wait(first["thread_id"])
    new = refs(conn, 2, skip=3)
    second = worksheet.propose(paths, r, student_id=sid, for_date=DAY, items=[{"ref": x} for x in new])
    assert second["existing"] is True and second["thread_id"] == first["thread_id"]
    r.wait(second["thread_id"])
    assert r.state(second["thread_id"])["refs"] == new
    assert len(r.list_threads(graph="G4")) == 1
    third = worksheet.propose(paths, r, student_id=sid, for_date="2026-10-31", items=[{"ref": new[0]}])
    assert third["existing"] is True and third["thread_id"] == "g4-hs01-20261031"
    assert [t["thread_id"] for t in r.list_threads(graph="G4")] == [third["thread_id"]]
