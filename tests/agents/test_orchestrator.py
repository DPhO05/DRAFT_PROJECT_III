"""P6-T05: agent 00 — fixed replies, problem codes, attachments, the model loop, sources and the number check."""

import json
from contextlib import closing

import pytest

from tests.assistant_fix import world
from tests.fakes import FakeLLM
from tutor import config, llm
from tutor.agents import orchestrator
from tutor.agents.orchestrator import Turn, fixed_parts, history_messages, version
from tutor.agents.tools import Starters, tool_defs
from tutor.db import repo


@pytest.fixture
def ro(conn, paths):
    w = world(conn)
    everyone = repo.list_students(conn, include_archived=True)
    codes = repo.error_codes(conn, active_only=True)
    w |= {
        "redact": {s["name"]: s["code"] for s in everyone},
        "students": {s["id"]: s for s in everyone},
        "fixed": fixed_parts(repo.list_kc(conn), codes),
        "tools": tool_defs([c["code"] for c in codes]),
    }
    with closing(repo.connect(paths.tutor_db, readonly=True)) as c:
        yield c, w


def say(ro, turn, script=None, *, history=(), starters=None, settings=None, redact=None):
    c, w = ro
    llm.set_backend(fake := FakeLLM({} if script is None else {"00": script}))
    events = list(
        orchestrator.reply(
            turn if isinstance(turn, Turn) else Turn(turn),
            history=list(history),
            conn=c,
            starters=starters,
            settings=settings or config.defaults(),
            today=w["today"],
            redact=w["redact"] if redact is None else redact,
            students=w["students"],
            conversation_id="2026-10-21-1",
            fixed=w["fixed"],
            tools=w["tools"],
        )
    )
    return events, fake


def tool(name, **inp):
    return {"type": "tool_use", "name": name, "input": inp}


def text(t):
    return {"type": "text", "text": t}


def of(events, kind):
    return [e for e in events if e["type"] == kind]


def said(events):
    return "".join(e["delta"] for e in of(events, "text"))


def test_refs_skip_llm(ro):
    events, fake = say(ro, "8DS-PT1-004, 8ds-pt1-005")
    assert fake.calls == []
    [card] = [e["card"] for e in of(events, "card")]
    assert card["kind"] == "problem" and [p["ref"] for p in card["problems"]] == ["8DS-PT1-004", "8DS-PT1-005"]
    assert card["missing"] == []
    assert events[-2:] == [{"type": "source", "items": ["ngân hàng bài (theo mã)"]}, {"type": "done", "stopped": None}]
    events, fake = say(ro, " 8DS-XXX-999 ")
    assert fake.calls == [] and of(events, "card")[0]["card"]["missing"] == ["8DS-XXX-999"]


def test_refs_go_to_open_worksheet(ro):
    added = []

    def add(thread_id, refs):
        added.append((thread_id, refs))
        return {"thread_id": thread_id, "added": refs, "invalid": []}

    starters = Starters(start_grading=None, start_bank_import=None, propose_worksheet=None, add_to_worksheet=add)
    events, fake = say(ro, Turn("8ds-pt1-004", worksheet_thread_id="g4-hs01-20261024"), starters=starters)
    assert fake.calls == [] and added == [("g4-hs01-20261024", ["8ds-pt1-004"])]
    assert [e["card"] for e in of(events, "card")] == [
        {"kind": "worksheet", "thread_id": "g4-hs01-20261024", "added": ["8ds-pt1-004"], "invalid": []}
    ]


@pytest.mark.parametrize("words", ["ok", "Lưu đi!", "DUYỆT", "ok, lưu đi", "  Đồng ý; tạo phiếu. "])
def test_confirm_words_never_write(ro, conn, words):
    before = repo.row_counts(conn)
    events, fake = say(ro, words)
    assert fake.calls == []
    assert said(events).startswith("Mình chưa lưu gì cả")
    assert of(events, "source") == [{"type": "source", "no_student_data": True}]
    assert events[-1] == {"type": "done", "stopped": None}
    assert repo.row_counts(conn) == before


