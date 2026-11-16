"""P6-T09: POST /api/assistant/messages (NDJSON), conversations, pending (api-v3 §3.1-§3.3, R25, C-39)."""

import gc
import json
import logging
import threading
from contextlib import closing
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from tests.agents.test_orchestrator import text, tool
from tests.api.conftest import PORT
from tests.api.test_bank import ONE
from tests.api.test_review_api import submit
from tests.api.test_sessions import W, add_student, poll
from tests.assistant_fix import world
from tests.bankfix import P1
from tests.fakes import FakeLLM, openai_client
from tutor import llm
from tutor.agents.a00_orchestrator import chat
from tutor.agents.a00_orchestrator.tools import Outcome, Toolbox
from tutor.api import assistant
from tutor.api.app import create_app
from tutor.db import repo
from tutor.graphs import worksheet

BUSY = {"reason": "Trợ lý đang trả lời tin trước"}


@pytest.fixture
def w(paths, client):
    with closing(repo.connect(paths.tutor_db)) as conn:
        return world(conn)


def script(*turns) -> FakeLLM:
    llm.set_backend(fake := FakeLLM({"00": list(turns)}))
    return fake


def send(client, text_, mentions=(), cid=None, **body):
    msg = {"conversation_id": cid, "text": text_, "mentions": list(mentions)} | body
    return client.post("/api/assistant/messages", json=msg, headers=W)


def lines(r) -> list[dict]:
    assert r.status_code == 200, r.text
    assert r.text.endswith("\n")
    return [json.loads(x) for x in r.text.splitlines()]


def rows(paths, cid) -> list[dict]:
    return [json.loads(x) for x in (paths.logs / "chat" / f"{cid}.jsonl").read_text(encoding="utf-8").splitlines()]


def test_stream_shape(paths, client, w):
    script([tool("student_profile", code="HS-01")], [text("HS-01 còn lỗi lặp.")])
    r = send(client, "Tháng này @HS-01 yếu gì?", [w["an"]])
    assert r.headers["content-type"] == "application/x-ndjson"
    evs = lines(r)
    cid = f"{date.today().isoformat()}-1"
    assert evs[0] == {"type": "start", "conversation_id": cid, "message_id": "m2"}
    assert evs[-1] == {"type": "done", "stopped": None}
    assert [e["state"] for e in evs if e["type"] == "tool"] == ["start", "done"]
    assert all("summary" not in e for e in evs)  # S10
    user, bot = rows(paths, cid)
    assert user == {"id": "m1", "role": "user", "ts": user["ts"], "text": "Tháng này @HS-01 yếu gì?",
                    "mentions": [w["an"]], "attachment": None}  # fmt: skip
    assert (bot["id"], bot["role"], bot["text"]) == ("m2", "assistant", "HS-01 còn lỗi lặp.")
    assert [t["name"] for t in bot["tools"]] == ["student_profile"] and bot["tools"][0]["summary"]
    assert bot["events"] == [e for e in evs if e["type"] not in ("start", "text")]


def test_logs_have_no_names(paths, client, w):
    fake = script([text("Ừ.")])
    lines(send(client, "Nguyễn Văn An với lê văn cường hay sai gì?"))
    assert "HS-01 với HS-03" in sent_texts(fake.calls[0])[-1]
    for f in (paths.logs / "chat" / f"{date.today().isoformat()}-1.jsonl", paths.logs / "llm.jsonl"):
        got = "".join(llm._fold(c) for c in f.read_text(encoding="utf-8"))
        assert "nguyen van an" not in got and "le van cuong" not in got
        assert f.name == "llm.jsonl" or "hs-01" in got and "hs-03" in got  # llm.jsonl keeps no request text


