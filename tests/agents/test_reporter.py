"""P7-T04: agent 09 Reporter (design T9): facts in, cited sentences out, one rewrite at most."""

import json
from contextlib import closing
from datetime import date

import pytest

from tests.assistant_fix import world
from tests.fakes import FakeLLM
from tutor import config, llm
from tutor.agents import CallContext
from tutor.agents.a08_recommender import select
from tutor.agents.a09_reporter import reporter
from tutor.agents.a09_reporter.reporter import ReportOut, Sentence
from tutor.db import repo
from tutor.services import facts

TODAY = date(2026, 10, 21)
MONTH = {"code": "HS-01", "period_kind": "month", "period_start": "2026-10-01"}
CTX = CallContext(graph="G5", thread_id="g5-hs01m-20261001", student_code="HS-01")


@pytest.fixture
def ro(conn, paths):
    w = world(conn)
    with closing(repo.connect(paths.tutor_db, readonly=True)) as c:
        yield c, w


def go(ro, *, ctx=CTX, low=0.5, ranked=None, **period):
    """09 run as G5's `write` does: facts read, `rank` closure on select.rank_problems; `ranked` collects its calls."""
    p = MONTH | period
    got = facts.report_facts(ro[0], ro[1]["an"], p["period_kind"], p["period_start"], today=TODAY, low_pass_rate=low)

    def rank():
        if ranked is not None:
            ranked.append(1)
        return select.rank_problems(ro[0], ro[1]["an"], 3, reco=config.defaults()["reco"], today=TODAY)["items"]

    return reporter.run(got, rank, ctx=ctx)


def fake(*turns):
    """FakeLLM answering 09 with `turns`, one per call; None = output off schema."""
    queue = list(turns)
    f = FakeLLM({"09": lambda user, system: queue.pop(0)})
    llm.set_backend(f)
    return f


def out(*sentences):
    """("text", "F01", …) per sentence."""
    return ReportOut(sentences=[Sentence(text=t, facts=list(ids)) for t, *ids in sentences])


# month of HS-01: F01 sessions = 2, F02 problems = 2, F04 session 07/10
DRAFT = out(("Tháng này em học 2 buổi.", "F01"), ("Em đã làm 5 bài.", "F02"), ("Em rất chăm chỉ.", "F99"))


def test_report_facts_refuses_an_empty_or_malformed_period(ro):
    """R13: an empty period raises NotReady and a malformed one a ValueError in words; G5 fails the run with either."""
    c, w = ro
    with pytest.raises(facts.NotReady):
        facts.report_facts(c, w["an"], "month", "2026-09-01", today=TODAY, low_pass_rate=0.5)
    with pytest.raises(ValueError, match="Loại kỳ"):
        facts.report_facts(c, w["an"], "year", "2026-10-01", today=TODAY, low_pass_rate=0.5)


def test_rewrite_once_then_drop(ro):
    f = fake(DRAFT, out(("Em đã làm 2 bài.", "F02"), ("Em rất chăm chỉ.", "F99")))
    r = go(ro)
    assert f.count["09"] == 2
    assert [(a["i"], a["status"], a["flag"]) for a in r["audit"]] == [
        (0, "ok", None),
        (1, "rewritten", "number"),
        (2, "dropped", "no_fact"),
    ]
    assert r["sentences"] == [
        {"text": "Tháng này em học 2 buổi.", "facts": ["F01"]},
        {"text": "Em đã làm 2 bài.", "facts": ["F02"]},
    ]
    assert "F99" not in json.dumps(r)  # Review Focus 4
    first, again = f.calls[0]["user"], f.calls[1]["user"]
    assert again.startswith(first) and again.index("Em đã làm 5 bài.") < again.index("Em rất chăm chỉ.")


@pytest.mark.parametrize(
    ("again", "status"),
    [
        ((None, None), ["ok", "dropped", "dropped"]),
        ((out(("Em đã làm 2 bài.", "F02")),), ["ok", "rewritten", "dropped"]),
        ((llm.LLMUnavailable("GPT từ chối: x"),), ["ok", "dropped", "dropped"]),
    ],
)
def test_failed_rewrite_drops(ro, again, status):
    """Rewrite off schema twice or unavailable: every failed sentence dropped; one sentence short: that one dropped."""
    fake(DRAFT, *again)
    r = go(ro)
    assert [a["status"] for a in r["audit"]] == status
    assert len(r["sentences"]) == status.count("ok") + status.count("rewritten")


def test_schema_flag_on_first_call_raises(ro):
    fake(None, None)
    with pytest.raises(llm.SchemaFlag):
        go(ro)


def test_clean_draft_one_call(ro):
    f = fake(out(("Tháng này em học 2 buổi, làm 2 bài.", "F01", "F02"), ("Buổi 07/10 em đạt 1 trong 2 ý.", "F04")))
    ranked = []
    r = go(ro, ranked=ranked)
    assert f.count["09"] == 1 and [a["status"] for a in r["audit"]] == ["ok", "ok"] and not ranked
    user = f.calls[0]["user"]
    assert all(f"{x['fact_id']} · {x['text']}" in user.split("Số liệu:\n")[1] for x in r["facts"])
    assert all(f"{i['text']} ({', '.join(i['facts'])})" in user.split("Điểm cần nói:\n")[1] for i in r["insights"])
    assert r["insights"] and not any(x["kind"] == "suggestion" for x in r["facts"])


