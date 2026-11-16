"""P4-T02: agent 00 as a LangChain agent: thread state, context trimming, code paths, start limits, rank memory."""

import json
import re
import sqlite3
import time
from contextlib import closing

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from tests.assistant_fix import world
from tests.fakes import FakeLLM
from tutor import config, llm
from tutor.agents.a00_orchestrator import chat
from tutor.agents.a00_orchestrator.orchestrator import SAVED_NOTHING, Turn
from tutor.agents.a00_orchestrator.tools import Starters, Toolbox, lc_tools, tool_defs
from tutor.db import repo

BIG = 20000


@tool(response_format="content_and_artifact")
def look(n: int) -> tuple[str, dict]:
    """Look."""
    return f"R{n}:" + "z" * BIG, {}


def use(name, **inp):
    return {"type": "tool_use", "name": name, "input": inp}


def text(t):
    return {"type": "text", "text": t}


def auto(messages):
    """One `look` per message, then an answer."""
    last = messages[-1]["content"][-1]
    return [text("xong")] if last["type"] == "tool_result" else [use("look", n=len(messages))]


class Rig:
    def __init__(self, conn, w, tmp_path, script):
        self.conn, self.w, self.cfg = conn, w, {}
        llm.configure(tmp_path / "llm.jsonl", {})
        self.saver = SqliteSaver(sqlite3.connect(tmp_path / "chat.db", check_same_thread=False))
        self.script = script
        self.fake = FakeLLM({"00": script if callable(script) else lambda m: self.script.pop(0)})
        llm.set_backend(self.fake)
        self.codes = [c["code"] for c in repo.error_codes(conn, active_only=True)]

    def _setup(self, words, thread, starters, tools, max_tool_turns, turn=None):
        box = Toolbox(self.conn, settings=config.defaults(), today=self.w["today"], text=words, starters=starters)
        ctx = chat.ChatContext(turn or Turn(words), box, self.w["students"], self.w["redact"])
        agent = chat.build(
            llm.model("00"),
            [*lc_tools(box, self.codes), *tools],
            self.saver,
            max_tool_turns=max_tool_turns,
            system=["sys"],
        )
        cfg = {"configurable": {"thread_id": thread}, "recursion_limit": 200}
        cc = llm.CallContext(graph=None, conversation_id="c", redact=self.w["redact"])
        return agent, ctx, cfg, cc

    def events(self, words, *, thread="t", starters=None, tools=(), max_tool_turns=8, turn=None):
        """Every approval the model asks for is approved, so a start_* behaves as it did before the tutor was asked."""
        agent, ctx, cfg, cc = self._setup(words, thread, starters, tools, max_tool_turns, turn)
        with chat.scope(cc, ["sys"], tool_defs(self.codes)):
            out = list(chat.events(agent, ctx, cfg))
            while out[-1]["type"] == "approval":
                out += chat.events(agent, ctx, cfg, resume=[{"type": "approve"}] * len(chat.waiting(agent, cfg)))
        return out

    def say(self, words, *, thread="t", starters=None, tools=(), max_tool_turns=8):
        agent, ctx, cfg, cc = self._setup(words, thread, starters, tools, max_tool_turns)
        with chat.scope(cc, ["sys"], tool_defs(self.codes)):
            agent.invoke({"messages": [HumanMessage(words)]}, cfg, context=ctx)
            while asks := chat.waiting(agent, cfg):
                agent.invoke(Command(resume={"decisions": [{"type": "approve"}] * len(asks)}), cfg, context=ctx)
        return agent.get_state(cfg).values


@pytest.fixture
def make(conn, paths, tmp_path):
    w = world(conn)
    everyone = repo.list_students(conn, include_archived=True)
    w |= {"redact": {s["name"]: s["code"] for s in everyone}, "students": {s["id"]: s for s in everyone}}
    with closing(repo.connect(paths.tutor_db, readonly=True)) as c:
        yield lambda script: Rig(c, w, tmp_path, script)
    llm.set_backend(None)


def dangling(msgs):
    calls = {c["id"] for m in msgs if isinstance(m, AIMessage) for c in m.tool_calls}
    answered = {m.tool_call_id for m in msgs if isinstance(m, ToolMessage)}
    return calls ^ answered


def sent_results(call):
    return [b["content"] for m in call["messages"] for b in m["content"] if b["type"] == "tool_result"]