def test_readonly_chat_keeps_db(paths, client, w, monkeypatch):
    with closing(repo.connect(paths.tutor_db)) as c:
        before = repo.row_counts(c)
    opened = []
    real = repo.connect
    monkeypatch.setattr(repo, "connect", lambda db, readonly=False: opened.append(readonly) or real(db, readonly))
    script([tool("student_profile", code="HS-01")], [text("Xong.")], [tool("rank_problems", code="HS-01")],
           [text("6 bài.")], [text("Chào.")])  # fmt: skip
    cid = lines(send(client, "@HS-01 yếu gì?", [w["an"]]))[0]["conversation_id"]
    lines(send(client, "Gợi ý bài cho @HS-01", [w["an"]], cid=cid))
    lines(send(client, "Cảm ơn", cid=cid))
    assert opened == [True, True, True]  # one read-only connection per message
    with closing(real(paths.tutor_db)) as c:
        assert repo.row_counts(c) == before
    assert len(rows(paths, cid)) == 6


def test_second_message_409(paths, client, w):
    started, release = threading.Event(), threading.Event()

    def slow(messages):
        started.set()
        assert release.wait(10)
        return [text("Xong.")]

    script([text("Chào.")], slow, [text("Lại.")])
    cid = lines(send(client, "Chào"))[0]["conversation_id"]
    out = {}
    first = threading.Thread(target=lambda: out.update(r=send(client, "Hỏi lâu", cid=cid)))
    first.start()
    assert started.wait(10)
    busy = send(client, "Tin thứ hai", cid=cid)
    assert busy.status_code == 409
    assert (busy.json()["error"]["code"], busy.json()["error"]["detail"]) == ("not_ready", BUSY)
    release.set()
    first.join(10)
    assert lines(out["r"])[-1] == {"type": "done", "stopped": None}
    assert lines(send(client, "Tin thứ ba", cid=cid))[-1]["type"] == "done"
    assert [r["text"] for r in rows(paths, cid) if r["role"] == "user"] == ["Chào", "Hỏi lâu", "Tin thứ ba"]


def test_busy_released_after_error(paths, client, w):
    script([text("Đang tra"), llm.LLMUnavailable("00: overloaded")], RuntimeError("boom"), [text("Được.")])
    evs = lines(send(client, "Hỏi"))
    cid = evs[0]["conversation_id"]
    assert evs[-1] == {"type": "error", "code": "llm_unavailable", "message": "Chưa trả lời được, thử lại"}
    assert "".join(e["delta"] for e in evs if e["type"] == "text") == "Đang tra"
    evs = lines(send(client, "Hỏi lại", cid=cid))
    assert (evs[-1]["type"], evs[-1]["code"]) == ("error", "internal")
    assert "RuntimeError: boom" in (paths.logs / "app.log").read_text(encoding="utf-8")
    assert lines(send(client, "Lần nữa", cid=cid))[-1] == {"type": "done", "stopped": None}
    got = rows(paths, cid)
    assert [(r["role"], r["text"]) for r in got[:2]] == [("user", "Hỏi"), ("assistant", "Đang tra")]
    assert got[1]["events"] == [{"type": "error", "code": "llm_unavailable", "message": "Chưa trả lời được, thử lại"}]
    assert [r["id"] for r in got] == ["m1", "m2", "m3", "m4", "m5", "m6"]


BAD_KEY = "Khoá API sai, hết hạn, chưa có hoặc tài khoản hết hạn mức. Mở ⚙ Cài đặt để kiểm tra khoá."


def test_refused_key_has_its_own_code(paths, client, w):
    script(llm.KeyRejected("x"), llm.LLMUnavailable("x"))
    assert lines(send(client, "Hỏi"))[-1] == {"type": "error", "code": "bad_key", "message": BAD_KEY}
    assert lines(send(client, "Hỏi lại"))[-1]["code"] == "llm_unavailable"


def test_chat_card_and_server_share_the_key_text():
    assert f"bad_key: '{BAD_KEY}'" in (Path(__file__).parents[2] / "app" / "chat.js").read_text(encoding="utf-8")


