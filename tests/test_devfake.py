"""SDD §8.8: `--fake-llm` backend so the app runs end to end with no API key and no cost."""

from contextlib import closing
from pathlib import Path

from tutor import devfake, llm
from tutor.db import repo, seed_dummy
from tutor.graphs import runner as rmod
from tutor.graphs import session

FIX = Path(__file__).resolve().parent / "fixtures" / "submissions"
BANK = Path(__file__).resolve().parents[1] / "data" / "dummy" / "bank"


def test_g1_runs_to_review_on_fixture_with_dev_fake(paths, conn):
    seed_dummy.seed(conn, BANK)
    sid = repo.add_student(conn, name="Cam", grade=8)
    llm.configure(paths.logs / "llm.jsonl", devfake.models())
    llm.set_backend(devfake.DevFakeLLM())
    (paths.inbox / "s04.tex").write_bytes((FIX / "s04.tex").read_bytes())
    r = rmod.Runner(paths, {"G1": session.build(paths)})
    r.pending_fn("G1", session.pending(paths))
    try:
        out = session.submit(paths, r, student_id=sid, held_on="2026-10-20", rel_path="s04.tex")
        tid = out["thread_id"]
        assert r.wait(tid, 30)["node"] == "gate_confirm_match"
        st = r.state(tid)
        low = [f for f in st["ingest"]["flags"] if f["type"] == "low_match"]
        cands = st["ingest"]["attempts"][low[0]["seq"] - 1]["candidates"]
        assert low and 1 <= len(cands) <= 3 and "8DS-PTNT-003" in [c["ref"] for c in cands]
        r.save_decisions(tid, {str(f["seq"]): {"problem_ref": cands[0]["ref"]} for f in low})
        r.resume(tid)
        row = r.wait(tid, 30)
        assert (row["status"], row["node"], row["error"]) == ("awaiting_review", "gate_review", None)
        st = r.state(tid)
        assert len(st["lanes"]) == 4 and st["proposals"]
        assert all(lane["grade"]["flags"] == [] for lane in st["lanes"])
        rows = list(llm.iter_log(paths.logs / "llm.jsonl")) if hasattr(llm, "iter_log") else []
        assert all(x["model"] == "dev-fake" for x in rows)
    finally:
        r.close()
        llm.set_backend(None)
    with closing(repo.connect(paths.tutor_db)) as c:
        assert repo.row_counts(c)["session"] == 1
