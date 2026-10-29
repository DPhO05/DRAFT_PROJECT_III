"""P1-T10: G1 first part — ① session row, 01 Ingest, gate confirm_match."""

import pytest

from tests.bankfix import P2, add_bank
from tests.fakes import FakeLLM, lane_handlers
from tutor import llm
from tutor.agents import ingest
from tutor.db import repo
from tutor.graphs import runner as rmod
from tutor.graphs import session

WITH_IDS = "\\begin{problem}[8DS-PT1-001]\n$4x = 20$\n$x = 5$\n\\end{problem}\n"
NO_ID = "\\begin{problem}\nTìm m để $2x + m = 5 - x$ nhận $x = 3$.\n$m = -4$\n\\end{problem}\n"


@pytest.fixture
def env(paths, conn):
    add_bank(conn)
    sid = repo.add_student(conn, name="Nguyễn Văn An", grade=8)
    llm.configure(paths.logs / "llm.jsonl", {})
    fake = FakeLLM(lane_handlers() | {"01": ingest.MatchResult(candidates=[ingest.Candidate(ref=P2[0], score=0.5)])})
    llm.set_backend(fake)
    r = rmod.Runner(paths, {"G1": session.build(paths)})
    r.on_fail("G1", session.on_fail(paths))
    yield paths, conn, r, sid, fake
    r.close()
    llm.set_backend(None)


def put(paths, name, text):
    (paths.inbox / name).write_text(text, encoding="utf-8")
    return name


def status(conn, session_id):
    return conn.execute("SELECT status FROM session WHERE id = ?", (session_id,)).fetchone()[0]


def test_submit_writes_session_then_runs_01(env):
    paths, conn, r, sid, fake = env
    out = session.submit(paths, r, student_id=sid, held_on="2026-10-20", rel_path=put(paths, "a.tex", WITH_IDS))
    assert out["thread_id"] == f"g1-hs{sid:02d}-20261020" and out["status"] == "running"
    assert status(conn, out["session_id"]) in ("running",)
    row = r.wait(out["thread_id"])
    assert (row["status"], row["node"], row["session_id"]) == ("awaiting_review", "gate_review", out["session_id"])
    st = r.state(out["thread_id"])
    assert st["transcript"] == WITH_IDS and st["ingest"]["attempts"][0]["ref"] == "8DS-PT1-001"
    assert fake.count["01"] == 0


def test_flag_stops_at_confirm_match(env):
    paths, conn, r, sid, _ = env
    out = session.submit(paths, r, student_id=sid, held_on="2026-10-20", rel_path=put(paths, "b.tex", NO_ID))
    row = r.wait(out["thread_id"])
    assert (row["status"], row["node"]) == ("awaiting_review", "gate_confirm_match")
    assert status(conn, out["session_id"]) == "awaiting_review"


def test_duplicate_rejected_before_session_row(env):
    paths, conn, r, sid, _ = env
    name = put(paths, "a.tex", WITH_IDS)
    session.submit(paths, r, student_id=sid, held_on="2026-10-20", rel_path=name)
    put(paths, "copy.tex", WITH_IDS)
    with pytest.raises(repo.DuplicateSubmission):
        session.submit(paths, r, student_id=sid, held_on="2026-10-21", rel_path="copy.tex")
    assert repo.row_counts(conn)["session"] == 1


def test_earlier_date_than_committed_session_rejected(env):
    paths, conn, r, sid, _ = env
    conn.execute(
        "INSERT INTO session (student_id, held_on, source_path, source_kind, source_sha256, thread_id, status)"
        " VALUES (?, '2026-10-20', 'inbox/x.tex', 'tex', 'x', 'g1-old', 'committed')",
        (sid,),
    )
    with pytest.raises(repo.DateOrderLocked):
        session.submit(paths, r, student_id=sid, held_on="2026-10-13", rel_path=put(paths, "a.tex", WITH_IDS))


@pytest.mark.parametrize("bad", ["../settings.json", "/etc/hosts", "missing.tex", "a.docx"])
def test_path_must_be_a_tex_file_inside_inbox(env, bad):
    paths, _, r, sid, _ = env
    (paths.inbox / "a.docx").write_text("x")
    with pytest.raises(ValueError):
        session.submit(paths, r, student_id=sid, held_on="2026-10-20", rel_path=bad)


def test_failure_after_01_then_rerun_does_not_call_01_again(env, monkeypatch):
    paths, conn, r, sid, fake = env
    real, broken = repo.commit_session_status, [True]

    def flaky(c, session_id, st):
        if st == "awaiting_review" and broken and broken.pop():
            raise RuntimeError("gài lỗi sau 01")
        return real(c, session_id, st)

    monkeypatch.setattr(repo, "commit_session_status", flaky)
    out = session.submit(paths, r, student_id=sid, held_on="2026-10-20", rel_path=put(paths, "b.tex", NO_ID))
    row = r.wait(out["thread_id"])
    assert row["status"] == "failed" and "gài lỗi" in row["error"]
    assert status(conn, out["session_id"]) == "failed"
    r.resume(out["thread_id"])
    assert r.wait(out["thread_id"])["status"] == "awaiting_review"
    assert fake.count["01"] == 1


def test_session_marked_failed_when_graph_cannot_start(env, monkeypatch):
    paths, conn, r, sid, _ = env

    def broken(*a, **k):
        raise RuntimeError("checkpoints.db hỏng")

    monkeypatch.setattr(r, "start", broken)
    with pytest.raises(RuntimeError):
        session.submit(paths, r, student_id=sid, held_on="2026-10-20", rel_path=put(paths, "a.tex", WITH_IDS))
    assert conn.execute("SELECT status FROM session").fetchone()[0] == "failed"