def real_llm(monkeypatch, paths, models, client=None):
    """Route agent 00 through the real llm.py, with the provider (if any) over a mock transport."""
    if client:
        monkeypatch.setitem(llm.PROVIDERS, "openai", lambda: llm.OpenAIBackend(client))
        shared = dict(api_key="test", use_responses_api=True, store=False, max_retries=0,
                      root_client=client, client=client.chat.completions)  # fmt: skip
        monkeypatch.setattr(
            llm, "_chat", {m: llm.GuardedOpenAI(model=m.split(":")[1], **shared) for m in models.values()}
        )  # what llm.model builds, over the mock client
    monkeypatch.setattr(llm, "_live", {})
    llm.set_backend(None)
    llm.configure(paths.logs / "llm.jsonl", models)


def test_bad_model_setting_reaches_health_and_log(paths, client, w, caplog, monkeypatch):
    real_llm(monkeypatch, paths, {"00": "gpt:x"})
    monkeypatch.setattr(llm, "_last_result", "ok")
    caplog.set_level(logging.WARNING, logger="tutor")
    assert lines(send(client, "Hỏi"))[-1]["code"] == "llm_unavailable"
    assert client.get("/api/health").json()["llm"] == "error"
    assert "models.00: không biết provider gpt" in caplog.text


def test_unavailable_is_logged_without_key(paths, client, w, caplog, monkeypatch):
    echo = "Incorrect API key provided: sk-proj-abcd1234wxyz."
    oc, _ = openai_client([{"type": "error", "code": "invalid_prompt", "message": echo}])
    real_llm(monkeypatch, paths, {"00": "openai:gpt-x"}, oc)
    caplog.set_level(logging.WARNING, logger="tutor")
    assert lines(send(client, "Hỏi"))[-1]["code"] == "llm_unavailable"
    assert "Incorrect API key" in caplog.text
    assert not any(s in caplog.text for s in ("sk-proj", "wxyz"))


def test_unread_stream_frees_conversation(paths, client, w):
    """The browser may leave before the first line is read; the stream's `finally` must still run."""
    script([text("A.")], [text("B.")])
    cid = lines(send(client, "Chào"))[0]["conversation_id"]
    resp = assistant.message(assistant.Message(conversation_id=cid, text="Bỏ đi"), SimpleNamespace(app=client.app))
    del resp
    assert lines(send(client, "Lại", cid=cid))[-1] == {"type": "done", "stopped": None}
    assert [(r["role"], r["text"]) for r in rows(paths, cid)][2:] == [
        ("user", "Bỏ đi"),
        ("assistant", ""),
        ("user", "Lại"),
        ("assistant", "B."),
    ]


def test_validation(paths, client, w):
    fake = script()

    def code(r, status):
        assert r.status_code == status, r.text
        return r.json()["error"]["code"]

    assert code(send(client, " "), 422) == "validation_error"
    assert code(send(client, "@HS-02 sao rồi?", [w["an"]]), 422) == "validation_error"
    assert code(send(client, "@HS-03 sao rồi?", [w["cuong"]]), 422) == "validation_error"
    assert code(send(client, "Chào", [99]), 422) == "validation_error"
    assert code(send(client, "Chào", held_on="2026-13-40"), 422) == "validation_error"
    assert code(send(client, "Chào", cid="2026-01-01-9"), 404) == "not_found"
    assert code(send(client, "Chào", cid="../x"), 404) == "not_found"
    assert fake.calls == [] and not list((paths.logs / "chat").glob("*"))
    evs = lines(send(client, "", attachment={"path": "hs01-2026-10-21.tex"}))
    assert evs[1]["card"]["kind"] == "ask_grading" and fake.calls == []