def test_confirm_inside_a_question_goes_to_model(ro):
    events, fake = say(ro, "ok, vậy HS-01 yếu gì?", [[text("Mình xem nhé.")]])
    assert len(fake.calls) == 1 and said(events) == "Mình xem nhé."


def test_free_text_calls_scripted_tool(ro, tmp_path):
    llm.configure(tmp_path / "llm.jsonl", {})
    events, fake = say(ro, "Tháng này @HS-01 yếu gì?", [[tool("student_profile", code="HS-01")],
                                                        [text("HS-01 có 2 buổi.")]])  # fmt: skip
    assert [e["type"] for e in events] == ["tool", "tool"] + ["text"] * len(of(events, "text")) + ["source", "done"]
    start, done = events[:2]
    assert start == {"type": "tool", "name": "student_profile", "label": "hồ sơ học sinh", "state": "start"}
    assert done["state"] == "done" and done["summary"].startswith("student_profile HS-01")
    assert said(events) == "HS-01 có 2 buổi."
    assert events[-2:] == [{"type": "source", "items": ["hồ sơ của HS-01"]}, {"type": "done", "stopped": None}]
    assert fake.calls[0]["messages"] == [
        {"role": "user", "content": "Hôm nay: 2026-10-21 (thứ Tư).\n\nTháng này @HS-01 yếu gì?"}
    ]
    _, w = ro
    rows = [json.loads(x) for x in (tmp_path / "llm.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {r["prompt_version"] for r in rows} == {version(w["fixed"], w["tools"])}
    assert {r["conversation_id"] for r in rows} == {"2026-10-21-1"}


def test_invented_number_warns(ro):
    answer = "HS-01 sai 5 lần nhầm dấu. Hôm nay 21/10, lần gần nhất là 14/10.\n1. Bài 9DS-BPT-001: $x^2 = 4$ còn sai."
    events, _ = say(ro, "@HS-01 sai dấu mấy lần?", [[tool("student_mistakes", code="HS-01")], [text(answer)]])
    assert of(events, "warning") == [
        {"type": "warning", "kind": "unverified_number", "sentence": "HS-01 sai 5 lần nhầm dấu.", "numbers": ["5"]}
    ]
    kinds = [e["type"] for e in events]
    assert kinds[-3:] == ["warning", "source", "done"] and kinds.index("warning") > max(
        i for i, k in enumerate(kinds) if k == "text"
    )


def test_no_tool_no_student_data(ro):
    events, _ = say(ro, "Mẹo dạy phương trình chứa ẩn ở mẫu?", [[text("Cho em làm 3 bước: tìm điều kiện trước.")]])
    assert of(events, "warning") == []
    assert of(events, "source") == [{"type": "source", "no_student_data": True}]


def test_source_added_when_model_omits(ro):
    script = [
        [tool("student_mistakes", code="HS-01"), tool("student_profile", code="HS-01")],
        [tool("student_mistakes", code="HS-01")],
        [text("HS-01 còn 1 lỗi lặp.")],
    ]
    events, _ = say(ro, "@HS-01 thế nào?", script)
    assert "Nguồn" not in said(events)
    assert of(events, "source") == [{"type": "source", "items": ["lỗi đã duyệt của HS-01", "hồ sơ của HS-01"]}]


def test_cards_and_tool_errors_pass_through(ro):
    script = [[tool("list_students"), tool("student_profile", code="HS-99")], [text("Thầy chọn học sinh nhé.")]]
    events, _ = say(ro, "Học sinh nào yếu nhất?", script)
    assert [e["card"]["kind"] for e in of(events, "card")] == ["pick_student"]
    assert [(e["name"], e["state"]) for e in of(events, "tool")] == [
        ("list_students", "start"), ("list_students", "done"), ("student_profile", "start"),
        ("student_profile", "error")]  # fmt: skip
    assert "summary" not in of(events, "tool")[3]
    assert of(events, "source") == [{"type": "source", "items": ["danh sách học sinh"]}]


def test_stops_after_max_tool_turns(ro):
    settings = config.defaults()
    settings["assistant"]["max_tool_turns"] = 1
    events, fake = say(ro, "@HS-01?", lambda messages: [tool("student_profile", code="HS-01")], settings=settings)
    assert len(fake.calls) == 2 and events[-1] == {"type": "done", "stopped": "max_tool_turns"}


def test_names_masked_short_names_kept(ro):
    _, w = ro
    redact = w["redact"] | {"Minh": "HS-09"}  # a legacy one-word name must not mask "chứng minh" (S24)
    _, fake = say(ro, "NGUYEN VAN AN chứng minh sai", [[text("Ừ.")]], redact=redact)
    assert fake.calls[0]["messages"][-1]["content"].endswith("HS-01 chứng minh sai")
    assert orchestrator.mask("Nguyễn Văn An chứng minh", redact) == "HS-01 chứng minh"


def test_history_last_20(ro):
    rows = []
    for k in range(15):
        rows.append({"id": f"m{2 * k + 1}", "role": "user", "text": f"hỏi {k}", "mentions": [], "attachment": None})
        rows.append({"id": f"m{2 * k + 2}", "role": "assistant", "text": f"đáp {k}" if k != 13 else "",
                     "events": [{"type": "source", "items": ["hồ sơ của HS-01"]}],
                     "tools": [{"name": "student_profile", "summary": f"student_profile HS-01: {k} vững"}],
                     })  # fmt: skip
    msgs = history_messages(rows)
    assert len(msgs) <= 20 and msgs[0]["role"] == "user"
    assert {"role": "assistant", "content": "đáp 14\n\n(đã tra: student_profile HS-01: 14 vững)"} == msgs[-1]
    assert "đáp 13" not in json.dumps(msgs, ensure_ascii=False) and all(m["content"] for m in msgs)
    assert not [m for m in msgs if "{" in m["content"] or "items" in m["content"]]
    _, fake = say(ro, "còn gì nữa?", [[text("Hết rồi.")]], history=msgs)
    assert fake.calls[0]["messages"][:-1] == msgs


def test_attachment_needs_student_and_date(ro):
    _, w = ro
    events, fake = say(ro, Turn("", attachment="bai-lam-moi.tex"))
    assert of(events, "card") == [
        {"type": "card", "card": {"kind": "ask_grading", "attachment": "bai-lam-moi.tex", "guess": None}}
    ]
    assert of(events, "source") == [{"type": "source", "no_student_data": True}]
    events, _ = say(ro, Turn("Chấm bài này", attachment="hs01-2026-10-21.tex", mentions=[w["an"]]))
    assert of(events, "card")[0]["card"]["guess"] == {"student_id": w["an"], "held_on": "2026-10-21"}
    for archived_or_unknown in ("hs03-2026-10-21.tex", "hs09-2026-10-21.tex"):
        events, _ = say(ro, Turn("", attachment=archived_or_unknown))
        assert of(events, "card")[0]["card"]["guess"] is None
    events, _ = say(ro, Turn("", attachment="hs01-2026-10-21.tex", mentions=[w["an"]], held_on="2026-10-21"))
    assert not [e for e in of(events, "card") if e["card"]["kind"] == "ask_grading"]
    assert fake.calls == [] and llm._backend.calls == []
    assert config.guess_submission("HS01-2026-02-30.tex") is None


def test_prompt_version_tracks_catalog(conn):
    world(conn)
    kcs, codes = repo.list_kc(conn), repo.error_codes(conn, active_only=True)
    fixed = fixed_parts(kcs, codes)
    assert fixed[0] == orchestrator.SYSTEM and "notational.operator_swap" in fixed[1]
    before = version(fixed, tool_defs([c["code"] for c in codes]))
    more = codes + [{"code": "other.new_kind", "category": "other", "description": "Lỗi mới", "example": None}]
    assert version(fixed_parts(kcs, more), tool_defs([c["code"] for c in more])) != before
    assert version(fixed, tool_defs([c["code"] for c in codes])) == before
