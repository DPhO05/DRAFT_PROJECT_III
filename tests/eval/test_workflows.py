"""The code-only workflows on the scorecard: every listed test exists (design section 6)."""

# ruff: noqa: F811  (fixtures imported from other test modules are used as arguments)

import json
import subprocess
import sys

from langchain_core.messages import ToolMessage

from tests.agents.test_chat import make, text, use  # noqa: F401
from tests.eval import scorecard
from tests.graphs.test_report import approve, draft, g5, rows  # noqa: F401
from tutor.agents.a00_orchestrator.tools import Starters
from tutor.graphs import report


def test_every_listed_test_is_collected():
    ids = sorted({t for w in json.loads(scorecard.WORKFLOWS.read_text(encoding="utf-8")) for t in w["tests"]})
    out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", *ids],
                         capture_output=True, text=True, cwd=scorecard.ROOT)  # fmt: skip
    assert out.returncode == 0, out.stdout[-2000:]


def test_saved_report_md_holds_no_student_name(g5, paths):
    """The approved .md, as stored and as saved, holds no full student name."""
    r, conn, _, sid = g5
    approve(r, draft(paths, r, sid)["thread_id"])
    [(_, _, _, md, _)] = rows(conn)
    saved = report.report_file(paths, sid, "week", "2026-10-12").read_text(encoding="utf-8")
    assert md == saved and report.lines(md)
    assert not [n for (n,) in conn.execute("SELECT name FROM student") if n in saved]


def test_propose_worksheet_runs_at_most_twice_in_a_message(make):
    got = []

    def propose(sid, for_date, items, note, warnings):
        got.append(for_date)
        return {"thread_id": "g4-x", "added": [i["ref"] for i in items], "invalid": [], "existing": False}

    starters = Starters(start_grading=None, start_bank_import=None, propose_worksheet=propose, add_to_worksheet=None)
    r = make([[use("rank_problems", code="HS-01", n=2)], [text("đây")]])
    ref = r.say("gợi ý", starters=starters)["rank"]["items"][0]["ref"]
    ask = use("propose_worksheet", code="HS-01", for_date="2026-10-24", refs=[ref])
    r.script += [[ask], [ask], [ask], [text("xong")]]
    state = r.say("soạn phiếu", starters=starters)
    assert [m.status for m in state["messages"] if isinstance(m, ToolMessage)][-3:] == ["success", "success", "error"]
    assert len(got) == 2
