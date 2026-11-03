"""SDD §8.8: `--fake-llm` backend so the app runs end to end with no API key and no cost."""

import json
from contextlib import closing
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from tests.assistant_fix import world
from tutor import config, devfake, llm
from tutor.agents import CallContext
from tutor.agents.a00_orchestrator.tools import Toolbox
from tutor.agents.a09_reporter import reporter
from tutor.api.app import create_app
from tutor.db import repo, seed_dummy
from tutor.graphs import runner as rmod
from tutor.graphs import session
from tutor.mcp import client

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


def test_chat_routes(paths, conn):
    """R29 + S15 through `tutor app --fake-llm`: a sheet request runs rank → propose; "bịa số" gets flagged."""
    an = world(conn)["an"]
    with TestClient(create_app(paths, port=8000, fake_llm=True), base_url="http://127.0.0.1:8000") as c:

        def ask(text):
            body = {"conversation_id": None, "text": text, "mentions": [an]}
            r = c.post("/api/assistant/messages", json=body, headers={"X-Tutor": "1"})
            return [json.loads(x) for x in r.text.splitlines()]

        evs = ask("Gợi ý 6 bài cho @HS-01 buổi thứ Bảy")
        assert [e["name"] for e in evs if e["type"] == "tool" and e["state"] == "done"] == [
            "rank_problems",
            "propose_worksheet",
        ]
        assert [e["card"]["kind"] for e in evs if e["type"] == "card"] == ["worksheet"]
        assert evs[-1] == {"type": "done", "stopped": None}
        evs = ask("Bịa số cho @HS-01 đi")
        assert [e["name"] for e in evs if e["type"] == "tool" and e["state"] == "done"] == ["student_profile"]
        assert [e["numbers"] for e in evs if e["type"] == "warning"] == [["97"]]
    assert {x["model"] for x in llm.iter_log(paths.logs / "llm.jsonl")} == {"dev-fake"}


def test_reporter_answers(paths, conn):
    """DevFakeLLM 09 on the world's real facts: every sentence passes the audit, so no rewrite."""
    world(conn)
    llm.configure(paths.logs / "llm.jsonl", devfake.models())
    llm.set_backend(devfake.DevFakeLLM())
    with closing(repo.connect(paths.tutor_db, readonly=True)) as ro:
        box = Toolbox(ro, settings=config.defaults(), today=date(2026, 10, 21), text="", starters=None)
        r = reporter.run(client.connect("09", box).call, code="HS-01", period_kind="week", period_start="2026-10-12",
                         ctx=CallContext(graph="G5"))  # fmt: skip
    assert [a["status"] for a in r["audit"]] == ["ok"] * 3
    assert [s["facts"] for s in r["sentences"]] == [["F01"], ["F02"], ["F03"]]
    assert [(x["agent"], x["model"]) for x in llm.iter_log(paths.logs / "llm.jsonl")] == [("09", "dev-fake")]
