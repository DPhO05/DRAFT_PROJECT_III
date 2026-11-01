"""G2 bank import (P5-T03, MONO-P5-01): read .tex → DỪNG → one transaction, no LLM."""

import shutil
from pathlib import Path

import pytest

from tests.fakes import FakeLLM
from tutor import llm
from tutor.db import repo, seed_dummy
from tutor.graphs import bank
from tutor.graphs.registry import make_runner
from tutor.graphs.runner import UndecidedItems
from tutor.services import search

ROOT = Path(__file__).resolve().parents[2]
MIX = ROOT / "tests" / "fixtures" / "bank" / "import-mix.tex"
NEW = ("8DS-NEW-001", "8DS-NEW-002", "8DS-NEW-003", "8DS-NEW-004")


@pytest.fixture
def g2(paths, conn):
    """(start, conn, runner, fake_llm, kc id by code); the mix file is in data/inbox/bank/mix.tex."""
    seed_dummy.seed(conn, ROOT / "data" / "dummy" / "bank")
    fake = FakeLLM({})
    llm.set_backend(fake)
    shutil.copy(MIX, paths.inbox / "bank" / "mix.tex")
    r = make_runner(paths)
    kc = {k["code"]: k["id"] for k in repo.list_kc(conn)}

    def start(file="mix.tex"):
        out = bank.start_import(paths, r, file=file)
        return out, r.wait(out["thread_id"])

    yield start, conn, r, fake, kc
    r.close()


def counts(conn):
    return repo.row_counts(conn)


def problem(conn, ref):
    return conn.execute(
        "SELECT id, delta, difficulty_approved_at, source FROM problem WHERE ref = ?", (ref,)
    ).fetchone()


def tags(conn, pid):
    return conn.execute(
        "SELECT kc_id, step_idx, evidence_latex FROM problem_kc WHERE problem_id = ?", (pid,)
    ).fetchall()


def test_no_write_until_commit(g2):
    start, conn, r, fake, _ = g2
    before = counts(conn)
    out, row = start()
    assert out["existing"] is False and out["thread_id"].startswith("g2-mix-")
    assert (row["status"], row["node"], row["graph"], row["subject"]) == (
        "awaiting_review", "gate_confirm_import", "G2", "mix.tex")  # fmt: skip
    assert counts(conn) == before
    assert fake.calls == []
    items = {i["ref"]: i for i in r.state(out["thread_id"])["items"]}
    assert items["8DS-PT1-001"]["existing"] and items["8DS-NEW-001"]["existing"] is False
    assert sum(1 for i in items.values() if i["invalid"]) == 3


def test_resume_blocked_until_kc(g2):
    start, conn, r, _, kc = g2
    out, _ = start()
    tid = out["thread_id"]
    with pytest.raises(UndecidedItems) as e:
        r.resume(tid)
    assert e.value.n == 2
    assert r.save_decisions(tid, {"items": {"8DS-NEW-002": {"kc_ids": [kc["8DS-HSBN-02"]]}}}) == 1
    both = {"8DS-NEW-002": {"kc_ids": [kc["8DS-HSBN-02"]]}, "8DS-NEW-003": {"kc_ids": [kc["8DS-HSBN-01"]]}}
    assert r.save_decisions(tid, {"items": both}) == 0
    r.resume(tid)
    assert r.wait(tid)["status"] == "committed"


def commit_mix(start, r, kc, extra=None):
    out, _ = start()
    tid = out["thread_id"]
    items = {"8DS-NEW-002": {"kc_ids": [kc["8DS-HSBN-02"]]}, "8DS-NEW-003": {"kc_ids": [kc["8DS-HSBN-01"]]}}
    r.save_decisions(tid, {"items": items | (extra or {})})
    r.resume(tid)
    return tid, r.wait(tid)


def test_commit_receipt(g2, paths):
    start, conn, r, fake, kc = g2
    tid, row = commit_mix(start, r, kc)
    assert row["status"] == "committed"
    assert r.state(tid)["receipt"] == {"added": 4, "skipped_existing": 1}
    assert list(paths.backup.glob("tutor-*.db"))
    assert problem(conn, "8DS-NEW-002")[1:3] == (None, None)
    assert problem(conn, "8DS-NEW-003")[1] == 0.6 and problem(conn, "8DS-NEW-003")[2]
    assert problem(conn, "8DS-NEW-001")[3] == "import:mix.tex"
    for ref in NEW:
        pid = problem(conn, ref)[0]
        assert conn.execute("SELECT version FROM rubric WHERE problem_id = ?", (pid,)).fetchall() == [(1,)]
        assert tags(conn, pid)
        assert ref in [h["ref"] for h in search.search_problems(conn, ref)]
    for ref in ("8DS-NEW-005", "8DS-NEW-006"):  # invalid: never written
        assert problem(conn, ref) is None
    assert fake.calls == []


