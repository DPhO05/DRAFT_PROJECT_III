"""P6-T08: make_starters runs the routes' functions; the only row a chat tool writes is the G1 session."""

import json
import re
from concurrent.futures import Future
from contextlib import closing

import pytest

from tests.assistant_fix import world
from tests.fakes import FakeLLM, lane_handlers
from tutor import config, llm
from tutor.agents.tools import Toolbox
from tutor.api.assistant import make_starters
from tutor.db import repo
from tutor.graphs import worksheet
from tutor.graphs.registry import make_runner

REF = "9DS-BPT-001"
TEX = f"\\begin{{problem}}[{REF}]\n$4x = 20$\n$x = 5$\n\\end{{problem}}\n"
BANK = "% Hàm số ôn tập\n\\begin{problem}[8DS-ONE-001]\n% kc_du_kien: 8DS-HSBN-02\nTính $f(0)$.\n\\end{problem}\n"
XY = re.compile(r"\b[a-z]+\.[a-z_]+\b")


@pytest.fixture
def env(paths, conn):
    w = world(conn)
    llm.configure(paths.logs / "llm.jsonl", {})
    llm.set_backend(FakeLLM(lane_handlers()))
    runner = make_runner(paths)
    (paths.inbox / "a.tex").write_text(TEX, encoding="utf-8")
    (paths.inbox / "b.tex").write_text(TEX.replace("x = 5", "x = 6"), encoding="utf-8")
    (paths.inbox / "bank" / "new.tex").write_text(BANK, encoding="utf-8")
    with closing(repo.connect(paths.tutor_db, readonly=True)) as ro:

        def box():
            return Toolbox(
                ro, settings=config.defaults(), today=w["today"], text="x", starters=make_starters(paths, runner)
            )

        yield box(), runner, conn
    runner.close()


def grade(tb, file="a.tex", day="2026-10-21"):
    return tb.run("start_grading", {"code": "HS-01", "file": file, "held_on": day})


def test_duplicate_file_is_words(env):
    tb, runner, _ = env
    first = grade(tb)
    assert not first.is_error
    runner.wait(first.card["thread_id"])
    again = grade(tb, day="2026-10-22")
    err = json.loads(again.content)["error"]
    assert again.is_error and again.card is None
    assert err == "Bài này đã nộp cho HS-01 rồi (buổi 21/10)." and not XY.search(err)


def test_date_lock_is_words(env):
    tb, _, _ = env
    out = grade(tb, day="2026-10-01")
    assert out.is_error and json.loads(out.content)["error"] == "Ngày học sớm hơn buổi đã lưu 14/10, không chấm được."


def test_only_session_rows_change(env):
    tb, runner, conn = env
    before = repo.row_counts(conn)
    ranked = tb.run("rank_problems", {"code": "HS-01"})
    refs = [i["ref"] for i in json.loads(ranked.content)["items"]]
    outs = [
        grade(tb),
        tb.run("start_bank_import", {"file": "new.tex"}),
        tb.run("propose_worksheet", {"code": "HS-01", "for_date": "2026-10-24", "refs": refs}),
        ranked,
        tb.run("list_students", {}),
        tb.run("student_profile", {"code": "HS-01"}),
        tb.run("student_mistakes", {"code": "HS-01"}),
        tb.run("compare_students", {"metric": "open_repeats"}),
        tb.run("find_problems", {"refs": [REF]}),
        tb.run("search_problems", {"text": "phương trình"}),
    ]
    assert not [o.content for o in outs if o.is_error]
    threads = runner.list_threads()
    assert sorted(t["graph"] for t in threads) == ["G1", "G2", "G4"]
    for t in threads:
        runner.wait(t["thread_id"])
    after = repo.row_counts(conn)
    assert {t: after[t] - before[t] for t in after if after[t] != before[t]} == {"session": 1}


def test_propose_keeps_rank_reasons(env):
    tb, runner, conn = env
    ranked = json.loads(tb.run("rank_problems", {"code": "HS-01"}).content)["items"]
    five = ranked[:5]
    own = next(p["ref"] for p in repo.bank_problems(conn) if p["ref"] not in {i["ref"] for i in ranked})
    out = tb.run(
        "propose_worksheet", {"code": "HS-01", "for_date": "2026-10-24", "refs": [i["ref"] for i in five] + [own]}
    )
    assert not out.is_error and out.card["invalid"] == []
    state = runner.state(out.card["thread_id"])
    assert state["reasons"] == {i["ref"]: {"bucket": i["bucket"], "reason": i["reason"]} for i in five}
    ok, _ = worksheet.resolve(conn, state["refs"], state["reasons"])
    assert [o["reason"] for o in ok] == [i["reason"] for i in five] + [worksheet.SELF_ADDED]


def test_unknown_student_is_words(env, paths):
    with pytest.raises(ValueError, match="Không có học sinh HS-99"):
        make_starters(paths, env[1]).propose_worksheet(99, "2026-10-24", [], None, [])


def test_busy_old_draft_is_words(env):
    tb, runner, _ = env
    args = {"code": "HS-01", "for_date": "2026-10-24", "refs": [REF]}
    old = tb.run("propose_worksheet", args).card["thread_id"]
    running = runner._futures[old] = Future()  # the old draft is being saved right now
    try:
        out = tb.run("propose_worksheet", args)
    finally:
        running.set_result(None)
    assert out.is_error and json.loads(out.content) == {"error": "Phiếu nháp đang được lưu, thử lại sau ít phút"}
    assert out.card is None and [t["thread_id"] for t in runner.list_threads(graph="G4")] == [old]