def test_conversations_list_and_get(paths, client, w):
    script([text("A.")], [text("B.")], [text("C.")])
    c1 = lines(send(client, "Nguyễn Văn An dạo này thế nào?"))[0]["conversation_id"]
    lines(send(client, "Tiếp nhé", cid=c1))
    c2 = lines(send(client, "Câu khác"))[0]["conversation_id"]
    got = client.get("/api/assistant/conversations").json()
    day = date.today().isoformat()
    assert [(c["id"], c["title"], c["date"], c["n_messages"]) for c in got] == [
        (c2, "Câu khác", day, 2),
        (c1, "HS-01 dạo này thế nào?", day, 4),
    ]
    assert got[0]["updated_at"] == rows(paths, c2)[-1]["ts"]
    assert [c["id"] for c in client.get("/api/assistant/conversations?limit=1").json()] == [c2]
    one = client.get(f"/api/assistant/conversations/{c1}").json()
    assert one["id"] == c1
    assert [m["text"] for m in one["messages"]] == ["HS-01 dạo này thế nào?", "A.", "Tiếp nhé", "B."]
    assert all("tools" not in m for m in one["messages"])  # tool summaries stay in the log (S10)
    for bad in ("../x", "..%2Fx", "x", f"{day}-9"):
        assert client.get(f"/api/assistant/conversations/{bad}").status_code == 404


def test_pending_counts(paths, client):
    sid = add_student(client)
    g1, _, t = submit(client, sid)
    assert t["node"] == "gate_review"
    r = client.app.state.runner
    g4 = worksheet.propose(paths, r, student_id=sid, for_date="2026-10-24", items=[{"ref": P1[0]}])["thread_id"]
    (paths.inbox / "bank" / "one.tex").write_text(ONE, encoding="utf-8")
    g2 = client.post("/api/bank/imports", json={"file": "one.tex"}, headers=W).json()["thread_id"]
    assert poll(client, g2)["status"] == "awaiting_review"
    got = client.get("/api/assistant/pending").json()
    assert got["counts"] == {"assistant": 2, "reports": 0}
    assert {i["thread_id"]: (i["kind"], i["words"]) for i in got["items"]} == {
        g1: ("grading", "1 lỗi cần xem"),
        g4: ("worksheet", "1 bài"),
        g2: ("bank_import", "1 bài cần chọn kỹ năng"),
    }


def test_no_route_to_commit(client):
    spec = client.get("/api/openapi.json").json()["paths"]
    got = {(m.upper(), p) for p, ops in spec.items() if p.startswith("/api/assistant") for m in ops}
    assert got == {
        ("POST", "/api/assistant/messages"),
        ("GET", "/api/assistant/conversations"),
        ("GET", "/api/assistant/conversations/{conversation_id}"),
        ("GET", "/api/assistant/pending"),
    }


def test_broken_log_line_is_skipped(paths, client, w):
    """A crash or full disk mid-append leaves a partial line (even mid-character); the conversation stays usable."""
    script([text("A.")], [text("B.")])
    cid = lines(send(client, "Chào"))[0]["conversation_id"]
    with (paths.logs / "chat" / f"{cid}.jsonl").open("ab") as f:
        f.write('{"id": "m3", "role": "user", "text": "Chà'.encode()[:-1] + b"\n")
    listed, one = client.get("/api/assistant/conversations"), client.get(f"/api/assistant/conversations/{cid}")
    assert (listed.status_code, one.status_code) == (200, 200)
    assert [(c["id"], c["n_messages"]) for c in listed.json()] == [(cid, 2)]
    assert [m["text"] for m in one.json()["messages"]] == ["Chào", "A."]
    assert lines(send(client, "Tiếp", cid=cid))[-1] == {"type": "done", "stopped": None}


def test_chat_locks_are_reentrant():
    """A stream the browser dropped is closed by GC, possibly inside a section that holds the same lock."""
    for lock in (assistant._lock, llm._log_lock):
        with lock:
            assert lock.acquire(timeout=1)
            lock.release()


def chat_db_bytes(paths) -> bytes:
    return b"".join(f.read_bytes() for f in sorted(paths.root.glob("chat.db*")))


