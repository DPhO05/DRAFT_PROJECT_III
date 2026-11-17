"""GuardedOpenAI: structured call and stream on the Responses API, over a mock transport (C-34)."""

import asyncio
import json
import threading
import time
import traceback

import httpx2
import openai
import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

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
        llm.set_backend(None)
        llm.configure(tmp_path / "llm.jsonl", models or {"02": MODEL})
        shared = dict(  # what llm.model builds, over the mock client; `call` reads it from _chat
            api_key="test", use_responses_api=True, store=False, max_retries=0,
            root_client=client, client=client.chat.completions,
        )  # fmt: skip
        monkeypatch.setattr(
            llm,
            "_chat",
            {m: llm.GuardedOpenAI(model=m.split(":")[1], **shared) for m in (models or {"02": MODEL}).values()},
        )
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


@pytest.mark.parametrize(
    "schema",
    [ingest.MatchResult, grader.GradeOut, grader.RubricDraftOut, diagnoser.DiagnosisOut, verifier.VerdictOut],
)
def test_strict_schemas_01_to_04(schema):
    objs = list(objects(llm._Schema(schema)["schema"]))
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
    with pytest.raises(llm.LLMUnavailable, match="models trong settings"):
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
        json.JSONDecodeError("Expecting value", "", 0),
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


