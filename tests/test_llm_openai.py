"""OpenAIBackend: structured call and streaming tool loop on the Responses API, over a mock transport (C-34)."""

import json
import traceback

import httpx2
import openai
import pytest

from tests.fakes import openai_client
from tutor import llm
from tutor.agents.a00_orchestrator.tools import tool_defs
from tutor.agents.a01_ingest import ingest
from tutor.agents.a02_grader import grader
from tutor.agents.a03_diagnoser import diagnoser
from tutor.agents.a04_verifier import verifier

MODEL = "openai:gpt-5.6-sol"
U = {
    "input_tokens": 1896,
    "input_tokens_details": {"cached_tokens": 1874, "cache_write_tokens": 19},
    "output_tokens": 6,
    "output_tokens_details": {"reasoning_tokens": 0},
}
OK = '{"items": [], "score": 0, "alt_method": false}'
REQ = httpx2.Request("POST", "http://x")


def RESP(text, status="completed", reason=None, content=None):
    part = {"type": "output_text", "text": text, "annotations": []}
    return {
        "id": "r1",
        "status": status,
        "incomplete_details": {"reason": reason} if reason else None,
        "output": [
            {"type": "message", "id": "m1", "role": "assistant", "phase": "final_answer", "content": content or [part]}
        ],
        "usage": U,
    }


@pytest.fixture
def use_openai(tmp_path, monkeypatch):
    def setup(*replies, models=None):
        client, bodies = openai_client(*replies)
        monkeypatch.setitem(llm.PROVIDERS, "openai", lambda: llm.OpenAIBackend(client))
        monkeypatch.setattr(llm, "_live", {})
        llm.set_backend(None)
        llm.configure(tmp_path / "llm.jsonl", models or {"02": MODEL})
        return bodies

    return setup


def rows(tmp_path):
    return [json.loads(x) for x in (tmp_path / "llm.jsonl").read_text(encoding="utf-8").splitlines()]


def grade(**kw):
    return llm.call("02", ["sys"], grader.GradeOut, student_work="bài", context=llm.CallContext(graph=None, **kw))


def objects(x):
    if isinstance(x, dict):
        if "properties" in x:
            yield x
        for v in x.values():
            yield from objects(v)
    elif isinstance(x, list):
        for v in x:
            yield from objects(v)


def test_request_shape():
    r = llm.responses_request("gpt-5.6-sol", ["a", "b"], "u", grader.GradeOut)
    assert r["store"] is False and r["instructions"] == "a\n\nb"
    assert r["text"]["format"]["strict"] is True and r["text"]["format"]["name"] == "GradeOut"
    assert r["max_output_tokens"] == 32000 and r["reasoning"] == {"effort": "medium"}
    assert "previous_response_id" not in r and "include" not in r


@pytest.mark.parametrize(
    "schema",
    [ingest.MatchResult, grader.GradeOut, grader.RubricDraftOut, diagnoser.DiagnosisOut, verifier.VerdictOut],
)
def test_strict_schemas_01_to_04(schema):
    objs = list(objects(llm.responses_request("m", [], "u", schema)["text"]["format"]["schema"]))
    assert objs
    for o in objs:
        assert o["additionalProperties"] is False and set(o["required"]) == set(o["properties"])


def test_call_parses_and_logs_split_usage(use_openai, tmp_path):
    bodies = use_openai(RESP(OK))
    redact = {"Nguyễn Văn An": "HS-03"}
    out = llm.call(
        "02", ["sys"], grader.GradeOut, extra=["đề của Nguyễn Văn An"], context=llm.CallContext(None, redact=redact)
    )
    assert out == grader.GradeOut(items=[], score=0)
    assert bodies[0]["model"] == "gpt-5.6-sol" and bodies[0]["store"] is False
    assert "Văn An" not in json.dumps(bodies, ensure_ascii=False)
    (row,) = rows(tmp_path)
    assert row["model"] == MODEL and row["result"] == "ok"
    assert (row["input_tokens"], row["cache_read_tokens"], row["cache_write_tokens"], row["output_tokens"]) == (
        3,
        1874,
        19,
        6,
    )