def sent_blocks(call, kind) -> list[dict]:
    return [b for m in call["messages"] if isinstance(m["content"], list) for b in m["content"] if b["type"] == kind]


def sent_texts(call) -> list[str]:
    return [m["content"] if isinstance(m["content"], str) else "".join(b.get("text", "") for b in m["content"])
            for m in call["messages"]]  # fmt: skip


def test_chat_db_stays_small(paths, client, w, monkeypatch):
    """K28: every turn keeps only the newest checkpoint; 30 tool turns of 6000 chars stay under 1 MB."""
    monkeypatch.setattr(Toolbox, "run", lambda self, name, args: Outcome("x" * 6000, summary="s"))

    def auto(messages):
        last = messages[-1]["content"]
        done = isinstance(last, list) and last[-1]["type"] == "tool_result"
        return [text("Xong.")] if done else [tool("student_profile", code="HS-01")]

    llm.set_backend(FakeLLM({"00": auto}))
    cid = None
    for i in range(30):
        cid = lines(send(client, f"Tin {i}", cid=cid))[0]["conversation_id"]
    assert sum(f.stat().st_size for f in paths.root.glob("chat.db*")) < 1_000_000
    assert lines(send(client, "Tin 31", cid=cid))[-1] == {"type": "done", "stopped": None}


def test_thread_survives_a_new_app(paths, app, w):
    fake = script([tool("student_profile", code="HS-01")], [text("Một.")], [text("Hai.")])
    base = f"http://127.0.0.1:{PORT}"
    with TestClient(app, base_url=base) as c:
        cid = lines(send(c, "@HS-01 thế nào?", [w["an"]]))[0]["conversation_id"]
    with TestClient(create_app(paths, port=PORT), base_url=base) as c:
        lines(send(c, "Tiếp nhé", cid=cid))
    assert sent_blocks(fake.calls[2], "tool_result")  # the tool context of message 1, not just its words


@pytest.mark.parametrize("first_ok", [False, True])
def test_failed_turn_leaves_no_dangling_call(paths, client, w, first_ok):
    """K12/K13: the turn after a failed one starts from the checkpoint before it."""
    first = [[text("Chào.")]] if first_ok else []
    fake = script(*first, [tool("student_profile", code="HS-01")], llm.LLMUnavailable("00: overloaded"),
                  [text("Được.")])  # fmt: skip
    cid = lines(send(client, "Chào"))[0]["conversation_id"] if first_ok else None
    evs = lines(send(client, "Hỏi gì đó", cid=cid))
    cid = evs[0]["conversation_id"]
    assert evs[-1]["type"] == "error"
    assert lines(send(client, "Hỏi lại", cid=cid))[-1] == {"type": "done", "stopped": None}
    last = fake.calls[-1]
    assert {b["id"] for b in sent_blocks(last, "tool_use")} == {
        b["tool_use_id"] for b in sent_blocks(last, "tool_result")
    }
    assert not any("Hỏi gì đó" in t for t in sent_texts(last))  # the failed message left the context
    assert [r.get("incomplete") for r in rows(paths, cid) if r["role"] == "assistant"] == [
        *([None] if first_ok else []), True, None,
    ]  # fmt: skip


def test_closed_after_a_tool_call_leaves_no_dangling_call(paths, client, w, monkeypatch):
    """K11/K13: the browser leaves right after the tool call began; the thread holds a call with no result."""
    fake = script([text("Chào.")], [tool("student_profile", code="HS-01")], [text("Được.")])
    cid = lines(send(client, "Chào"))[0]["conversation_id"]
    monkeypatch.setattr(assistant, "StreamingResponse", lambda it, media_type: it)  # read the lines here
    stream = assistant.message(
        assistant.Message(conversation_id=cid, text="Tra HS-01"), SimpleNamespace(app=client.app)
    )
    for line in stream:
        if json.loads(line).get("state") == "start":
            break
    del stream  # the generator behind it is closed here, as when the connection drops
    gc.collect()
    monkeypatch.undo()
    assert lines(send(client, "Lại", cid=cid))[-1] == {"type": "done", "stopped": None}
    last = fake.calls[-1]
    assert {b["id"] for b in sent_blocks(last, "tool_use")} == {
        b["tool_use_id"] for b in sent_blocks(last, "tool_result")
    }
    assert not any("Tra HS-01" in t for t in sent_texts(last))
    assert [r.get("incomplete") for r in rows(paths, cid) if r["role"] == "assistant"] == [None, True, None]


