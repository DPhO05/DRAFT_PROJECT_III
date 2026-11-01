"""FakeLLM: same backend interface as llm.AnthropicBackend, no network (C-34)."""

import copy
import re
from collections import Counter
from collections.abc import Callable, Iterator

from tutor import llm

USAGE = {"input": 100, "output": 20, "cache_read": 80, "cache_write": 0}


class FakeLLM:
    """handlers[agent] = model instance | exception | None (invalid output) | callable(user, system) -> one of those.

    chat (agent 00): handlers[agent] = list of turns, one per call, or callable(messages) -> turn for every call.
    A turn = list of blocks (text, tool_use without id, thinking) | exception raised before any text |
    callable(messages) -> turn; an exception inside the list is raised after the blocks before it.
    """

    def __init__(self, handlers: dict[str, object] | None = None):
        self.handlers = handlers or {}
        self.calls: list[dict] = []
        self.count: Counter = Counter()
        self._tool_ids = 0

    def __call__(self, *, agent: str, model: str, system: list[str], user: str, schema: type) -> llm.Reply:
        self.calls.append({"agent": agent, "model": model, "system": system, "user": user})
        self.count[agent] += 1
        out = self.handlers[agent]
        if isinstance(out, Callable) and not isinstance(out, type) and not hasattr(out, "model_dump"):
            out = out(user=user, system=system)
        if isinstance(out, BaseException):
            raise out
        if out is None:
            return llm.Reply(None, "not json", USAGE)
        return llm.Reply(out, out.model_dump_json(), USAGE)

    def chat(
        self, *, agent: str, model: str, system: list[str], tools: list[dict], messages: list[dict]
    ) -> Iterator[dict]:
        self.calls.append(copy.deepcopy({"agent": agent, "model": model, "system": system, "tools": tools,
                                         "messages": messages}))  # fmt: skip
        self.count[agent] += 1
        turn = self.handlers[agent]
        if isinstance(turn, list):
            turn = turn[self.count[agent] - 1]
        if callable(turn):
            turn = turn(messages)
        if isinstance(turn, BaseException):
            raise turn
        content = []
        for b in turn:
            if isinstance(b, BaseException):
                raise b
            if b["type"] == "text":
                for i in range(0, len(b["text"]), 8):
                    yield {"type": "text", "delta": b["text"][i : i + 8]}
            if b["type"] == "tool_use":
                self._tool_ids += 1
                b = {"type": "tool_use", "id": f"tu{self._tool_ids}", "name": b["name"], "input": b["input"]}
            content.append(copy.deepcopy(b))
        stop = "tool_use" if any(b["type"] == "tool_use" for b in content) else "end_turn"
        yield {"type": "message", "content": content, "stop_reason": stop, "usage": dict(USAGE)}


def lane_handlers(*, mistakes: int = 1, fail_03: object = None) -> dict:
    """Generic 02 · 03 · 04 outputs for any problem: full marks, `mistakes` mistakes at step 1, 04 agrees.

    fail_03(user) -> exception to raise for that call, or None.
    """
    from tutor.agents import diagnoser, grader, verifier

    def g02(user, system):
        if "Rubric:" not in user:  # generate_rubric
            return grader.RubricDraftOut(items=[grader.RubricItem(item_id="r1", text="Đáp số đúng", points=2)])
        items = re.findall(r"^\[(\w+)\] \(([\d.]+) điểm\)", user.split("Rubric:")[1], re.M)
        return grader.GradeOut(
            items=[grader.GradeItem(item_id=i, passed=True, evidence_latex="x") for i, _ in items],
            score=sum(float(p) for _, p in items),
        )

    def g03(user, system):
        if fail_03 and (e := fail_03(user)):
            raise e
        return diagnoser.DiagnosisOut(corrected_latex="", mistakes=[
            diagnoser.MistakeOut(step_idx=1, code="other.unclear", kc_id=None, description=f"lỗi {k}",
                                 evidence_latex="x", confidence=0.5)
            for k in range(mistakes)
        ])  # fmt: skip

    return {"02": g02, "03": g03, "04": verifier.VerdictOut(verdict="agree", reason="đúng")}