@pytest.mark.parametrize(
    ("kind", "start", "line"),
    [
        ("day", "2026-10-14", "Kỳ: ngày 14/10/2026"),
        ("week", "2026-10-12", "Kỳ: tuần 12/10–18/10/2026"),
        ("month", "2026-10-01", "Kỳ: tháng 10/2026"),
    ],
)
def test_period_line(ro, kind, start, line):
    f = fake(out(("Em đi học đều.", "F01")))
    go(ro, period_kind=kind, period_start=start)
    assert line in f.calls[0]["user"].splitlines()


def test_low_period_no_praise(ro):
    """R23: 09 is told the result is low, and the audit's tone check rewrites praise all the same (C-41)."""
    f = fake(out(("Tháng này em học 2 buổi, rất giỏi.", "F01")), out(("Tháng này em học 2 buổi.", "F01")))
    r = go(ro, low=0.6)  # 2 of 4 points
    assert r["low"] is True and "Kết quả kỳ này thấp." in f.calls[0]["user"].splitlines()
    assert [(a["status"], a["flag"]) for a in r["audit"]] == [("rewritten", "tone")]
    assert r["sentences"] == [{"text": "Tháng này em học 2 buổi.", "facts": ["F01"]}]


def test_fact_ids_never_in_text(ro):
    """C-44: fact ids the model writes into a sentence are cut out; look-alikes such as F1, F012, AF01 stay."""
    look_alike = "Em làm 2 bài dạng F1, F012 và AF01."
    f = fake(out(
        ("Em làm 2 bài [F02].", "F02"),
        ("Em học 2 buổi, làm 2 bài (F01, F02).", "F01", "F02"),
        ("Buổi 07/10 [F04][F99] em đạt 1 trong 2 ý.", "F04"),
        ("F01 Em học 2 buổi F01.", "F01"),
        (look_alike, "F02"),
    ))  # fmt: skip
    r = go(ro)
    assert f.count["09"] == 1
    assert [s["text"] for s in r["sentences"]] == [
        "Em làm 2 bài.",
        "Em học 2 buổi, làm 2 bài.",
        "Buổi 07/10 em đạt 1 trong 2 ý.",
        "Em học 2 buổi.",
        look_alike,
    ]
    assert [a["text"] for a in r["audit"]] == [s["text"] for s in r["sentences"]]
    assert "Không viết mã số liệu vào chữ của câu." in reporter.INSTRUCTIONS
    assert "Mọi số viết bằng chữ số (2, không “hai”)." in reporter.INSTRUCTIONS


@pytest.mark.parametrize(
    ("text", "kept"),
    [
        ("[F01]", None),
        ("(F01) · .", None),
        ("· Em làm 2 bài.", "Em làm 2 bài."),
        ("F01 · Em làm 2 bài.", "Em làm 2 bài."),
    ],
)
def test_fact_line_leftovers(ro, text, kept):
    """H6: a sentence left with no words is dropped, never sent to rewrite; a copied "F01 · " or "· " prefix is cut."""
    f = fake(out((text, "F02")))
    r = go(ro)
    assert f.count["09"] == 1
    assert [s["text"] for s in r["sentences"]] == ([kept] if kept else [])
    assert r["audit"][0]["status"] == ("ok" if kept else "dropped")


def test_weak_skill_gets_suggestions(conn, ro):
    conn.execute("UPDATE skill_event SET theta_after = -1 WHERE kc_id = ?", (ro[1]["kc_swap"],))  # level from events
    calls = []
    f = fake(out(("Tháng này em học 2 buổi.", "F01")))
    r = go(ro, ranked=calls)
    assert calls == [1]
    sug = [x for x in r["facts"] if x["kind"] == "suggestion"]
    assert len(sug) == 1 and sug[0] is r["facts"][-1] and sug[0]["fact_id"] == f"F{len(r['facts']):02d}"
    assert 1 <= sug[0]["value"]["n"] <= 3 and sug[0]["value"]["kcs"]
    assert f"{sug[0]['fact_id']} · {sug[0]['text']}" in f.calls[0]["user"].split("Số liệu:\n")[1]


def test_payload_masked(conn, ro, tmp_path):
    """Review Focus 5: a skill named after a student is masked before 09 sees it and in llm.jsonl."""
    repo.update_kc(conn, ro[1]["kc_swap"], name="Ôn cho Nguyễn Văn An")
    everyone = repo.list_students(ro[0], include_archived=True)
    redact = {x["name"]: x["code"] for x in everyone if len(x["name"].split()) >= 2}  # as G1's call context
    log = tmp_path / "llm.jsonl"
    llm.configure(log, {})
    f = fake(out(("Tháng này em học 2 buổi.", "F01")))
    go(ro, ctx=CallContext(graph="G5", student_code="HS-01", redact=redact))
    assert "Văn An" not in f.calls[0]["user"] and "Ôn cho HS-01" in f.calls[0]["user"]
    rows = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
    assert [x["agent"] for x in rows] == ["09"] and rows[0]["prompt_version"].startswith("09-")
    assert "Văn An" not in log.read_text(encoding="utf-8")