def test_dropped_stream_is_incomplete(paths, client, w):
    script([text("A.")], [text("B.")])
    cid = lines(send(client, "Chào"))[0]["conversation_id"]
    resp = assistant.message(assistant.Message(conversation_id=cid, text="Bỏ đi"), SimpleNamespace(app=client.app))
    del resp
    gc.collect()
    assert [r.get("incomplete") for r in rows(paths, cid) if r["role"] == "assistant"] == [None, True]


def test_history_from_log_when_thread_is_empty(paths, client, w):
    """A log with no thread (old conversation): the last 20 text messages, never an incomplete turn."""
    cid = f"{date.today().isoformat()}-1"
    log = [r for i in range(15) for r in (
        {"id": "u", "role": "user", "ts": "t", "text": f"u{i}"},
        {"id": "a", "role": "assistant", "ts": "t", "text": f"a{i}"} | ({"incomplete": True} if i == 14 else {})
        | ({"tools": [{"name": "student_profile", "summary": "S13"}]} if i == 13 else {}),
    )]  # fmt: skip
    f = paths.logs / "chat" / f"{cid}.jsonl"
    f.write_text("".join(json.dumps(r) + "\n" for r in log), encoding="utf-8")
    fake = script([text("Ừ.")])
    lines(send(client, "Tin mới", cid=cid))
    got = sent_texts(fake.calls[0])
    assert len(got) == 21 and got[0] == "u4" and got[-1].endswith("Tin mới")
    assert not any(t in ("u14", "a14") for t in got)
    assert "a13\n\n(đã tra: S13)" in got


@pytest.mark.parametrize(("status", "stamp", "recheck"), [
    ("committed", "9999-01-01T00:00:00Z", True),
    ("committed", "2000-01-01T00:00:00Z", False),  # saved before the last answer: said already
    ("awaiting_review", "9999-01-01T00:00:00Z", False),
])  # fmt: skip
def test_save_since_last_answer_asks_for_a_recheck(paths, client, w, monkeypatch, status, stamp, recheck):
    cid = f"{date.today().isoformat()}-1"
    card = {"type": "card", "card": {"kind": "grading", "thread_id": "g1-x"}}
    log = [
        {"id": "m1", "role": "user", "ts": "2026-11-01T00:00:00Z", "text": "Chấm"},
        {"id": "m2", "role": "assistant", "ts": "2026-11-01T00:00:01Z", "text": "Xong", "events": [card]},
    ]
    (paths.logs / "chat" / f"{cid}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in log), encoding="utf-8")
    monkeypatch.setattr(client.app.state.runner, "get", lambda tid: {"status": status, "updated_at": stamp})
    fake = script([text("Ừ.")])
    lines(send(client, "Tiếp", cid=cid))
    assert (chat.RECHECK in json.dumps(fake.calls[0]["system"], ensure_ascii=False)) is recheck


def test_chat_db_has_no_names(paths, client, w):
    script([tool("student_profile", code="HS-01")], [text("Ừ.")])
    lines(send(client, "Nguyễn Văn An dạo này thế nào?"))
    blob = chat_db_bytes(paths)
    assert b"HS-01" in blob
    assert "Nguyễn Văn An".encode() not in blob and b"Nguyen Van An" not in blob
