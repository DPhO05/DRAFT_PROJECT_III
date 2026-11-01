"""P6-T01: llm.chat, the streaming tool-use loop of agent 00."""

import json

import pytest

from tests.fakes import FakeLLM
from tutor import llm

TOOLS = [
    {"name": "student_profile", "description": "Hồ sơ", "input_schema": {"type": "object"}},
    {"name": "student_mistakes", "description": "Lỗi", "input_schema": {"type": "object"}},
]
ASK = [{"role": "user", "content": "An dạo này thế nào?"}]


@pytest.fixture
def log(tmp_path):
    p = tmp_path / "llm.jsonl"
    llm.configure(p, {})
    yield p
    llm.set_backend(None)


def ctx():
    return llm.CallContext(graph=None, conversation_id="2026-11-01-1", redact={"Nguyễn Văn An": "HS-01"})


def lines(p):
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()]


def fold(s):
    return "".join(llm._fold(c) for c in s)


def tool(name, **inp):
    return {"type": "tool_use", "name": name, "input": inp}


def text(t):
    return {"type": "text", "text": t}


def run(fake, messages=ASK, run_tool=lambda name, inp: (f"kết quả {name}", False), turns=8):
    llm.set_backend(fake)
    return list(llm.chat("00", ["cố định"], TOOLS, messages, run_tool=run_tool, context=ctx(), max_tool_turns=turns))


def test_two_tools_three_log_rows(log):
    fake = FakeLLM({"00": [[tool("student_profile", code="HS-01")], [tool("student_mistakes", code="HS-01")],
                           [text("Xong.")]]})  # fmt: skip
    events = run(fake)
    rows = lines(log)
    assert [r["agent"] for r in rows] == ["00"] * 3
    assert {r["conversation_id"] for r in rows} == {"2026-11-01-1"} and {r["graph"] for r in rows} == {None}
    assert [r["tools"] for r in rows] == [["student_profile"], ["student_mistakes"], []]
    assert fake.calls[1]["messages"][-1]["content"][0] == {
        "type": "tool_result", "tool_use_id": "tu1", "content": "kết quả student_profile"}  # fmt: skip
    assert [(e["name"], e["state"]) for e in events if e["type"] == "tool"] == [
        ("student_profile", "start"), ("student_profile", "done"),
        ("student_mistakes", "start"), ("student_mistakes", "done")]  # fmt: skip
    assert events[-1] == {"type": "end", "text": "Xong.", "stopped": None}


def test_stops_after_max_tool_turns(log):
    fake = FakeLLM({"00": lambda messages: [tool("student_profile", code="HS-01")]})
    ran = []
    events = run(fake, run_tool=lambda name, inp: ran.append(name) or ("x", False))
    assert len(ran) == 8 and len(fake.calls) == 9
    assert events[-1]["stopped"] == "max_tool_turns"


def test_tool_error_goes_back(log):
    fake = FakeLLM({"00": [[tool("student_profile", code="HS-01")], [text("Thầy chọn mức nhé.")]]})
    events = run(fake, run_tool=lambda name, inp: ("Mức phải là dễ / vừa / khó", True))
    result = fake.calls[1]["messages"][-1]["content"][0]
    assert result["is_error"] is True and result["content"] == "Mức phải là dễ / vừa / khó"
    assert [e["state"] for e in events if e["type"] == "tool"] == ["start", "error"]
    assert events[-1]["text"] == "Thầy chọn mức nhé."


def test_thinking_block_kept(log):
    thinking = {"type": "thinking", "thinking": "", "signature": "s1"}
    fake = FakeLLM({"00": [[thinking, tool("student_profile", code="HS-01")], [text("Xong.")]]})
    run(fake)
    sent = fake.calls[1]["messages"][-2]
    assert sent["role"] == "assistant"
    assert [b["type"] for b in sent["content"]] == ["thinking", "tool_use"]
    assert sent["content"][0] == thinking


def test_retry_before_first_delta(log):
    fake = FakeLLM({"00": [llm.Retryable("529"), llm.Retryable("529"), [text("Được rồi.")]]})
    events = run(fake)
    assert [r["result"] for r in lines(log)] == ["retry", "retry", "ok"]
    assert "".join(e["delta"] for e in events if e["type"] == "text") == "Được rồi."


def test_no_retry_after_delta(log):
    llm.set_backend(fake := FakeLLM({"00": [[text("Tháng này"), llm.Retryable("x")]]}))
    seen = []
    with pytest.raises(llm.LLMUnavailable):
        for e in llm.chat("00", ["f"], TOOLS, ASK, run_tool=lambda n, i: ("", False), context=ctx(), max_tool_turns=8):
            seen.append(e)
    assert seen and {e["type"] for e in seen} == {"text"}
    assert "".join(e["delta"] for e in seen) == "Tháng này"
    assert len(fake.calls) == 1


def test_masks_payload_and_log(log):
    fake = FakeLLM({"00": [[tool("student_mistakes", code="HS-01")], [text("HS-01 yếu phần dấu.")]]})
    run(fake, messages=[{"role": "user", "content": "Nguyễn Văn An yếu gì?"}],
        run_tool=lambda name, inp: ("Lỗi của nguyen van an: 3 lần nhầm dấu", False))  # fmt: skip
    sent = fold(json.dumps(fake.calls, ensure_ascii=False))
    logged = fold(log.read_text(encoding="utf-8"))
    for raw in (sent, logged):
        assert "van an" not in raw and "hs-01" in raw
    assert fake.calls[1]["messages"][-1]["content"][0]["content"] == "Lỗi của HS-01: 3 lần nhầm dấu"
    assert all(r["name_masked"] is True for r in lines(log))


def test_chat_request_shape():
    tools = [{"name": "z_last"}, {"name": "a_first"}]
    msgs = [{"role": "user", "content": "hỏi"}]
    req = llm.chat_request("claude-opus-5-5", ["a", "b"], tools, msgs)
    assert req["system"][-1]["cache_control"] == {"type": "ephemeral"}
    assert [("cache_control" in b) for b in req["system"]] == [False, True]
    assert [b["text"] for b in req["system"]] == ["a", "b"]
    assert req["thinking"] == {"type": "adaptive"} and req["output_config"] == {"effort": "medium"}
    assert req["max_tokens"] == 64000 and req["model"] == "claude-opus-5-5"
    assert req["fallbacks"] == "default" and req["betas"] == ["server-side-fallback-2026-07-01"]
    assert req["tools"] == tools and req["messages"] == msgs