def test_second_message_sees_first_tool_result(make):
    r = make([[use("look", n=1)], [text("một")], [text("hai")]])
    r.say("tin 1", tools=[look])
    r.say("tin 2", tools=[look])
    assert any(c.startswith("R1:") for c in sent_results(r.fake.calls[2]))


def test_state_stays_within_40_messages(make):
    r = make(auto)
    for i in range(30):
        state = r.say(f"tin {i}", tools=[look])
    msgs = state["messages"]
    assert len(msgs) <= 40 and isinstance(msgs[0], HumanMessage) and not dangling(msgs)


def test_long_turn_keeps_its_human_message(make):
    n = 0

    def six(messages):
        nonlocal n
        last = messages[-1]["content"][-1]
        if "big" not in json.dumps(messages, ensure_ascii=False):
            return auto(messages)
        n += last["type"] == "tool_result"
        return [use("look", n=n)] if n < 6 else [text("xong")]

    r = make(six)
    for i in range(9):
        r.say(f"tin {i}", tools=[look])
    before = len(r.fake.calls)
    state = r.say("big", tools=[look])
    msgs = state["messages"]
    assert isinstance(msgs[0], HumanMessage) and any(m.content == "big" for m in msgs if isinstance(m, HumanMessage))
    assert not dangling(msgs)
    assert all("big" in json.dumps(c["messages"]) and len(c["messages"]) <= 40 for c in r.fake.calls[before:])


def test_model_sees_only_three_recent_tool_results(make):
    r = make(auto)
    for i in range(30):
        r.say(f"tin {i}", tools=[look])
    seen = sent_results(r.fake.calls[-1])
    assert len([c for c in seen if len(c) > BIG]) == 3 and len(seen) > 3


def test_confirm_word_is_answered_without_model(make):
    r = make([])
    state = r.say("ok")
    assert r.fake.calls == []
    assert [m.type for m in state["messages"]] == ["human", "ai"] and state["messages"][-1].content == SAVED_NOTHING


def test_second_start_in_a_message_is_refused(make):
    starts = []

    def grading(sid, file, held_on):
        starts.append(file)
        return {"status": "queued", "thread_id": "g1-x"}

    starters = Starters(start_grading=grading, start_bank_import=None, propose_worksheet=None, add_to_worksheet=None)
    go = use("start_grading", code="HS-01", file="a.tex", held_on="2026-10-21")
    r = make([[go], [go], [text("xong")], [go], [text("xong")]])
    state = r.say("chấm", starters=starters)
    first, second = [m for m in state["messages"] if isinstance(m, ToolMessage)]
    assert first.status == "success" and second.status == "error" and not re.search(r"\d", second.content)
    assert "một lần" in second.content and len(starts) == 1
    state = r.say("chấm lại", starters=starters)
    assert [m.status for m in state["messages"] if isinstance(m, ToolMessage)][-1] == "success" and len(starts) == 2


def test_rank_survives_to_the_next_message(make):
    got = []

    def propose(sid, for_date, items, note, warnings):
        got.extend(items)
        return {"thread_id": "g4-x", "added": [i["ref"] for i in items], "invalid": [], "existing": False}

    starters = Starters(start_grading=None, start_bank_import=None, propose_worksheet=propose, add_to_worksheet=None)
    r = make([[use("rank_problems", code="HS-01", n=2)], [text("đây")]])
    state = r.say("gợi ý", starters=starters)
    ref = state["rank"]["items"][0]["ref"]
    r.script += [[use("propose_worksheet", code="HS-01", for_date="2026-10-24", refs=[ref])], [text("xong")]]
    r.say("soạn phiếu", starters=starters)
    assert got and got[0]["ref"] == ref and got[0]["bucket"] and got[0]["reason"]


def test_tool_rounds_stop_at_the_limit_and_flag_resets(make):
    r = make(lambda m: [use("look", n=1)])
    state = r.say("mãi", tools=[look], max_tool_turns=2)
    msgs = state["messages"]
    assert state["stopped"] is True and len([m for m in msgs if isinstance(m, ToolMessage)]) == 2
    assert len(r.fake.calls) == 2 and not dangling(msgs)
    r.script, r.fake.handlers["00"] = [[text("xong")]], lambda m: [text("xong")]
    assert r.say("lại", tools=[look])["stopped"] is False


