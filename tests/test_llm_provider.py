"""Model string picks the provider: "openai:<name>" -> OpenAI, no prefix -> Anthropic."""

import json
import os

import pytest
from pydantic import BaseModel

from tests.fakes import FakeLLM
from tutor import llm


class Out(BaseModel):
    answer: str


def fake() -> FakeLLM:
    return FakeLLM({"01": Out(answer="x"), "02": Out(answer="x")})


@pytest.fixture
def setup(tmp_path):
    llm.set_backend(None)

    def configure(models):
        llm.configure(tmp_path / "llm.jsonl", models)

    return configure


def ctx():
    return llm.CallContext(graph=None)


def test_split_model(setup):
    assert llm.split_model("openai:gpt-5.6-sol") == ("openai", "gpt-5.6-sol")
    assert llm.split_model("claude-opus-5-5") == ("anthropic", "claude-opus-5-5")
    assert llm.split_model("anthropic:claude-x") == ("anthropic", "claude-x")
    assert llm.split_model("dev-fake") == ("anthropic", "dev-fake")
    with pytest.raises(ValueError):
        llm.split_model("gpt:x")


def test_call_routes_by_prefix(setup, monkeypatch):
    monkeypatch.setattr(llm, "_chat", {})
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    setup({"01": "claude-x"})
    assert isinstance(llm.model("01"), llm.GuardedAnthropic) and llm.model("01").model == "claude-x"


def test_unknown_provider_is_unavailable(setup, monkeypatch):
    setup({"01": "gpt:x", "00": "gpt:x"})
    monkeypatch.setattr(llm, "_last_result", "ok")
    with pytest.raises(llm.LLMUnavailable, match="không biết provider gpt"):
        llm.call("01", ["cố định"], Out, student_work="bài", context=ctx())
    with pytest.raises(llm.LLMUnavailable, match="không biết provider gpt"):
        llm.model("00")
    assert llm.status() == "error"


def test_override_wins(setup):
    setup({"01": "openai:gpt-y"})
    fk = fake()
    llm.set_backend(fk)
    llm.call("01", ["cố định"], Out, student_work="bài", context=ctx())
    assert [c["model"] for c in fk.calls] == ["gpt-y"]


def test_providers_from_models():
    models = {"00": "openai:gpt-5.6-sol", "02": "claude-opus-5-5", "03": "x:y"}
    assert llm.providers(models) == ["anthropic", "openai"]
    assert llm.providers({"00": "openai:a", "01": "openai:b"}) == ["openai"]


def test_use_key_resets_cached_models_only(setup, monkeypatch):
    setup({"01": "openai:gpt-y"})
    monkeypatch.setattr(llm, "_chat", {"openai:gpt-y": object()})
    llm.use_key("openai", "sk-test-" + "a" * 30)
    assert llm._chat == {} and os.environ["OPENAI_API_KEY"] == "sk-test-" + "a" * 30
    fk = fake()
    llm.set_backend(fk)
    llm.use_key("openai", "sk-test-" + "b" * 30)
    assert llm._backend is fk and os.environ["OPENAI_API_KEY"] == "sk-test-" + "b" * 30


def test_missing_openai_key_points_to_settings(monkeypatch):
    llm.set_backend(None)
    monkeypatch.setattr(llm, "_models", {"02": "openai:gpt-y"})
    monkeypatch.setattr(llm, "_chat", {})
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(llm.KeyRejected) as e:
        llm.model("02")
    assert str(e.value) == "Thiếu OPENAI_API_KEY: nhập khoá ở ⚙ Cài đặt rồi thử lại"


def test_openai_model_times_out(monkeypatch):
    """A hung call ends after CALL_TIMEOUT s, not the SDK's 600 s, and then counts as a network retry."""
    llm.set_backend(None)
    monkeypatch.setattr(llm, "_models", {"02": "openai:gpt-y"})
    monkeypatch.setattr(llm, "_chat", {})
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-" + "c" * 30)
    m = llm.model("02")
    assert m.root_client.timeout == llm.CALL_TIMEOUT == 120


# GuardedAnthropic over httpx2.MockTransport (C-34): the SDK client is swapped in `_client` / `_async_client` (K25).
ANT = {"input_tokens": 100, "output_tokens": 7, "cache_read_input_tokens": 60, "cache_creation_input_tokens": 20}


def msg(content, stop="end_turn", **extra):
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-x",
        "content": content,
        "stop_reason": stop,
        "stop_sequence": None,
        "usage": ANT,
        **extra,
    }


def anthropic_model(*replies):
    """What llm.model builds for "anthropic:claude-x", with its two SDK clients over a mock transport."""
    import anthropic
    import httpx2

    bodies, queue = [], list(replies)

    def handler(req):
        bodies.append(json.loads(req.content))
        r = queue.pop(0)
        if isinstance(r, list):
            sse = "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in r)
            return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=sse.encode())
        if isinstance(r, int):
            kind = "overloaded_error" if r == 529 else "api_error"
            return httpx2.Response(r, json={"type": "error", "error": {"type": kind, "message": "x"}})
        return httpx2.Response(200, json=r)

    m = llm.model("01")
    sync = httpx2.Client(transport=httpx2.MockTransport(handler))
    aio = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    m._client = anthropic.Anthropic(api_key="k", max_retries=0, timeout=m.default_request_timeout, http_client=sync)
    m._async_client = anthropic.AsyncAnthropic(
        api_key="k", max_retries=0, timeout=m.default_request_timeout, http_client=aio
    )
    return m, bodies