def test_missing_key_on_call_marks_health_error(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(llm, "_chat", {})
    llm.set_backend(None)
    llm.configure(tmp_path / "llm.jsonl", {"02": MODEL})
    with pytest.raises(llm.KeyRejected, match="Thiếu OPENAI_API_KEY"):
        grade()
    assert llm.status() == "error"


def test_call_failed_server_error_is_retried(use_openai, tmp_path):
    failed = RESP("") | {"status": "failed", "error": {"code": "server_error", "message": "x"}, "output": []}
    bodies = use_openai(failed, RESP(OK))
    assert grade().score == 0
    assert len(bodies) == 2 and [r["result"] for r in rows(tmp_path)] == ["retry", "ok"]


def test_empty_body_is_retried(use_openai, tmp_path):
    empty = httpx2.Response(200, content=b"", headers={"content-type": "application/json"})
    bodies = use_openai(empty, RESP(OK))
    assert grade().score == 0
    assert len(bodies) == 2 and [r["result"] for r in rows(tmp_path)] == ["retry", "ok"]


@pytest.mark.parametrize(
    ("code", "err"),
    [(401, "invalid_api_key"), (403, "unsupported_country_region_territory"), (429, "insufficient_quota")],
)
def test_refused_key_is_not_retried(use_openai, tmp_path, code, err):
    body = {"error": {"message": "x", "type": "x", "code": err}}
    bodies = use_openai(httpx2.Response(code, json=body))
    with pytest.raises(llm.KeyRejected, match="Khoá API bị từ chối"):
        grade()
    assert len(bodies) == 1 and [r["result"] for r in rows(tmp_path)] == ["error"]


def test_key_fragment_scrubbed_from_errors(use_openai, tmp_path):
    echo = "Incorrect API key provided: sk-proj-ab**********wxyz. You can find your API key at https://x."
    use_openai(httpx2.Response(401, json={"error": {"message": echo, "type": "x", "code": "invalid_api_key"}}))
    with pytest.raises(llm.KeyRejected) as e:
        grade()
    shown = "".join(traceback.format_exception(e.value))  # what log.exception writes to app.log
    log = (tmp_path / "llm.jsonl").read_text(encoding="utf-8")
    assert "Incorrect API key" in shown and "Incorrect API key" in log
    assert not any(s in t for s in ("wxyz", "sk-proj") for t in (shown, log))


# tool schemas as `lc_tools` hands them to the model (strict mode, R9, S7)


def test_tool_schemas_are_strict():
    defs = tool_defs(["a.b"])
    out = {d["name"]: llm._strict(d["input_schema"]) for d in defs}
    assert len(out) == 11
    for s in out.values():
        for o in objects(s):
            assert set(o["required"]) == set(o["properties"]) and o["additionalProperties"] is False
    p = {n: s["properties"] for n, s in out.items()}
    assert p["student_profile"]["code"]["type"] == "string"
    assert p["search_problems"]["kc"]["type"] == ["integer", "null"]
    assert p["search_problems"]["level_min"]["enum"][-1] is None
    assert p["student_mistakes"]["kind"]["enum"] == ["a.b", None]
    assert p["rank_problems"]["ratios"]["type"] == ["object", "null"]
    assert p["rank_problems"]["ratios"]["required"] == ["review", "zpd", "challenge"]
    assert defs == tool_defs(["a.b"])  # the shared definitions are not changed in place


# GuardedOpenAI: ChatOpenAI under the guard, over the same mock transport

NAME, CODE = "Nguyễn Văn An", "HS-01"
GCTX = llm.CallContext(graph="g", thread_id="t", student_code=CODE, redact={NAME: CODE})
GBASE = {"agent": "02", "prompt_version": "p", "model": MODEL, "user": "u"}


@pytest.fixture
def glog(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "_log_path", tmp_path / "llm.jsonl")

    def rows():
        f = tmp_path / "llm.jsonl"
        return [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines()] if f.exists() else []

    return rows


def guarded(*replies, **kw):
    oc, bodies = openai_client(*replies)
    m = llm.GuardedOpenAI(
        model="gpt-5.6-sol",
        api_key="test",
        use_responses_api=True,
        store=False,
        max_retries=0,
        root_client=oc,
        client=oc.chat.completions,
        **kw,
    )
    return m, bodies


def ask(m, text="hi", **kw):
    with llm.scope(GCTX, GBASE, **kw):
        return m.invoke([SystemMessage("Chấm."), HumanMessage(text)])


def sse_text(*deltas, tail=None):
    n = iter(range(1, 99))
    ev = lambda t, **k: {"type": t, "sequence_number": next(n), **k}  # noqa: E731
    msg0 = {"id": "m1", "type": "message", "role": "assistant", "status": "in_progress", "content": []}
    out = [
        ev("response.created", response={"id": "r", "status": "in_progress", "output": []}),
        ev("response.output_item.added", output_index=0, item=msg0),
        ev(
            "response.content_part.added",
            item_id="m1",
            output_index=0,
            content_index=0,
            part={"type": "output_text", "text": "", "annotations": []},
        ),
    ]
    out += [
        ev("response.output_text.delta", item_id="m1", output_index=0, content_index=0, delta=d, logprobs=[])
        for d in deltas
    ]
    return out + (tail(ev) if tail else [])


def sse_error(ev):
    return [ev("error", code="server_error", message="mid", param=None)]


def sse_done(ev, text="xin chao"):
    done = RESP(text)["output"][0] | {"status": "completed"}
    resp = RESP(text) | {"id": "r"}
    return [ev("response.output_item.done", output_index=0, item=done), ev("response.completed", response=resp)]


def test_guard_body_masked_store_false(glog):
    m, bodies = guarded(RESP("ok"))
    ask(m, f"Bài của {NAME}")
    text = json.dumps(bodies[0], ensure_ascii=False)
    assert bodies[0]["store"] is False and NAME not in text and CODE in text
    assert glog()[0]["name_masked"] is True


def test_guard_name_left_after_mask_sends_nothing(glog):
    m, bodies = guarded(RESP("ok"))
    ctx = llm.CallContext(graph="g", redact={"An": "học sinh An"})  # the code itself carries the name
    with llm.scope(ctx, GBASE), pytest.raises(llm.LLMUnavailable):
        m.invoke("Bài của An")
    assert bodies == []


def test_guard_outside_scope_sends_nothing():
    m, bodies = guarded(RESP("ok"))
    with pytest.raises(RuntimeError):
        m.invoke("hi")
    with pytest.raises(RuntimeError):
        asyncio.run(m.ainvoke("hi"))
    assert bodies == []


def test_guard_500_three_tries(glog):
    m, bodies = guarded(500, 500, 500)
    with pytest.raises(llm.LLMUnavailable):
        ask(m)
    assert len(bodies) == 3 and [r["result"] for r in glog()] == ["retry"] * 3
    assert all(r["output"] is None for r in glog())


def test_guard_401_key_rejected_and_scrubbed(glog):
    leak = httpx2.Response(
        401,
        json={
            "error": {"message": "Incorrect API key provided: sk-proj-abc123", "type": "x", "code": "invalid_api_key"}
        },
    )
    m, bodies = guarded(leak)
    with pytest.raises(llm.KeyRejected) as e:
        ask(m)
    assert len(bodies) == 1
    assert "sk-proj" not in str(e.value) and "sk-proj" not in json.dumps(glog()) and glog()[0]["result"] == "error"


@pytest.mark.parametrize("status", [400, 404])
def test_guard_bad_request_one_try(status, glog):
    m, bodies = guarded(status)
    with pytest.raises(
        llm.LLMUnavailable, match="Tên model hoặc yêu cầu không hợp lệ, xem mục models trong settings.json"
    ):
        ask(m)
    assert len(bodies) == 1


def test_guard_row_fields_and_usage(glog):
    m, _ = guarded(RESP(OK))
    ask(m)
    (row,) = glog()
    assert row["agent"] == "02" and row["result"] == "ok" and row["output"] == OK
    assert (row["input_tokens"], row["cache_read_tokens"], row["cache_write_tokens"]) == (3, 1874, 19)
    assert llm.status() == "ok"


def test_guard_schema_check(glog):
    m, _ = guarded(RESP("nope"))
    ask(m, check=lambda raw: False)
    assert glog()[0]["result"] == "schema_error"


def test_guard_stream_error_after_text_no_retry(glog):
    m, bodies = guarded(sse_text("Xin ", "chao", tail=sse_error))
    got = []
    with llm.scope(GCTX, GBASE), pytest.raises(llm.LLMUnavailable):
        for c in m.stream("hi"):
            got.append(c.text)
    assert "".join(got) == "Xin chao" and len(bodies) == 1
    assert [r["result"] for r in glog()] == ["error"]


def test_guard_stream_error_before_text_retries(glog):
    m, bodies = guarded(sse_text(tail=sse_error), sse_text("xin chao", tail=sse_done))
    with llm.scope(GCTX, GBASE):
        text = "".join(c.text for c in m.stream("hi"))
    assert text == "xin chao" and len(bodies) == 2
    assert [r["result"] for r in glog()] == ["retry", "ok"]


def test_guard_stream_refusal_is_unavailable(glog):
    refused = {"id": "m1", "type": "message", "role": "assistant", "status": "completed",
               "content": [{"type": "refusal", "refusal": "no"}]}  # fmt: skip

    def tail(ev):
        resp = {"id": "r", "status": "completed", "output": [refused], "usage": U}
        done = ev("response.refusal.done", item_id="m1", output_index=0, content_index=0, refusal="no")
        item_done = ev("response.output_item.done", output_index=0, item=refused)
        return [done, item_done, ev("response.completed", response=resp)]

    m, bodies = guarded(sse_text(tail=tail))
    with llm.scope(GCTX, GBASE), pytest.raises(llm.LLMUnavailable, match="từ chối"):
        list(m.stream("hi"))
    assert len(bodies) == 1


def test_guard_reasoning_item_goes_back_after_tool_call(glog):
    rs = {"type": "reasoning", "id": "rs_1", "summary": [], "encrypted_content": "xyz"}
    call = {"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "f", "arguments": '{"a": 1}',
            "status": "completed"}  # fmt: skip
    m, bodies = guarded(RESP("") | {"output": [rs, call]}, RESP("xong"))
    with llm.scope(GCTX, GBASE):
        first = m.invoke([HumanMessage("hi")])
        m.invoke([HumanMessage("hi"), first, ToolMessage("kq", tool_call_id="call_1")])
    sent = bodies[1]["input"]
    assert first.tool_calls[0]["args"] == {"a": 1}
    assert any(i.get("type") == "reasoning" and i.get("encrypted_content") == "xyz" for i in sent)
    assert {"type": "function_call_output", "call_id": "call_1", "output": "kq"} in sent


def test_guard_incomplete_drops_tool_calls():
    call = {
        "id": "fc1",
        "type": "function_call",
        "call_id": "c1",
        "name": "t",
        "arguments": '{"code": "HS-0',
        "status": "incomplete",
    }
    r = {
        "id": "r",
        "status": "incomplete",
        "incomplete_details": {"reason": "max_output_tokens"},
        "output": [call],
        "usage": U,
    }
    m, _ = guarded(r)
    ai = ask(m)
    assert ai.tool_calls == [] and ai.invalid_tool_calls == []
    assert not any(isinstance(b, dict) and b.get("type") == "function_call" for b in ai.content)


def test_guard_incomplete_stream_drops_tool_calls():
    call = {
        "id": "fc1",
        "type": "function_call",
        "call_id": "c1",
        "name": "t",
        "arguments": "",
        "status": "in_progress",
    }

    def tail(ev):
        cut = call | {"arguments": '{"code": "HS-0', "status": "incomplete"}
        r = {
            "id": "r",
            "status": "incomplete",
            "incomplete_details": {"reason": "max_output_tokens"},
            "output": [cut],
            "usage": U,
        }
        return [
            ev("response.output_item.added", output_index=1, item=call),
            ev("response.function_call_arguments.delta", item_id="fc1", output_index=1, delta='{"code": "HS-0'),
            ev("response.incomplete", response=r),
        ]

    m, _ = guarded(sse_text("xin", tail=tail))
    with llm.scope(GCTX, GBASE):
        agg = None
        for c in m.stream("hi"):
            agg = c if agg is None else agg + c
    assert agg.text == "xin" and agg.tool_calls == [] and agg.tool_call_chunks == []


def test_guard_stop_flag_stops_before_next_chunk_and_closes_stream(glog):
    state = {"closed": False}

    class Tracked(httpx2.SyncByteStream):
        def __iter__(self):
            for p in sse_text("a ", "b ", "c ", "d "):
                yield f"event: {p['type']}\ndata: {json.dumps(p)}\n\n".encode()

        def close(self):
            state["closed"] = True

    resp = httpx2.Response(200, headers={"content-type": "text/event-stream"}, stream=Tracked())
    m, _ = guarded(resp)
    flag, got = threading.Event(), []
    with llm.scope(GCTX, GBASE, stop=flag), pytest.raises(llm.LLMUnavailable, match="Đã dừng"):
        for c in m.stream("hi"):
            got.append(c.text)
            if c.text == "a ":
                flag.set()
    assert got.count("a ") == 1 and "b " not in got and state["closed"]
    assert glog()[0]["result"] == "error"


def test_model_openai_cached_and_use_key_drops_it(monkeypatch):
    llm.set_backend(None)
    monkeypatch.setattr(llm, "_models", {"02": MODEL})
    monkeypatch.setattr(llm, "_chat", {})
    with pytest.raises(llm.LLMUnavailable, match="OPENAI_API_KEY"):
        llm.model("02")
    llm.use_key("openai", "sk-test")
    a = llm.model("02")
    assert isinstance(a, llm.GuardedOpenAI) and llm.model("02") is a
    assert a.store is False and a.max_retries == 0 and a.use_responses_api is True
    assert a.reasoning == {"effort": "medium"}
    assert a._get_request_payload([HumanMessage("x")])["max_output_tokens"] == 32000
    llm.use_key("openai", "sk-other")
    assert llm.model("02") is not a


def _fn_args(who):
    return json.dumps({"who": who}, ensure_ascii=False)


LEAKS = {
    "tool_calls": lambda: [
        HumanMessage("x"),
        AIMessage("", tool_calls=[{"id": "c1", "name": "t", "args": {"who": NAME}}]),
        ToolMessage("done", tool_call_id="c1"),
    ],
    "invalid_tool_calls": lambda: [
        HumanMessage("x"),
        AIMessage(
            "",
            invalid_tool_calls=[
                {"id": "c1", "name": "t", "args": '{"who": "' + NAME, "error": None, "type": "invalid_tool_call"}
            ],
        ),
        ToolMessage("done", tool_call_id="c1"),
    ],
    "additional_kwargs": lambda: [
        HumanMessage("x"),
        AIMessage(
            "",
            additional_kwargs={
                "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "t", "arguments": _fn_args(NAME)}}]
            },
        ),
        ToolMessage("done", tool_call_id="c1"),
    ],
    "content_blocks": lambda: [HumanMessage([{"type": "text", "text": f"Bài của {NAME}"}])],
    "tool_message": lambda: [
        HumanMessage("x"),
        AIMessage("", tool_calls=[{"id": "c1", "name": "t", "args": {}}]),
        ToolMessage(f"học sinh {NAME}", tool_call_id="c1"),
    ],
    "name_field": lambda: [HumanMessage("x", name=NAME)],
    "ai_text": lambda: [HumanMessage("x"), AIMessage(f"Chào {NAME}"), HumanMessage("y")],
    "function_call_block": lambda: [
        HumanMessage("x"),
        AIMessage(
            [{"type": "function_call", "call_id": "c1", "id": "fc1", "name": "t", "arguments": _fn_args(NAME)}],
            tool_calls=[{"id": "c1", "name": "t", "args": {}}],
        ),
        ToolMessage("done", tool_call_id="c1"),
    ],
}


@pytest.mark.parametrize("shape", LEAKS)
def test_guard_no_name_reaches_the_body(shape, glog):
    m, bodies = guarded(RESP("ok"))
    with llm.scope(GCTX, GBASE):
        try:
            m.invoke(LEAKS[shape]())
        except llm.LLMUnavailable:
            pass  # refusing to send is also clean
    assert NAME not in json.dumps(bodies, ensure_ascii=False)


def test_guard_stop_flag_while_chunks_are_held(glog):
    flag, read = threading.Event(), {"after": 0, "closed": False}
    call = {
        "id": "fc1",
        "type": "function_call",
        "call_id": "c1",
        "name": "t",
        "arguments": "",
        "status": "in_progress",
    }

    def tail(ev):
        return [ev("response.output_item.added", output_index=1, item=call)] + [
            ev("response.function_call_arguments.delta", item_id="fc1", output_index=1, delta="x") for _ in range(30)
        ]

    events = sse_text(tail=tail)

    class Tracked(httpx2.SyncByteStream):
        def __iter__(self):
            for i, p in enumerate(events):
                if i == 3:
                    flag.set()
                read["after"] += flag.is_set()
                yield f"event: {p['type']}\ndata: {json.dumps(p)}\n\n".encode()

        def close(self):
            read["closed"] = True

    m, _ = guarded(httpx2.Response(200, headers={"content-type": "text/event-stream"}, stream=Tracked()))
    with llm.scope(GCTX, GBASE, stop=flag), pytest.raises(llm.LLMUnavailable, match="Đã dừng"):
        list(m.stream("hi"))
    assert read["after"] <= 3 and read["closed"]


def test_guard_astream_cancel_closes_stream_after_pending_chunk():
    state = {"closed": False}

    class Slow(httpx2.SyncByteStream):
        def __iter__(self):
            for p in sse_text("a ", "b ", "c "):
                time.sleep(0.2)
                yield f"event: {p['type']}\ndata: {json.dumps(p)}\n\n".encode()

        def close(self):
            state["closed"] = True

    m, _ = guarded(httpx2.Response(200, headers={"content-type": "text/event-stream"}, stream=Slow()))

    async def consume():
        with llm.scope(GCTX, GBASE):
            async for _ in m.astream("hi"):
                pass

    async def main():
        t = asyncio.create_task(consume())
        await asyncio.sleep(0.3)
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t

    asyncio.run(main())
    assert state["closed"]


def test_guard_non_transient_stream_error_is_unavailable_and_scrubbed(glog):
    def tail(ev):
        return [ev("error", code="invalid_prompt", message="bad key sk-proj-abc123", param=None)]

    m, bodies = guarded(sse_text("xin", tail=tail))
    with llm.scope(GCTX, GBASE), pytest.raises(llm.LLMUnavailable) as e:
        list(m.stream("hi"))
    assert len(bodies) == 1 and "invalid_prompt" in str(e.value)
    assert "sk-proj" not in str(e.value) and "sk-proj" not in json.dumps(glog())


# --- call over GuardedOpenAI (Task 1.3) ---


def test_call_sends_masked_strict_body_and_returns_model(use_openai, tmp_path):
    bodies = use_openai(RESP(OK))
    redact = {"Nguyễn Văn An": "HS-03"}
    out = llm.call(
        "02", ["HS Nguyễn Văn An"], grader.GradeOut, student_work="bài", context=llm.CallContext(None, redact=redact)
    )
    assert isinstance(out, grader.GradeOut)
    fmt = bodies[0]["text"]["format"]
    assert fmt["type"] == "json_schema" and fmt["strict"] is True and fmt["name"] == "GradeOut"
    assert "Văn An" not in json.dumps(bodies, ensure_ascii=False) and "HS-03" in json.dumps(bodies)


def test_call_schema_error_once_then_ok(use_openai, tmp_path):
    bodies = use_openai(RESP("not json"), RESP(OK))
    assert grade().score == 0
    a, b = rows(tmp_path)
    assert len(bodies) == 2 and (a["result"], b["result"]) == ("schema_error", "ok")
    assert a["output"] == "not json" and a["output_tokens"] == 6


def test_call_name_in_fixed_extra_and_work_never_in_body(use_openai):
    bodies = use_openai(RESP(OK))
    c = llm.CallContext(None, redact={NAME: CODE})
    llm.call("02", [f"Hồ sơ {NAME}"], grader.GradeOut, extra=[f"Đề của {NAME}"], student_work=f"{NAME} làm", context=c)
    sent = json.dumps(bodies, ensure_ascii=False)
    assert NAME not in sent and sent.count(CODE) == 3