# what 09 was sent by the MCP path before it was removed, on this world (the plan's "so chuỗi")
GOLDEN_PLAIN = "Kỳ: tháng 10/2026\n\nSố liệu:\nF01 · Số buổi học: 2.\nF02 · Số bài đã làm: 2.\nF03 · Cả kỳ đạt 2 trong 4 ý, điểm 5 trên 10.\nF04 · Buổi 07/10: đạt 1 trong 2 ý, điểm 5 trên 10, 1 lỗi.\nF05 · Buổi 14/10: đạt 1 trong 2 ý, điểm 5 trên 10, 1 lỗi.\nF06 · Kỹ năng “Tính chất của bất đẳng thức”: từ đang hình thành thành đang hình thành (cần ôn).\nF07 · Lỗi “Nhầm phép toán hoặc dấu (+/−, ⇒/⇔)”: 2 lần.\nF08 · Lỗi “Nhầm phép toán hoặc dấu (+/−, ⇒/⇔)” ở “Tính chất của bất đẳng thức” hiện còn, đã gặp 2 lần.\n\nĐiểm cần nói:\n- Thay đổi rõ nhất ở “Tính chất của bất đẳng thức” (cần ôn). (F06)\n- Lỗi gặp nhiều nhất: “Nhầm phép toán hoặc dấu (+/−, ⇒/⇔)”. (F07)"  # noqa: E501
GOLDEN_WEAK = "Kỳ: tháng 10/2026\n\nSố liệu:\nF01 · Số buổi học: 2.\nF02 · Số bài đã làm: 2.\nF03 · Cả kỳ đạt 2 trong 4 ý, điểm 5 trên 10.\nF04 · Buổi 07/10: đạt 1 trong 2 ý, điểm 5 trên 10, 1 lỗi.\nF05 · Buổi 14/10: đạt 1 trong 2 ý, điểm 5 trên 10, 1 lỗi.\nF06 · Kỹ năng “Tính chất của bất đẳng thức”: từ đang hình thành thành chưa vững (cần ôn).\nF07 · Lỗi “Nhầm phép toán hoặc dấu (+/−, ⇒/⇔)”: 2 lần.\nF08 · Lỗi “Nhầm phép toán hoặc dấu (+/−, ⇒/⇔)” ở “Tính chất của bất đẳng thức” hiện còn, đã gặp 2 lần.\nF09 · Bài gợi ý luyện thêm: 3 bài về “Tính chất của bất đẳng thức”, “Chứng minh bất đẳng thức đơn giản”, “Bất phương trình đưa về dạng bậc nhất”, “Nghiệm nguyên, nghiệm thoả điều kiện thêm”.\n\nĐiểm cần nói:\n- Thay đổi rõ nhất ở “Tính chất của bất đẳng thức” (cần ôn). (F06)\n- Lỗi gặp nhiều nhất: “Nhầm phép toán hoặc dấu (+/−, ⇒/⇔)”. (F07)"  # noqa: E501
GOLDEN_LOW = "Kỳ: tháng 10/2026\nKết quả kỳ này thấp.\n\nSố liệu:\nF01 · Số buổi học: 2.\nF02 · Số bài đã làm: 2.\nF03 · Cả kỳ đạt 2 trong 4 ý, điểm 5 trên 10.\nF04 · Buổi 07/10: đạt 1 trong 2 ý, điểm 5 trên 10, 1 lỗi.\nF05 · Buổi 14/10: đạt 1 trong 2 ý, điểm 5 trên 10, 1 lỗi.\nF06 · Kỹ năng “Tính chất của bất đẳng thức”: từ đang hình thành thành đang hình thành (cần ôn).\nF07 · Lỗi “Nhầm phép toán hoặc dấu (+/−, ⇒/⇔)”: 2 lần.\nF08 · Lỗi “Nhầm phép toán hoặc dấu (+/−, ⇒/⇔)” ở “Tính chất của bất đẳng thức” hiện còn, đã gặp 2 lần.\n\nĐiểm cần nói:\n- Thay đổi rõ nhất ở “Tính chất của bất đẳng thức” (cần ôn). (F06)\n- Lỗi gặp nhiều nhất: “Nhầm phép toán hoặc dấu (+/−, ⇒/⇔)”. (F07)"  # noqa: E501


def test_user_text_same_as_mcp_path(conn, ro):
    f = fake(*[out(("Tháng này em học 2 buổi.", "F01"))] * 3)
    go(ro)
    go(ro, low=0.6)
    conn.execute("UPDATE skill_event SET theta_after = -1 WHERE kc_id = ?", (ro[1]["kc_swap"],))
    go(ro)
    assert [c["user"] for c in f.calls] == [GOLDEN_PLAIN, GOLDEN_LOW, GOLDEN_WEAK]


def test_prompt_version_unchanged():
    assert llm.prompt_version("09", [reporter.INSTRUCTIONS]) == "09-841b5710"