def stored(state):
    """What a checkpoint keeps of the model side; the HumanMessage is masked by the caller."""
    return json.dumps(
        [
            [m.content, getattr(m, "artifact", None), m.additional_kwargs, getattr(m, "tool_calls", None)]
            for m in state["messages"]
            if not isinstance(m, HumanMessage)
        ],
        ensure_ascii=False,
        default=str,
    )


def test_names_never_enter_state(make):
    name = "Nguyễn Văn An"

    @tool(response_format="content_and_artifact")
    def who(n: int) -> tuple[str, dict]:
        """Who."""
        return f"học sinh {name}", {"tutor/card": {"text": name}}

    r = make([[use("who", n=1)], [text("xong")]])
    state = r.say("ai?", tools=[who])
    assert name not in stored(state)
    assert "HS-01" in [m for m in state["messages"] if isinstance(m, ToolMessage)][0].content


def test_pick_student_card_text_is_masked(make):
    r = make([[use("list_students")], [text("xong")]])
    state = r.say("xem Nguyễn Văn An giúp")
    assert "pick_student" in stored(state) and "Nguyễn Văn An" not in stored(state)


def test_by_code_reply_is_masked(make):
    def add(thread_id, refs):
        raise ValueError("Phiếu của Nguyễn Văn An đã đóng")

    starters = Starters(start_grading=None, start_bank_import=None, propose_worksheet=None, add_to_worksheet=add)
    r = make([])
    box = Toolbox(r.conn, settings=config.defaults(), today=r.w["today"], text="8ds-pt1-004", starters=starters)
    ctx = chat.ChatContext(Turn("8ds-pt1-004", worksheet_thread_id="g4-x"), box, r.w["students"], r.w["redact"])
    agent = chat.build(llm.model("00"), [], r.saver, max_tool_turns=2)
    cfg = {"configurable": {"thread_id": "bc"}}
    agent.invoke({"messages": [HumanMessage("8ds-pt1-004")]}, cfg, context=ctx)
    state = agent.get_state(cfg).values
    assert "đã đóng" in stored(state) and "Nguyễn Văn An" not in stored(state)


def test_parallel_starts_run_once(make):
    starts = []

    def grading(sid, file, held_on):
        starts.append(file)
        return {"status": "queued", "thread_id": "g1-x"}

    starters = Starters(start_grading=grading, start_bank_import=None, propose_worksheet=None, add_to_worksheet=None)
    go = use("start_grading", code="HS-01", file="a.tex", held_on="2026-10-21")
    r = make([[go, go], [text("xong")]])
    state = r.say("chấm", starters=starters)
    statuses = sorted(m.status for m in state["messages"] if isinstance(m, ToolMessage))
    assert statuses == ["error", "success"] and len(starts) == 1


def test_stopped_message_starts_nothing(make):
    """K11: the browser left, so a start_* the model still asks for is refused and never runs."""
    starts = []

    def grading(sid, file, held_on):
        starts.append(file)
        return {"status": "queued", "thread_id": "g1-x"}

    starters = Starters(start_grading=grading, start_bank_import=None, propose_worksheet=None, add_to_worksheet=None)
    r = make([[use("start_grading", code="HS-01", file="a.tex", held_on="2026-10-21")], [text("xong")]])
    agent, ctx, cfg, cc = r._setup("chấm", "t", starters, [], 8)
    ctx.stop.set()
    with chat.scope(cc, ["sys"], tool_defs(r.codes)):
        agent.invoke({"messages": [HumanMessage("chấm")]}, cfg, context=ctx)
        agent.invoke(Command(resume={"decisions": [{"type": "approve"}]}), cfg, context=ctx)
    assert starts == []
    [m] = [m for m in agent.get_state(cfg).values["messages"] if isinstance(m, ToolMessage)]
    assert m.status == "error" and m.content == chat._error_message("start_grading", "x", chat.STOPPED).content


def test_stop_flag_reaches_the_model_guard(make):
    r = make([[text("xong")]])
    agent, ctx, cfg, cc = r._setup("chào", "t", None, [], 8)
    ctx.stop.set()
    with chat.scope(cc, ["sys"], tool_defs(r.codes), stop=ctx.stop), pytest.raises(llm.LLMUnavailable):
        list(chat.events(agent, ctx, cfg))


