"""00 as a LangChain agent: `ChatState` thread, six middleware, per-message tools and context.

State a code path (`by_code`) leaves, in order: per tool run an AIMessage with one tool call and its ToolMessage
(artifact = `tutor/` meta, plus `tutor/error` on an error), then one AIMessage with the reply text (`CARD_ONLY` when
code had no text) and `additional_kwargs["tutor/cards"]` = the cards to show, tool cards included.
"""

import threading
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import NotRequired
from uuid import uuid4

from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    AgentState,
    ClearToolUsesEdit,
    ContextEditingMiddleware,
    before_agent,
    before_model,
    wrap_model_call,
    wrap_tool_call,
)
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, SystemMessage, ToolMessage
from langgraph.types import Command

from tutor import llm
from tutor.agents.a00_orchestrator import orchestrator
from tutor.agents.a00_orchestrator.orchestrator import Turn
from tutor.agents.a00_orchestrator.tools import _ONCE, _REFUSED, LABELS, LIMITS, Toolbox
from tutor.services import audit

MAX_MESSAGES = 40
CARD_ONLY = (
    "Mình đã hiện kết quả ở thẻ bên dưới."  # a by_code reply with cards and no text: the API rejects empty content
)


RECHECK = (
    "Thầy/cô vừa lưu kết quả vào hệ thống, nên số liệu cũ trong cuộc trò chuyện có thể đã đổi. "
    "Hãy tra lại bằng công cụ trước khi dùng số cũ."
)


class ChatState(AgentState):
    rank: NotRequired[dict]
    stopped: NotRequired[bool]


@dataclass
class ChatContext:
    turn: Turn
    box: Toolbox
    students: dict[int, dict]
    redact: dict[str, str]
    seen: list[str] = field(default_factory=list)  # tool results of the last model request, after trimming
    resaved: bool = False  # the route sets it when a thread was saved since the last message
    started: Counter = field(default_factory=Counter)
    lock: threading.Lock = field(default_factory=threading.Lock)  # ToolNode runs one message's calls in parallel


def _mask_deep(x, redact: dict[str, str]):
    return llm._mask_all(x, orchestrator._names(redact))[0]


def _is_error(m: ToolMessage) -> bool:
    return m.status == "error"


def _error_message(name: str, call_id: str, text: str) -> ToolMessage:
    return ToolMessage(
        Toolbox._error(name, text).content,
        tool_call_id=call_id,
        name=name,
        status="error",
        artifact={"tutor/error": True},
    )


@before_agent(can_jump_to=["end"])
def by_code(state: ChatState, runtime) -> dict:
    """Confirm words, problem codes and attachments: answered by code, 0 model calls."""
    ctx = runtime.context
    call, ran = orchestrator._direct(ctx.box), []

    def run(name: str, args: dict):
        ran.append((name, args, r := call(name, args)))
        return r

    events = orchestrator.direct(ctx.turn, run, starters=ctx.box.starters, students=ctx.students)
    if events is None:
        return {"stopped": False}  # this message starts clean: the flag is state, so it outlives the last message
    events = list(events)
    messages: list = []
    for name, args, (content, is_error, m) in ran:
        cid = f"code_{uuid4().hex[:12]}"
        messages += [
            AIMessage("", tool_calls=[{"type": "tool_call", "id": cid, "name": name, "args": args}]),
            ToolMessage(
                orchestrator.mask(content, ctx.redact),
                tool_call_id=cid,
                name=name,
                status="error" if is_error else "success",
                artifact=_mask_deep(m, ctx.redact) | ({"tutor/error": True} if is_error else {}),
            ),
        ]
    said = "".join(e["delta"] for e in events if e["type"] == "text")
    cards = [e["card"] for e in events if e["type"] == "card"]
    said, cards = orchestrator.mask(said, ctx.redact), _mask_deep(cards, ctx.redact)
    messages.append(AIMessage(said or CARD_ONLY, additional_kwargs={"tutor/cards": cards}))
    return {"messages": messages, "stopped": False, "jump_to": "end"}