def test_decisions_override_file_labels(g2):
    start, conn, r, _, kc = g2
    k3 = kc["8DS-HSBN-03"]
    tid, _ = commit_mix(start, r, kc, {
        "8DS-NEW-003": {"kc_ids": [kc["8DS-HSBN-01"]], "level": None},
        "8DS-NEW-004": {"kc_ids": [k3], "level": "khó", "rubric_items": [{"text": "Đáp số", "points": 2}]},
    })  # fmt: skip
    assert problem(conn, "8DS-NEW-003")[1:3] == (None, None)  # level: null clears the file's level
    p4 = problem(conn, "8DS-NEW-004")
    assert p4[1] == 0.6 and tags(conn, p4[0]) == [(k3, 0, None)]  # kc_ids replace the two file tags
    assert conn.execute("SELECT items_json, max_score FROM rubric WHERE problem_id = ?", (p4[0],)).fetchone() == (
        '[{"item_id": "r1", "text": "Đáp số", "points": 2}]', 2)  # fmt: skip
    p1 = problem(conn, "8DS-NEW-001")  # no decision: file labels stay
    assert p1[1] == -0.6 and tags(conn, p1[0])[0][1] == 1


def test_reimport_zero_new(g2):
    start, conn, r, _, kc = g2
    commit_mix(start, r, kc)
    out, row = start()
    assert out["existing"] is False and row["status"] == "awaiting_review"
    valid = [i for i in r.state(out["thread_id"])["items"] if not i["invalid"]]
    assert len(valid) == 5 and all(i["existing"] for i in valid)
    r.resume(out["thread_id"])
    assert r.wait(out["thread_id"])["status"] == "committed"
    assert r.state(out["thread_id"])["receipt"] == {"added": 0, "skipped_existing": 5}


def test_race_existing_at_commit(g2):
    start, conn, r, _, kc = g2
    out, _ = start()
    tid = out["thread_id"]
    repo.add_bank_problem(conn, ref="8DS-NEW-001", statement="s", solution="x", source="t", delta=None, tags=[],
                          rubric_items=[{"item_id": "r1", "text": "t", "points": 1}])  # fmt: skip
    r.save_decisions(tid, {"items": {"8DS-NEW-002": {"kc_ids": [kc["8DS-HSBN-02"]]},
                                     "8DS-NEW-003": {"kc_ids": [kc["8DS-HSBN-01"]]}}})  # fmt: skip
    r.resume(tid)
    assert r.wait(tid)["status"] == "committed"
    assert r.state(tid)["receipt"] == {"added": 3, "skipped_existing": 2}


@pytest.mark.parametrize(
    "bad",
    [
        {"kc_ids": [9999]},
        {"kc_ids": []},
        {"kc_ids": "8DS-HSBN-02"},
        {"kc_ids": [True]},
        {"kc_ids": "ok", "level": "lạ"},
        {"kc_ids": "ok", "level": ["dễ"]},
        {"kc_ids": "ok", "rubric_items": []},
        {"kc_ids": "ok", "rubric_items": [{"text": "x", "points": 0}]},
    ],
)
def test_bad_decisions_count_as_missing(g2, bad):
    start, conn, r, _, kc = g2
    out, _ = start()
    tid = out["thread_id"]
    ok = kc["8DS-HSBN-02"]
    bad = {k: [ok] if v == "ok" else v for k, v in bad.items()}
    left = r.save_decisions(tid, {"items": {"8DS-NEW-002": bad, "8DS-NEW-003": {"kc_ids": [ok]}}})
    assert left == 1
    with pytest.raises(UndecidedItems):
        r.resume(tid)


def test_malformed_decisions_shape_counts_all_missing(g2):
    start, _, r, _, _ = g2
    out, _ = start()
    for d in (None, [], {"items": []}, {"items": {"8DS-NEW-002": 5}}):
        assert r.save_decisions(out["thread_id"], d) == 2


@pytest.mark.parametrize("name", ["../tutor.db", "/etc/hosts", "notes.txt", "empty.tex", "missing.tex"])
def test_start_rejects(g2, paths, name):
    start, _, r, _, _ = g2
    (paths.inbox / "bank" / "notes.txt").write_text("x", encoding="utf-8")
    (paths.inbox / "bank" / "empty.tex").write_text("Không có bài nào\n", encoding="utf-8")
    with pytest.raises(ValueError) as e:
        bank.start_import(paths, r, file=name)
    assert ("không tìm thấy bài" in str(e.value).lower()) == (name == "empty.tex")
    assert r.list_threads() == []


def test_same_file_returns_existing_thread(g2, paths):
    start, _, r, _, kc = g2
    first, _ = start()
    again = bank.start_import(paths, r, file="mix.tex")
    assert (again["thread_id"], again["existing"], again["status"]) == (first["thread_id"], True, "awaiting_review")
    assert len(r.list_threads(graph="G2")) == 1


def test_committed_file_starts_new_thread(g2, paths):
    start, _, r, _, kc = g2
    tid, _ = commit_mix(start, r, kc)
    out = bank.start_import(paths, r, file="mix.tex")
    assert out["existing"] is False and out["thread_id"] == f"{tid}-2"
    r.wait(out["thread_id"])