def test_tools_of_one_message_run_one_at_a_time(make):
    inside, worst = [], []

    @tool(response_format="content_and_artifact")
    def slow(n: int) -> tuple[str, dict]:
        """Slow."""
        inside.append(n)
        worst.append(len(inside))
        time.sleep(0.05)
        inside.remove(n)
        return str(n), {}

    r = make([[use("slow", n=1), use("slow", n=2), use("slow", n=3)], [text("xong")]])
    r.say("tin", tools=[slow])
    assert max(worst) == 1


@tool(response_format="content_and_artifact")
def peek(n: int) -> tuple[str, dict]:
    """Peek."""
    return f"so {n}", {"tutor/summary": "tóm tắt", "tutor/source": f"nguồn {n}", "tutor/card": {"kind": "k", "n": n}}


@tool(response_format="content_and_artifact")
def boom() -> tuple[str, dict]:
    """Boom."""
    return "hỏng", {"tutor/error": True}


@tool(response_format="content_and_artifact")
def start_grading() -> tuple[str, dict]:
    """Start."""
    return "ok", {"tutor/summary": "chấm"}


def kinds(evs):
    return [(e["type"], e.get("state") or e.get("kind")) for e in evs]


def test_events_order_of_a_two_tool_turn(make):
    r = make([[text("Xem "), use("peek", n=1)], [use("peek", n=2)], [text("kết quả 1 và 2")]])
    evs = r.events("hỏi", tools=[peek])
    assert [e["type"] for e in evs[:2]] == ["text", "tool"]
    assert kinds([e for e in evs if e["type"] != "text"]) == [
        ("tool", "start"), ("tool", "done"), ("card", None),
        ("tool", "start"), ("tool", "done"), ("card", None),
        ("source", None), ("done", None),
    ]  # fmt: skip
    assert "".join(e["delta"] for e in evs if e["type"] == "text") == "Xem \n\nkết quả 1 và 2"
    assert evs[-2] == {"type": "source", "items": ["nguồn 1", "nguồn 2"]}
    assert evs[-1] == {"type": "done", "stopped": None}
    done = [e for e in evs if e["type"] == "tool" and e["state"] == "done"]
    assert done[0]["summary"] == "tóm tắt"


def test_events_two_model_calls_split_by_blank_line(make):
    r = make([[text("một"), use("peek", n=1)], [text("hai")]])
    texts = [e["delta"] for e in r.events("hỏi", tools=[peek]) if e["type"] == "text"]
    assert "".join(texts) == "một\n\nhai"


def test_events_tool_error(make):
    r = make([[use("boom")], [text("lỗi rồi")]])
    evs = r.events("hỏi", tools=[boom])
    tool = [e for e in evs if e["type"] == "tool" and e["state"] != "start"]
    assert [e["state"] for e in tool] == ["error"] and not [e for e in evs if e["type"] == "card"]
    assert evs[-2] == {"type": "source", "no_student_data": True}


def test_events_refused_start_has_no_summary_or_source(make):
    r = make([[use("start_grading"), use("start_grading")], [text("xong")]])
    evs = r.events("hỏi", tools=[start_grading])
    states = sorted(e["state"] for e in evs if e["type"] == "tool" and e["state"] != "start")
    assert states == ["done", "error"] and evs[-1]["type"] == "done"


def test_events_by_code_turn_gives_text_and_cards(make):
    r = make([])
    evs = r.events("ok")
    assert evs == [
        {"type": "text", "delta": SAVED_NOTHING},
        {"type": "source", "no_student_data": True},
        {"type": "done", "stopped": None},
    ]
    evs = r.events("8ds-pt1-004", thread="t2")
    [card] = [e["card"] for e in evs if e["type"] == "card"]
    assert card["kind"] == "problem" and not [e for e in evs if e["type"] == "text"]
    assert kinds(evs)[:2] == [("tool", "start"), ("tool", "done")] and r.fake.calls == []


def test_events_warn_on_unseen_number_only(make):
    r = make([[use("peek", n=7)], [text("Có 7 bài và 99 lỗi.")]])
    evs = r.events("hỏi", tools=[peek])
    [w] = [e for e in evs if e["type"] == "warning"]
    assert w["numbers"] == ["99"] and w["kind"] == "unverified_number"


def test_events_stopped_at_max_tool_turns(make):
    r = make(lambda m: [use("peek", n=1)])
    evs = r.events("hỏi", tools=[peek], max_tool_turns=1)
    assert evs[-1] == {"type": "done", "stopped": "max_tool_turns"}