def test_bad_json_is_schema_error(use_openai, tmp_path):
    use_openai(RESP("not json"), RESP("not json"))
    with pytest.raises(llm.SchemaFlag):
        grade()
    a, b = rows(tmp_path)
    assert a["result"] == b["result"] == "schema_error" and a["output"] == "not json"
    assert a["input_tokens"] > 0 and a["output_tokens"] > 0


def test_refusal_is_unavailable(use_openai):
    bodies = use_openai(RESP("", content=[{"type": "refusal", "refusal": "no"}]))
    with pytest.raises(llm.LLMUnavailable, match="từ chối"):
        grade()
    assert len(bodies) == 1


def test_content_filter_is_unavailable(use_openai):
    bodies = use_openai(RESP("", status="incomplete", reason="content_filter"))
    with pytest.raises(llm.LLMUnavailable, match="từ chối"):
        grade()
    assert len(bodies) == 1


def test_retry_then_ok(use_openai, tmp_path):
    bodies = use_openai(429, 500, RESP(OK))
    assert grade().score == 0
    assert len(bodies) == 3 and [r["result"] for r in rows(tmp_path)] == ["retry", "retry", "ok"]


def test_bad_request_is_not_retried(use_openai, tmp_path):
    bodies = use_openai(400)
    with pytest.raises(openai.BadRequestError):
        grade()
    assert len(bodies) == 1 and [r["result"] for r in rows(tmp_path)] == ["error"]


def test_openai_retryable():
    def status(cls, code, body=None):
        return cls("x", response=httpx2.Response(code, request=REQ), body=body)

    yes = [
        status(openai.RateLimitError, 429),
        status(openai.InternalServerError, 500),
        status(openai.InternalServerError, 503),
        status(openai.APIStatusError, 408),
        status(openai.APIStatusError, 409),
        openai.APIConnectionError(request=REQ),
        openai.APITimeoutError(REQ),
        httpx2.ReadError("x"),
        openai.APIError("x", REQ, body={"code": "server_error"}),
    ]
    no = [
        status(openai.BadRequestError, 400),
        status(openai.AuthenticationError, 401),
        status(openai.NotFoundError, 404),
        openai.APIError("x", REQ, body={"code": "invalid_prompt"}),
        ValueError("x"),
    ]
    assert all(llm._openai_retryable(e) for e in yes)
    assert not any(llm._openai_retryable(e) for e in no)


