"""P4-T02: agent 00 as a LangChain agent: thread state, context trimming, code paths, start limits, rank memory."""

import json
import re
import sqlite3
from contextlib import closing

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.sqlite import SqliteSaver

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

    def say(self, words, *, thread="t", starters=None, tools=(), max_tool_turns=8):
        box = Toolbox(self.conn, settings=config.defaults(), today=self.w["today"], text=words, starters=starters)
        ctx = chat.ChatContext(Turn(words), box, self.w["students"], self.w["redact"])
        agent = chat.build(
            llm.model("00"),
            [*lc_tools(box, self.codes), *tools],
            self.saver,
            max_tool_turns=max_tool_turns,
            system=["sys"],
        )
        cfg = {"configurable": {"thread_id": thread}, "recursion_limit": 200}
        cc = llm.CallContext(graph=None, conversation_id="c", redact=self.w["redact"])
        with chat.scope(cc, ["sys"], tool_defs(self.codes)):
            agent.invoke({"messages": [HumanMessage(words)]}, cfg, context=ctx)
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
    assert state["stopped"] is True and len(r.fake.calls) == 3
    r.script, r.fake.handlers["00"] = [[text("xong")]], lambda m: [text("xong")]
    assert r.say("lại", tools=[look])["stopped"] is False


def test_names_never_enter_state(make):
    name = "Nguyễn Văn An"

    @tool(response_format="content_and_artifact")
    def who(n: int) -> tuple[str, dict]:
        """Who."""
        return f"học sinh {name}", {}

    r = make([[use("who", n=1)], [text("xong")]])
    state = r.say("ai?", tools=[who])
    assert name not in json.dumps([m.content for m in state["messages"]], ensure_ascii=False)
    assert "HS-01" in [m for m in state["messages"] if isinstance(m, ToolMessage)][0].content