def test_resaved_adds_recheck_line_for_next_call(make):
    r = make([[text("ừ")]])
    agent, ctx, cfg, cc = r._setup("hỏi", "t", None, (), 8)
    ctx.resaved = True
    with chat.scope(cc, ["sys"], tool_defs(r.codes)):
        list(chat.events(agent, ctx, cfg))
    assert "tra lại" in json.dumps(r.fake.calls[0]["system"], ensure_ascii=False)


@tool(response_format="content_and_artifact")
def fat(n: int) -> tuple[str, dict]:
    """Fat."""
    return "z" * BIG + (" 4242" if n in HOLDS else ""), {}


HOLDS: set[int] = set()


@pytest.mark.parametrize(("holds", "warned"), [(1, True), (7, False)])
def test_events_number_only_in_trimmed_result_is_unverified(make, holds, warned):
    HOLDS.clear()
    HOLDS.add(holds)
    r = make([[use("fat", n=i)] for i in range(1, 8)] + [[text("Có 4242 bài.")]])
    evs = r.events("hỏi", tools=[fat])
    assert bool([e for e in evs if e["type"] == "warning"]) is warned


def test_rejected_start_does_not_count_toward_the_limit(make):
    """Task 4.7: HITL sits before limit_starts, so a call the tutor rejected leaves the one start of the message."""
    starts = []

    def grading(sid, file, held_on):
        starts.append(file)
        return {"status": "queued", "thread_id": "g1-x"}

    starters = Starters(start_grading=grading, start_bank_import=None, propose_worksheet=None, add_to_worksheet=None)
    go = use("start_grading", code="HS-01", file="a.tex", held_on="2026-10-21")
    r = make([[go], [go], [text("xong")]])
    agent, ctx, cfg, cc = r._setup("chấm", "t", starters, [], 8)
    with chat.scope(cc, ["sys"], tool_defs(r.codes)):
        agent.invoke({"messages": [HumanMessage("chấm")]}, cfg, context=ctx)
        agent.invoke(Command(resume={"decisions": [{"type": "reject", "message": chat.REJECTED}]}), cfg, context=ctx)
        assert starts == [] and len(chat.waiting(agent, cfg)) == 1
        agent.invoke(Command(resume={"decisions": [{"type": "approve"}]}), cfg, context=ctx)
    assert starts == ["a.tex"]
    assert [m.status for m in agent.get_state(cfg).values["messages"] if isinstance(m, ToolMessage)] == [
        "error",
        "success",
    ]


def test_start_limit_holds_across_a_decision(make):
    """Task 4.7 (P4-13): the limit counts results in the thread, so a pause and a new context do not reset it."""
    ran = []

    def bank(file):
        ran.append(file)
        return {"status": "queued", "thread_id": "g2-x", "existing": 0}

    starters = Starters(
        start_grading=lambda *a: {"status": "queued", "thread_id": "g1-x"},
        start_bank_import=bank,
        propose_worksheet=None,
        add_to_worksheet=None,
    )
    imp, go = (
        use("start_bank_import", file="b.tex"),
        use("start_grading", code="HS-01", file="a.tex", held_on="2026-10-21"),
    )
    r = make([[imp], [go], [imp], [text("xong")], [imp], [text("lại")]])
    agent, ctx, cfg, cc = r._setup("nạp rồi chấm", "t", starters, [], 8)
    with chat.scope(cc, ["sys"], tool_defs(r.codes)):
        agent.invoke({"messages": [HumanMessage("nạp rồi chấm")]}, cfg, context=ctx)
        assert len(chat.waiting(agent, cfg)) == 1
        _, ctx2, _, _ = r._setup("x", "t", starters, [], 8)  # a restart: nothing of the first context survives
        agent.invoke(Command(resume={"decisions": [{"type": "approve"}]}), cfg, context=ctx2)
        tools = [m for m in agent.get_state(cfg).values["messages"] if isinstance(m, ToolMessage)]
        assert [m.status for m in tools] == ["success", "success", "error"] and ran == ["b.tex"]
        assert "một lần" in tools[-1].content and not re.search(r"\d", tools[-1].content)
        agent.invoke({"messages": [HumanMessage("nạp tiếp")]}, cfg, context=ctx2)
    assert ran == ["b.tex", "b.tex"]