def _limit_turns(max_tool_turns: int):
    @before_model(can_jump_to=["end"])
    def limit_turns(state: ChatState, runtime) -> dict | None:
        rounds = 0
        for m in reversed(state["messages"]):
            if isinstance(m, HumanMessage):
                break
            rounds += isinstance(m, AIMessage) and bool(m.tool_calls)
        return {"stopped": True, "jump_to": "end"} if rounds >= max_tool_turns else None

    return limit_turns


@wrap_tool_call
def limit_starts(request, handler):
    """H5: each start_* once per message, propose_worksheet twice; a refused call never runs."""
    name, ctx = request.tool_call["name"], request.runtime.context
    if name not in LIMITS:
        return handler(request)
    with ctx.lock:  # the slot is taken before the tool runs, so a parallel twin is refused
        if ctx.started[name] >= LIMITS[name]:
            return _error_message(name, request.tool_call["id"], _REFUSED.get(name, _ONCE))
        ctx.started[name] += 1
    out = handler(request)
    if isinstance(out, ToolMessage) and _is_error(out):
        with ctx.lock:
            ctx.started[name] -= 1
    return out


@wrap_tool_call
def keep_masked(request, handler):
    """Names out of tool results before they enter state (C-40); the last rank rides along in `ChatState.rank`."""
    name, ctx = request.tool_call["name"], request.runtime.context
    box = ctx.box
    if name == "propose_worksheet" and (rank := request.state.get("rank")):
        box.ranked, box.rank_student, box.rank_warnings = rank["items"], rank["student"], rank["warnings"]
    out = handler(request)
    if not isinstance(out, ToolMessage):
        return out
    failed = (out.artifact or {}).get("tutor/error") or _is_error(out)
    out = out.model_copy(
        update={
            "content": orchestrator.mask(out.content, ctx.redact),
            "artifact": _mask_deep(out.artifact, ctx.redact),
            "status": "error" if failed else out.status,
        }
    )
    if name != "rank_problems" or failed:
        return out
    items = [{k: i[k] for k in ("ref", "bucket", "reason")} for i in box.ranked]
    rank = {"student": box.rank_student, "items": items, "warnings": box.rank_warnings}
    return Command(update={"messages": [out], "rank": rank})


@wrap_model_call
def recheck(request, handler):
    """After a save the older tool results may be stale: one more system line for this call."""
    if not request.runtime.context.resaved:
        return handler(request)
    old = request.system_message.content if request.system_message else []
    blocks = [{"type": "text", "text": old}] if isinstance(old, str) else list(old)
    return handler(request.override(system_message=SystemMessage(content=[*blocks, {"type": "text", "text": RECHECK}])))


@wrap_model_call
def record_seen(request, handler):
    """Placed inside the trimming middleware: keeps what the model actually received (C-41)."""
    request.runtime.context.seen = [m.content for m in request.messages if isinstance(m, ToolMessage)]
    return handler(request)


class _DropOld(AgentMiddleware[ChatState, ChatContext]):
    """Oldest messages go, cut only just before a HumanMessage: no orphan ToolMessage, the live turn stays (K31)."""

    state_schema = ChatState

    @staticmethod
    def _cut(state: ChatState) -> dict | None:
        msgs = state["messages"]
        if len(msgs) <= MAX_MESSAGES:
            return None
        start = next(
            (i for i, m in enumerate(msgs) if i >= len(msgs) - MAX_MESSAGES and isinstance(m, HumanMessage)), None
        )
        return {"messages": [RemoveMessage(id=m.id) for m in msgs[:start]]} if start else None

    def before_model(self, state, runtime):
        return self._cut(state)

    def after_agent(self, state, runtime):
        return self._cut(state)


def build(model, tools, saver, *, max_tool_turns: int, system: list[str] | None = None):
    """The agent for one message: tools are per message, the thread (`saver`) is per conversation."""
    prompt = SystemMessage(content=[{"type": "text", "text": t} for t in system]) if system else None
    trim_old_tools = ContextEditingMiddleware(edits=[ClearToolUsesEdit(trigger=30000, keep=3)])
    return create_agent(
        model,
        tools,
        system_prompt=prompt,
        middleware=[
            by_code,
            _limit_turns(max_tool_turns),
            limit_starts,
            keep_masked,
            recheck,
            trim_old_tools,
            record_seen,
            _DropOld(),
        ],
        state_schema=ChatState,
        context_schema=ChatContext,
        checkpointer=saver,
    )


