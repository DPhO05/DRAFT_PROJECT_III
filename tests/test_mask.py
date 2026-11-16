"""P6-T02: masking of every student name before an agent 00 call."""

import json

from tests.fakes import FakeLLM
from tutor import llm

MINH = {"Nguyễn Văn Minh": "HS-03"}


def test_full_name_to_code():
    assert llm.mask("Nguyễn Văn Minh làm sai", MINH) == "HS-03 làm sai"
    assert llm.mask("NGUYEN VAN MINH", MINH) == "HS-03"


def test_short_word_untouched():
    assert llm.mask("chứng minh rằng", MINH) == "chứng minh rằng"


def test_same_given_name_other_family():
    redact = MINH | {"Trần Văn Minh": "HS-05"}
    assert llm.mask("Trần Văn Minh và Nguyễn Văn Minh", redact) == "HS-05 và HS-03"


def test_nested_names_longest_wins():
    redact = {"Văn Minh": "HS-02"} | MINH
    assert llm.mask("Nguyễn Văn Minh làm sai, Văn Minh đúng", redact) == "HS-03 làm sai, HS-02 đúng"


def test_chat_masks_pasted_tex(tmp_path):
    llm.configure(tmp_path / "llm.jsonl", {})
    fake = FakeLLM({"00": [[{"type": "text", "text": "Đã nhận."}]]})
    llm.set_backend(fake)
    tex = "Chấm giúp: \\begin{problem}[8DS-PT1-001] Bài làm của Nguyễn Văn Minh: $4x=20$ \\end{problem}"
    ctx = llm.CallContext(graph=None, conversation_id="2026-11-01-1", redact=MINH)
    list(llm.chat("00", ["f"], [], [{"role": "user", "content": tex}], run_tool=lambda n, i: ("", False),
                  context=ctx, max_tool_turns=8))  # fmt: skip
    sent = json.dumps(fake.calls, ensure_ascii=False)
    assert "Văn Minh" not in sent and "HS-03" in sent


def test_name_split_by_line_break_or_double_space():
    assert llm.mask("Nguyễn Văn\nAn làm sai", {"Nguyễn Văn An": "HS-01"}) == "HS-01 làm sai"
    assert llm.mask("Nguyễn  Văn   An", {"Nguyễn Văn An": "HS-01"}) == "HS-01"


def test_mask_latex_spaced_names():
    redact = {"Nguyễn Văn An": "HS-01"}
    for text in ("Nguyễn~Văn~An", "Nguyễn\\ Văn\\ An", "Nguyễn\\,Văn~An", "nguyen~van an"):
        assert llm.mask(text, redact) == "HS-01"
    assert llm.mask("An~ và Nguyễn~", redact) == "An~ và Nguyễn~"


def test_mask_name_split_by_braces():
    redact = {"Nguyễn Văn An": "HS-01"}
    for text in ("\\textbf{Nguyễn} Văn An", "{Nguyễn}{Văn}{An}"):
        out = llm.mask(text, redact)
        assert "HS-01" in out and "Nguyễn" not in out


def _bound_chat(tmp_path, turns):
    from langchain_core.messages import HumanMessage, SystemMessage

    llm.configure(tmp_path / "llm.jsonl", {})
    fake = FakeLLM({"00": turns})
    llm.set_backend(fake)
    tool = {"name": "t", "description": "d", "input_schema": {"type": "object", "properties": {}}}
    m = llm.model("00").bind_tools([tool])
    return fake, m, (SystemMessage("cố định"), HumanMessage("Nguyễn Văn Minh làm sai"))


def test_backend_chat_tool_turn(tmp_path):
    from langchain_core.messages import AIMessage

    from tutor.agents.a00_orchestrator import tools

    fake, _, _ = _bound_chat(
        tmp_path, [[{"type": "text", "text": "Xem nhé"}, {"type": "tool_use", "name": "list_students", "input": {}}]]
    )
    m = llm.model("00").bind_tools(tools.lc_tools(tools.Toolbox(None, settings={}, today=None, text=""), ["a.b"]))
    with llm.scope(llm.CallContext(graph=None, redact=MINH), {"agent": "00"}):
        ai = m.invoke("chào")
    assert isinstance(ai, AIMessage) and ai.text == "Xem nhé"
    assert ai.tool_calls == [{"type": "tool_call", "id": "tu1", "name": "list_students", "args": {}}]
    assert ai.usage_metadata["total_tokens"] > 0
    sent = fake.calls[0]["tools"]
    assert len(sent) == 11 and sent[0]["input_schema"]["required"] == ["refs"]
    kind = next(t for t in sent if t["name"] == "student_mistakes")["input_schema"]["properties"]["kind"]
    assert kind["enum"] == ["a.b", None]


def test_backend_chat_tool_result_and_mask(tmp_path):
    from langchain_core.messages import AIMessage, ToolMessage

    fake, m, (system, human) = _bound_chat(tmp_path, [[{"type": "text", "text": "Xong"}]])
    call = {"type": "tool_call", "id": "x1", "name": "t", "args": {"a": 1}}
    thread = [
        system,
        human,
        AIMessage("", tool_calls=[call]),
        ToolMessage("kết quả", tool_call_id="x1", status="error"),
    ]
    with llm.scope(llm.CallContext(graph=None, redact=MINH), {"agent": "00"}):
        assert [c.text for c in m.stream(thread)][0] == "Xong"
    sent = fake.calls[0]
    assert sent["system"] == ["cố định"]
    assert "Văn Minh" not in json.dumps(sent, ensure_ascii=False) and "HS-03" in json.dumps(sent)
    assert sent["messages"][1]["content"] == [{"type": "tool_use", "id": "x1", "name": "t", "input": {"a": 1}}]
    assert sent["messages"][2]["content"] == [
        {"type": "tool_result", "tool_use_id": "x1", "content": "kết quả", "is_error": True}
    ]


def test_backend_chat_stream_ends_with_tool_calls(tmp_path):
    from langchain_core.messages import AIMessageChunk

    _, m, (system, human) = _bound_chat(
        tmp_path, [[{"type": "text", "text": "Để xem nhé."}, {"type": "tool_use", "name": "t", "input": {"a": 1}}]]
    )
    with llm.scope(llm.CallContext(graph=None, redact=MINH), {"agent": "00"}):
        chunks = list(m.stream([system, human]))
    whole = sum(chunks[1:], chunks[0])
    assert isinstance(whole, AIMessageChunk) and whole.text == "Để xem nhé."
    assert whole.tool_calls == [{"type": "tool_call", "id": "tu1", "name": "t", "args": {"a": 1}}]
    assert len(chunks) > 2


def test_backend_chat_artifact_error_flag_is_error(tmp_path):
    from langchain_core.messages import AIMessage, ToolMessage

    fake, m, (system, human) = _bound_chat(tmp_path, [[{"type": "text", "text": "Ok"}]])
    call = {"type": "tool_call", "id": "x1", "name": "t", "args": {}}
    thread = [
        system,
        human,
        AIMessage("", tool_calls=[call]),
        ToolMessage("lỗi", tool_call_id="x1", artifact={"tutor/error": True}),
    ]
    with llm.scope(llm.CallContext(graph=None, redact=MINH), {"agent": "00"}):
        m.invoke(thread)
    assert fake.calls[0]["messages"][2]["content"][0]["is_error"] is True