@pytest.fixture
def ant(tmp_path, monkeypatch):
    llm.set_backend(None)
    monkeypatch.setattr(llm, "_sleep", lambda s: None)

    def setup(*replies):
        monkeypatch.setattr(llm, "_chat", {})
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        llm.configure(tmp_path / "llm.jsonl", {"01": "anthropic:claude-x"})
        m, bodies = anthropic_model(*replies)
        return m, bodies, tmp_path / "llm.jsonl"

    return setup


def rows(log):
    return [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]


def test_model_builds_guarded_anthropic(monkeypatch, tmp_path):
    llm.set_backend(None)
    llm.configure(tmp_path / "llm.jsonl", {"01": "anthropic:claude-x"})
    monkeypatch.setattr(llm, "_chat", {})
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(llm.KeyRejected, match="Thiếu ANTHROPIC_API_KEY: nhập khoá ở ⚙ Cài đặt rồi thử lại"):
        llm.model("01")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    m = llm.model("01")
    assert isinstance(m, llm.GuardedAnthropic) and m.model == "claude-x"
    assert m.max_retries == 0 and m.default_request_timeout == llm.CALL_TIMEOUT == 120
    assert llm.model("01") is m


def test_anthropic_call_masks_name_and_sends_settings(ant):
    _, bodies, log = ant(msg([{"type": "text", "text": '{"answer": "x"}'}]))
    ctx = llm.CallContext(graph=None, redact={"Nguyễn Văn An": "HS-03"})
    out = llm.call("01", ["cố định"], Out, extra=["đề của Nguyễn Văn An"], student_work="bài", context=ctx)
    assert out.answer == "x"
    body = bodies[0]
    assert "Nguyễn Văn An" not in json.dumps(body, ensure_ascii=False) and "HS-03" in json.dumps(body)
    assert body["thinking"] == {"type": "adaptive"} and body["output_config"]["effort"] == "medium"
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert body["system"][-1]["cache_control"] == {"type": "ephemeral"}
    assert body["fallbacks"] == "default" and body["max_tokens"] == 64000
    (row,) = rows(log)
    assert row["name_masked"] is True and row["result"] == "ok"
    assert (row["input_tokens"], row["output_tokens"], row["cache_read_tokens"], row["cache_write_tokens"]) == (
        100,
        7,
        60,
        20,
    )


def test_anthropic_529_is_retried(ant):
    _, bodies, log = ant(529, msg([{"type": "text", "text": '{"answer": "x"}'}]))
    assert llm.call("01", ["cố định"], Out, student_work="bài", context=ctx()).answer == "x"
    assert len(bodies) == 2 and [r["result"] for r in rows(log)] == ["retry", "ok"]


def test_anthropic_refusal_is_unavailable(ant):
    ant(msg([], stop="refusal", stop_details={"type": "refusal", "category": "cyber", "explanation": None}))
    with pytest.raises(llm.LLMUnavailable, match="Claude từ chối"):
        llm.call("01", ["cố định"], Out, student_work="bài", context=ctx())


def test_anthropic_async_path(ant):
    import asyncio

    m, bodies, _ = ant(msg([{"type": "text", "text": "ok"}]))
    from langchain_core.messages import HumanMessage

    async def run():
        with llm.scope(ctx(), {"agent": "01", "model": "anthropic:claude-x", "user": "u"}):
            return await m.ainvoke([HumanMessage("hi")])

    assert asyncio.run(run()).text == "ok" and len(bodies) == 1


def test_anthropic_thinking_block_goes_back_after_tool_call(ant):
    from langchain_core.messages import HumanMessage, ToolMessage

    think = {"type": "thinking", "thinking": "nghĩ", "signature": "sig-1"}
    use = {"type": "tool_use", "id": "tu1", "name": "f", "input": {"a": 1}}
    m, bodies, _ = ant(msg([think, use], stop="tool_use"), msg([{"type": "text", "text": "xong"}]))
    with llm.scope(ctx(), {"agent": "01", "model": "anthropic:claude-x", "user": "u"}):
        first = m.invoke([HumanMessage("hi")])
        m.invoke([HumanMessage("hi"), first, ToolMessage("kq", tool_call_id="tu1")])
    sent = bodies[1]["messages"][1]["content"]
    assert {"type": "thinking", "thinking": "nghĩ", "signature": "sig-1"} in sent


def test_anthropic_streamed_refusal_is_unavailable(ant):
    from langchain_core.messages import HumanMessage

    start = msg([], stop=None, usage={"input_tokens": 5, "output_tokens": 1})
    detail = {"type": "refusal", "category": "cyber", "explanation": None}
    events = [
        {"type": "message_start", "message": start},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Xin"}},
        {"type": "content_block_stop", "index": 0},
        {
            "type": "message_delta",
            "delta": {"stop_reason": "refusal", "stop_sequence": None, "stop_details": detail},
            "usage": {"output_tokens": 3},
        },
        {"type": "message_stop"},
    ]
    m, _, _ = ant(events)
    with llm.scope(ctx(), {"agent": "01", "model": "anthropic:claude-x", "user": "u"}):
        with pytest.raises(llm.LLMUnavailable, match="Claude từ chối"):
            list(m.stream([HumanMessage("hi")]))
