"""OpenAIBackend.__call__: one structured call on the Responses API, over a mock transport (C-34)."""

import json

import httpx2
import openai
import pytest

from tests.fakes import openai_client
from tutor import llm
from tutor.agents import diagnoser, grader, ingest, verifier

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