def scope(context: llm.CallContext, fixed: list[str], tool_defs: list[dict]):
    base = {
        "agent": "00",
        "prompt_version": orchestrator.version(fixed, tool_defs),
        "model": llm._route("00")[2],
        "graph": context.graph,
        "conversation_id": context.conversation_id,
    }
    return llm.scope(context, base)


def _text(chunk) -> str:
    c = chunk.content
    return c if isinstance(c, str) else "".join(b.get("text", "") for b in c if isinstance(b, dict))


def _tool_done(m: ToolMessage) -> dict:
    art = m.artifact if isinstance(m.artifact, dict) else {}
    name = m.name or ""
    ev = {"type": "tool", "name": name, "label": LABELS.get(name, "")}
    if _is_error(m):
        return ev | {"state": "error"}
    return ev | {"state": "done", "summary": art.get("tutor/summary", "")}


def _starts(msgs) -> Iterator[dict]:
    for m in msgs:
        for c in getattr(m, "tool_calls", None) or []:
            yield {"type": "tool", "name": c["name"], "label": LABELS.get(c["name"], ""), "state": "start"}


def events(agent, ctx: ChatContext, cfg: dict) -> Iterator[dict]:
    """NDJSON events of one tutor message, as `orchestrator.reply` gives them, without `start` / `error`.

    agent: `build(...)`; ctx.resaved: set by the caller; the thread (`cfg`) carries the earlier messages.
    """
    turn, redact = ctx.turn, ctx.redact
    today = orchestrator.today_line(ctx.box.today)
    human = HumanMessage(orchestrator.mask(f"{today}\n\n{turn.text}", redact))
    said, streamed, ran, by_code, stopped, sources = [], False, False, False, None, []
    for mode, data in agent.stream({"messages": [human]}, cfg, context=ctx, stream_mode=["messages", "updates"]):
        if mode == "messages":
            chunk, meta = data
            if meta.get("langgraph_node") != "model" or not (delta := _text(chunk)):
                continue
            if said and not streamed:  # text of an earlier model call in this message: a paragraph apart
                said.append("\n\n")
                yield {"type": "text", "delta": "\n\n"}
            said.append(delta)
            streamed = True
            yield {"type": "text", "delta": delta}
            continue
        for node, upd in data.items():
            if not isinstance(upd, dict):
                continue
            stopped = upd.get("stopped", stopped)
            msgs = upd.get("messages") or []
            if node == "model":
                streamed = False
                yield from _starts(msgs)
            elif node == "tools":
                ran = True
                for m in (m for m in msgs if isinstance(m, ToolMessage)):
                    yield _tool_done(m)
                    art = m.artifact if isinstance(m.artifact, dict) else {}
                    sources += [art["tutor/source"]] if "tutor/source" in art else []
                    if "tutor/card" in art and not _is_error(m):
                        yield {"type": "card", "card": art["tutor/card"]}
            elif node.startswith("by_code") and msgs:
                by_code = True
                yield from _starts(msgs)
                for m in (m for m in msgs if isinstance(m, ToolMessage)):
                    yield _tool_done(m)
                    sources += [m.artifact["tutor/source"]] if "tutor/source" in (m.artifact or {}) else []
                final = msgs[-1]
                if final.content != CARD_ONLY:
                    yield {"type": "text", "delta": final.content}
                for card in final.additional_kwargs.get("tutor/cards", []):
                    yield {"type": "card", "card": card}
    if ran and not by_code:  # C-41: numbers the model can still see, plus the date line
        known = audit.known_numbers([*ctx.seen, today])
        for w in audit.unverified("".join(said), known):
            yield {"type": "warning", "kind": "unverified_number", **w}
    items = list(dict.fromkeys(sources))
    yield {"type": "source", "items": items} if items else {"type": "source", "no_student_data": True}
    yield {"type": "done", "stopped": "max_tool_turns" if stopped else None}