def test_missing_key_is_unavailable(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(llm.LLMUnavailable, match="OPENAI_API_KEY"):
        llm.OpenAIBackend()


def test_missing_key_on_call_marks_health_error(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(llm, "_live", {})
    llm.set_backend(None)
    llm.configure(tmp_path / "llm.jsonl", {"02": MODEL})
    with pytest.raises(llm.LLMUnavailable, match="Thiếu OPENAI_API_KEY"):
        grade()
    assert llm.status() == "error"


def test_call_failed_server_error_is_retried(use_openai, tmp_path):
    failed = RESP("") | {"status": "failed", "error": {"code": "server_error", "message": "x"}, "output": []}
    bodies = use_openai(failed, RESP(OK))
    assert grade().score == 0
    assert len(bodies) == 2 and [r["result"] for r in rows(tmp_path)] == ["retry", "ok"]


def test_key_fragment_scrubbed_from_errors(use_openai, tmp_path):
    echo = "Incorrect API key provided: sk-proj-ab**********wxyz. You can find your API key at https://x."
    use_openai(httpx2.Response(401, json={"error": {"message": echo, "type": "x", "code": "invalid_api_key"}}))
    with pytest.raises(openai.AuthenticationError) as e:
        grade()
    shown = "".join(traceback.format_exception(e.value))  # what log.exception writes to app.log
    log = (tmp_path / "llm.jsonl").read_text(encoding="utf-8")
    assert "Incorrect API key" in shown and "Incorrect API key" in log
    assert not any(s in t for s in ("wxyz", "sk-proj") for t in (shown, log))


# --- chat: streaming tool loop (Task 4) ---

TOOLS = [{"name": "student_profile", "description": "Hồ sơ", "input_schema": {"type": "object"}}]
ASK = [{"role": "user", "content": "HS-01 dạo này thế nào?"}]


def delta(t):
    return {"type": "response.output_text.delta", "delta": t, "item_id": "m1", "output_index": 0, "content_index": 0}


def final(output, status="completed", reason=None, code="server_error"):
    r = {"id": "r1", "status": status, "incomplete_details": {"reason": reason} if reason else None, "usage": U}
    if status == "failed":
        r["error"] = {"code": code, "message": "x"}
    return {"type": f"response.{status}", "response": r | {"output": output}}


def rs(enc):
    return {"type": "reasoning", "id": "rs_1", "summary": [], "encrypted_content": enc}


def msg(text, phase):
    part = {"type": "output_text", "text": text, "annotations": []}
    return {"type": "message", "id": "m1", "role": "assistant", "status": "completed", "phase": phase,
            "content": [part]}  # fmt: skip


def fc(call_id, name, args):
    return {"type": "function_call", "id": "fc_1", "call_id": call_id, "name": name, "arguments": args,
            "status": "completed"}  # fmt: skip


def ctx(redact=None):
    return llm.CallContext(graph=None, conversation_id="c1", redact=redact or {})


def chat(messages=ASK, run_tool=lambda name, inp: ("kết quả", False), fixed=("cố định",), redact=None, out=None):
    events = out if out is not None else []
    tools = tool_defs(["notational.operator_swap"])
    for ev in llm.chat("00", list(fixed), tools, messages, run_tool=run_tool, context=ctx(redact), max_tool_turns=8):
        events.append(ev)
    return events


def fold(s):
    return "".join(llm._fold(c) for c in s)


def test_openai_tools_strict():
    defs = tool_defs(["a.b"])
    out = llm.openai_tools(defs)
    assert [t["name"] for t in out] == [d["name"] for d in defs] and len(out) == 10
    assert all(t["type"] == "function" and t["strict"] is True for t in out)
    for t in out:
        for o in objects(t["parameters"]):
            assert set(o["required"]) == set(o["properties"]) and o["additionalProperties"] is False
    p = {t["name"]: t["parameters"]["properties"] for t in out}
    assert p["student_profile"]["code"]["type"] == "string"
    assert p["search_problems"]["kc"]["type"] == ["integer", "null"]
    assert p["search_problems"]["level_min"]["enum"][-1] is None
    assert p["student_mistakes"]["kind"]["enum"] == ["a.b", None]
    assert p["rank_problems"]["ratios"]["type"] == ["object", "null"]
    assert p["rank_problems"]["ratios"]["required"] == ["review", "zpd", "challenge"]
    assert defs == tool_defs(["a.b"])  # the shared definitions are not changed in place


def test_chat_request_shape():
    r = llm.responses_chat_request("gpt-5.6-sol", ["a", "b"], TOOLS, ASK)
    assert r["store"] is False and r["stream"] is True and r["instructions"] == "a\n\nb"
    assert r["max_output_tokens"] == 64000 and r["reasoning"] == {"effort": "medium"}
    assert r["tools"][0]["type"] == "function" and r["input"] == ASK
    assert "include" not in r and "previous_response_id" not in r
    said = {"role": "assistant", "content": "ok"}
    assert llm.openai_input([*ASK, said])[-1] == said | {"phase": "final_answer"}


def test_text_tool_then_answer(use_openai, tmp_path):
    call = fc("call_1", "student_profile", '{"code":"HS-01","since":null}')
    bodies = use_openai(
        [delta("Để mình "), delta("tra."), final([rs("xyz"), msg("Để mình tra.", "commentary"), call])],
        [delta("HS-01 có 2 buổi."), final([msg("HS-01 có 2 buổi.", "final_answer")])],
        models={"00": MODEL},
    )
    ran = []
    events = chat(run_tool=lambda name, inp: ran.append((name, inp)) or ('{"sessions":2}', False))
    assert ran == [("student_profile", {"code": "HS-01"})]
    start = next(e for e in events if e["type"] == "tool")
    assert start["input"] == {"code": "HS-01"}
    assert bodies[1]["input"] == [
        ASK[0],
        rs("xyz"),
        msg("Để mình tra.", "commentary"),
        call,
        {"type": "function_call_output", "call_id": "call_1", "output": '{"sessions":2}'},
    ]
    assert len(bodies) == 2 and all(b["store"] is False for b in bodies)
    assert events[-1] == {"type": "end", "text": "Để mình tra.\n\nHS-01 có 2 buổi.", "stopped": None}
    a, b = rows(tmp_path)
    assert a["model"] == b["model"] == MODEL and (a["tools"], b["tools"]) == (["student_profile"], [])
    assert a["output"][1]["input"] == {"code": "HS-01"}  # no null in the logged tool_use (Review Focus 3)
    log = (tmp_path / "llm.jsonl").read_text(encoding="utf-8")
    assert "xyz" not in log and "openai_item" not in log


def test_masks_before_translation(use_openai):
    redact = {"Nguyễn Văn An": "HS-01"}
    call = fc("call_1", "student_profile", '{"code":"HS-01"}')
    bodies = use_openai([final([call])], [delta("Xong."), final([msg("Xong.", "final_answer")])], models={"00": MODEL})
    chat(
        [{"role": "user", "content": "Nguyễn Văn An yếu gì?"}],
        run_tool=lambda name, inp: ('{"name":"nguyen van an"}', False),
        fixed=["Thầy dạy Nguyễn Văn An"],
        redact=redact,
    )
    sent = fold(json.dumps(bodies, ensure_ascii=False))
    assert "van an" not in sent and "hs-01" in sent
    assert "hs-01" in fold(bodies[0]["instructions"]) and "hs-01" in fold(bodies[1]["input"][-1]["output"])


def test_incomplete_max_tokens(use_openai):
    use_openai(
        [delta("Tháng"), final([msg("Tháng", "final_answer")], status="incomplete", reason="max_output_tokens")],
        models={"00": MODEL},
    )
    assert chat()[-1] == {"type": "end", "text": "Tháng", "stopped": "max_tokens"}


def test_retry_before_first_delta(use_openai, tmp_path):
    bodies = use_openai(
        429, [final([], status="failed")], [delta("Xong."), final([msg("Xong.", "final_answer")])], models={"00": MODEL}
    )
    assert chat()[-1]["text"] == "Xong."
    assert len(bodies) == 3 and [r["result"] for r in rows(tmp_path)] == ["retry", "retry", "ok"]


def test_no_retry_after_delta(use_openai):
    for reply in ([delta("Tháng này"), {"type": "error", "code": "server_error", "message": "x"}], [delta("A")]):
        bodies = use_openai(reply, models={"00": MODEL})
        got = []
        with pytest.raises(llm.LLMUnavailable):
            chat(out=got)
        assert got == [{"type": "text", "delta": reply[0]["delta"]}] and len(bodies) == 1


def test_failed_other_code_not_retried(use_openai):
    bodies = use_openai([final([], status="failed", code="invalid_prompt")], models={"00": MODEL})
    with pytest.raises(llm.LLMUnavailable, match="invalid_prompt"):
        chat()
    assert len(bodies) == 1


def test_chat_refusal(use_openai):
    refused = {"type": "message", "id": "m1", "role": "assistant", "status": "completed",
               "content": [{"type": "refusal", "refusal": "no"}]}  # fmt: skip
    bodies = use_openai([final([refused])], models={"00": MODEL})
    with pytest.raises(llm.LLMUnavailable, match="từ chối"):
        chat()
    assert len(bodies) == 1
