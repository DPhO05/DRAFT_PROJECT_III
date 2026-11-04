"""Model string picks the provider: "openai:<name>" -> OpenAI, no prefix -> Anthropic."""

import json
import os

import pytest
from pydantic import BaseModel

from tests.fakes import FakeLLM
from tutor import llm


class Out(BaseModel):
    answer: str


ASK = [{"role": "user", "content": "An dạo này thế nào?"}]


def fake() -> FakeLLM:
    return FakeLLM({"01": Out(answer="x"), "02": Out(answer="x"), "00": [[{"type": "text", "text": "Chào"}]]})


@pytest.fixture
def setup(tmp_path, monkeypatch):
    fa, fo = fake(), fake()
    llm.set_backend(None)
    monkeypatch.setattr(llm, "_live", {})
    monkeypatch.setattr(llm, "PROVIDERS", {"anthropic": lambda: fa, "openai": lambda: fo})
    log = tmp_path / "llm.jsonl"

    def configure(models):
        llm.configure(log, models)
        return fa, fo, log

    return configure


def ctx():
    return llm.CallContext(graph=None)


def chat():
    return list(
        llm.chat("00", ["cố định"], [], ASK, run_tool=lambda name, inp: ("x", False), context=ctx(), max_tool_turns=1)
    )


def test_split_model(setup):
    assert llm.split_model("openai:gpt-5.6-sol") == ("openai", "gpt-5.6-sol")
    assert llm.split_model("claude-opus-5-5") == ("anthropic", "claude-opus-5-5")
    assert llm.split_model("anthropic:claude-x") == ("anthropic", "claude-x")
    assert llm.split_model("dev-fake") == ("anthropic", "dev-fake")
    with pytest.raises(ValueError):
        llm.split_model("gpt:x")


def test_call_routes_by_prefix(setup):
    fa, fo, log = setup({"01": "claude-x", "02": "openai:gpt-y"})
    llm.call("01", ["cố định"], Out, student_work="bài", context=ctx())
    llm.call("02", ["cố định"], Out, student_work="bài", context=ctx())
    assert fa.calls[0]["model"] == "claude-x" and len(fa.calls) == 1
    assert fo.calls[0]["model"] == "gpt-y" and len(fo.calls) == 1
    assert [json.loads(x)["model"] for x in log.read_text(encoding="utf-8").splitlines()] == [
        "claude-x",
        "openai:gpt-y",
    ]


def test_chat_routes_by_prefix(setup):
    fa, fo, log = setup({"00": "openai:gpt-y"})
    chat()
    assert fo.count["00"] == 1 and fa.count["00"] == 0
    assert fo.calls[0]["model"] == "gpt-y"
    assert json.loads(log.read_text(encoding="utf-8").splitlines()[0])["model"] == "openai:gpt-y"


def test_one_backend_per_provider(setup, monkeypatch):
    fa, fo, _ = setup({"01": "openai:a", "02": "openai:b"})
    made = []
    monkeypatch.setattr(llm, "PROVIDERS", {"openai": lambda: made.append(1) or fo})
    llm.call("01", ["cố định"], Out, student_work="bài", context=ctx())
    llm.call("02", ["cố định"], Out, student_work="bài", context=ctx())
    assert made == [1] and [c["model"] for c in fo.calls] == ["a", "b"]


def test_unknown_provider_is_unavailable(setup, monkeypatch):
    setup({"01": "gpt:x", "00": "gpt:x"})
    monkeypatch.setattr(llm, "_last_result", "ok")
    with pytest.raises(llm.LLMUnavailable, match="không biết provider gpt"):
        llm.call("01", ["cố định"], Out, student_work="bài", context=ctx())
    with pytest.raises(llm.LLMUnavailable, match="không biết provider gpt"):
        chat()
    assert llm.status() == "error"


def test_override_wins(setup):
    fa, fo, _ = setup({"01": "openai:gpt-y"})
    fk = fake()
    llm.set_backend(fk)
    llm.call("01", ["cố định"], Out, student_work="bài", context=ctx())
    assert [c["model"] for c in fk.calls] == ["gpt-y"]
    assert fa.calls == [] and fo.calls == [] and llm._live == {}


def test_providers_from_models():
    models = {"00": "openai:gpt-5.6-sol", "02": "claude-opus-5-5", "03": "x:y"}
    assert llm.providers(models) == ["anthropic", "openai"]
    assert llm.providers({"00": "openai:a", "01": "openai:b"}) == ["openai"]


def test_use_key_resets_real_backend_only(setup):
    fa, fo, _ = setup({"01": "openai:gpt-y"})
    llm._live.update(anthropic=fa, openai=fo)
    llm.use_key("openai", "sk-test-" + "a" * 30)
    assert llm._live == {"anthropic": fa} and os.environ["OPENAI_API_KEY"] == "sk-test-" + "a" * 30
    fk = fake()
    llm.set_backend(fk)
    llm.use_key("openai", "sk-test-" + "b" * 30)
    assert llm._backend is fk and os.environ["OPENAI_API_KEY"] == "sk-test-" + "b" * 30


def test_missing_openai_key_points_to_settings():
    with pytest.raises(llm.LLMUnavailable) as e:
        llm.OpenAIBackend()
    assert str(e.value) == "Thiếu OPENAI_API_KEY: nhập khoá ở ⚙ Cài đặt rồi thử lại"
