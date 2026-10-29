import pytest

from tests.bankfix import add_bank
from tests.fakes import FakeLLM, lane_handlers
from tutor import llm
from tutor.db import repo
from tutor.graphs import runner as rmod
from tutor.graphs import session


@pytest.fixture
def env(paths, conn):
    """go(text) submits a .tex for one student and waits for G1 to stop; yields (go, conn, runner)."""
    add_bank(conn)
    sid = repo.add_student(conn, name="Nguyễn Văn An", grade=8)
    llm.configure(paths.logs / "llm.jsonl", {})
    r = rmod.Runner(paths, {"G1": session.build(paths)})
    r.on_fail("G1", session.on_fail(paths))
    r.pending_fn("G1", session.pending(paths))
    r._paths_for_test = paths

    def go(text, name="a.tex", handlers=None, day="2026-10-20"):
        fake = FakeLLM(handlers or lane_handlers())
        llm.set_backend(fake)
        (paths.inbox / name).write_text(text, encoding="utf-8")
        out = session.submit(paths, r, student_id=sid, held_on=day, rel_path=name)
        return out, r.wait(out["thread_id"]), fake

    yield go, conn, r
    r.close()
    llm.set_backend(None)
