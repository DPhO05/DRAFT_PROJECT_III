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
from tests.api.test_sessions import TEX, W, add_student, poll
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
                    "mentions": [w["an"]], "attachment": None, "from": None}  # fmt: skip
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


def test_wrong_model_has_its_own_code(paths, client, w):
    script(llm.BadRequest("x"))
    assert lines(send(client, "Hỏi"))[-1] == {"type": "error", "code": "bad_model", "message": assistant.BAD_MODEL}


def test_chat_card_and_server_share_the_key_text():
    assert f"bad_key: '{BAD_KEY}'" in (Path(__file__).parents[2] / "app" / "chat.js").read_text(encoding="utf-8")


def real_llm(monkeypatch, paths, models, client=None):
    """Route agent 00 through the real llm.py, with the provider (if any) over a mock transport."""
    if client:
        shared = dict(api_key="test", use_responses_api=True, store=False, max_retries=0,
                      root_client=client, client=client.chat.completions)  # fmt: skip
        monkeypatch.setattr(
            llm, "_chat", {m: llm.GuardedOpenAI(model=m.split(":")[1], **shared) for m in models.values()}
        )  # what llm.model builds, over the mock client
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


def test_pending_lists_running_grading(client):
    sid = add_student(client)
    g1, _, _ = submit(client, sid)
    client.app.state.runner._set(g1, status="running")
    got = client.get("/api/assistant/pending").json()
    assert [(i["thread_id"], i["kind"], i["state"]) for i in got["items"]] == [(g1, "grading", "saving")]
    assert got["counts"]["assistant"] == 0  # nothing for the tutor to do yet


def test_no_route_to_commit(client):
    spec = client.get("/api/openapi.json").json()["paths"]
    got = {(m.upper(), p) for p, ops in spec.items() if p.startswith("/api/assistant") for m in ops}
    assert got == {
        ("POST", "/api/assistant/messages"),
        ("GET", "/api/assistant/conversations"),
        ("GET", "/api/assistant/conversations/{conversation_id}"),
        ("GET", "/api/assistant/pending"),
        ("POST", "/api/assistant/conversations/{conversation_id}/decide"),
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
        | ({"text": ""} if i == 5 else {})
        | ({"tools": [{"name": "student_profile", "summary": "S13"}]} if i == 13 else {}),
    )]  # fmt: skip
    f = paths.logs / "chat" / f"{cid}.jsonl"
    f.write_text("".join(json.dumps(r) + "\n" for r in log), encoding="utf-8")
    fake = script([text("Ừ.")])
    lines(send(client, "Tin mới", cid=cid))
    got = sent_texts(fake.calls[0])
    # 27 kept rows (a5 is empty, pair 14 incomplete); the last 20 start on a3, which is dropped: u4 leads
    assert len(got) == 20 and got[0] == "u4" and got[-1].endswith("Tin mới")
    assert not any(t in ("u14", "a14", "a5", "") for t in got)
    assert "a13\n\n(đã tra: S13)" in got


def test_old_log_text_is_masked_against_todays_names(paths, client, w):
    """C-40: a log line written before the student existed holds the name; the thread built from it must not."""
    name = "Nguyễn Văn An"
    cid = f"{date.today().isoformat()}-1"
    log = [
        {"id": "m1", "role": "user", "ts": "t", "text": f"{name} làm bài thế nào?"},
        {"id": "m2", "role": "assistant", "ts": "t", "text": f"{name} làm khá."},
    ]
    (paths.logs / "chat" / f"{cid}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in log), encoding="utf-8")
    script([text("Ừ.")])
    lines(send(client, "Tin mới", cid=cid))
    blob = chat_db_bytes(paths)
    assert b"Tin m" in blob
    assert name.encode() not in blob


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


def test_meta_never_reaches_the_model(paths, client, w):
    """C-40: the `tutor/` meta of a tool result stays in the thread's artifact, never in a model call."""
    fake = script([tool("list_students"), tool("student_profile", code="HS-01")], [text("Ừ.")], [text("Ừ2.")])
    cid = lines(send(client, "Ai yếu?"))[0]["conversation_id"]
    lines(send(client, "Tiếp", cid=cid))
    assert len(fake.calls) == 3 and "tutor/" not in json.dumps(fake.calls, ensure_ascii=False)


def orphan_free(call) -> bool:
    return {b["id"] for b in sent_blocks(call, "tool_use")} == {
        b["tool_use_id"] for b in sent_blocks(call, "tool_result")
    }


@pytest.mark.parametrize("first_ok", [False, True])
def test_tool_crash_leaves_no_orphan_call(paths, client, w, monkeypatch, first_ok):
    """The tool raises, so the thread keeps an AI tool_use with no result; the next turn runs from before it."""
    calls = []
    real = Toolbox.tool_list_students

    def boom(self, a):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("tool broke")
        return real(self, a)

    monkeypatch.setattr(Toolbox, "tool_list_students", boom)
    fake = script(*([[text("Chào.")]] if first_ok else []), [tool("list_students")], [text("Được.")])
    cid = lines(send(client, "Chào"))[0]["conversation_id"] if first_ok else None
    evs = lines(send(client, "Ai yếu?", cid=cid))
    cid = evs[0]["conversation_id"]
    assert evs[-1]["code"] == "internal"
    assert lines(send(client, "Lại", cid=cid))[-1] == {"type": "done", "stopped": None}
    last = fake.calls[-1]
    assert orphan_free(last) and not any("Ai yếu?" in t for t in sent_texts(last))


def test_killed_process_leaves_the_way_back(paths, client, w, monkeypatch):
    """P4-11: the process died mid-turn, so there is no assistant row; the user row's `from` is the way back."""
    monkeypatch.setattr(Toolbox, "tool_list_students", lambda self, a: (_ for _ in ()).throw(RuntimeError("x")))
    n = []

    def strict(messages):  # a provider that rejects a tool_use with no tool_result, as the real APIs do
        n.append(1)
        blocks = [b for m in messages if isinstance(m["content"], list) for b in m["content"]]
        last = messages[-1]["content"]
        if {b["id"] for b in blocks if b["type"] == "tool_use"} != {
            b["tool_use_id"] for b in blocks if b["type"] == "tool_result"
        } and not (isinstance(last, list) and last[-1]["type"] == "tool_result"):
            raise llm.LLMUnavailable("00: 400 dangling tool call")
        return [tool("list_students")] if len(n) == 2 else [text("Ừ.")]

    llm.set_backend(FakeLLM({"00": strict}))
    cid = lines(send(client, "Chào"))[0]["conversation_id"]
    lines(send(client, "Ai yếu?", cid=cid))
    f = paths.logs / "chat" / f"{cid}.jsonl"
    f.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows(paths, cid)[:-1]), encoding="utf-8")
    for msg in ("Lại", "Lại nữa"):
        assert lines(send(client, msg, cid=cid))[-1] == {"type": "done", "stopped": None}


DAY, EARLIER = "2026-11-15", "2026-11-14"


def ask_grading(client, paths, w, *then, day=DAY):
    """The model picks start_grading from free text; returns (events, conversation id)."""
    (paths.inbox / "s01.tex").write_text(TEX, encoding="utf-8")
    script([tool("start_grading", code="HS-01", file="s01.tex", held_on=day)], *then)
    evs = lines(send(client, "Chấm bài s01.tex cho @HS-01", [w["an"]]))
    return evs, evs[0]["conversation_id"]


def decide(client, cid, decision, args=None):
    body = {"decision": decision} | ({"args": args} if args else {})
    return client.post(f"/api/assistant/conversations/{cid}/decide", json=body, headers=W)


def g1(client) -> list[str]:
    return sorted(t["thread_id"] for t in client.app.state.runner.list_threads())


def test_free_text_grading_waits_for_the_tutor(paths, client, w):
    evs, cid = ask_grading(client, paths, w)
    assert evs[-1] == {
        "type": "approval",
        "name": "start_grading",
        "args": {"code": "HS-01", "file": "s01.tex", "held_on": DAY},
        "description": "Chấm s01.tex cho HS-01, buổi 15/11?",
    }
    assert "done" not in [e["type"] for e in evs] and g1(client) == []
    bot = rows(paths, cid)[-1]
    assert bot["role"] == "assistant" and not bot.get("incomplete") and bot["events"][-1]["type"] == "approval"


def test_approve_starts_the_thread(paths, client, w):
    _, cid = ask_grading(client, paths, w, [text("Đã bắt đầu.")])
    evs = lines(decide(client, cid, "approve"))
    assert evs[0]["type"] == "start" and evs[0]["conversation_id"] == cid
    assert [e["card"]["kind"] for e in evs if e["type"] == "card"] == ["grading"]
    assert evs[-1] == {"type": "done", "stopped": None} and g1(client) == ["g1-hs01-20261115"]


def test_edit_runs_with_the_new_date(paths, client, w):
    _, cid = ask_grading(client, paths, w, [text("Đã bắt đầu.")])
    args = {"code": "HS-01", "file": "s01.tex", "held_on": EARLIER}
    [card] = [e["card"] for e in lines(decide(client, cid, "edit", args)) if e["type"] == "card"]
    assert g1(client) == ["g1-hs01-20261114"] and card["thread_id"] == "g1-hs01-20261114"


def test_reject_answers_in_words(paths, client, w):
    fake = script([tool("start_grading", code="HS-01", file="s01.tex", held_on=DAY)], [text("Mình không chấm nữa.")])
    (paths.inbox / "s01.tex").write_text(TEX, encoding="utf-8")
    cid = lines(send(client, "Chấm bài s01.tex cho @HS-01", [w["an"]]))[0]["conversation_id"]
    evs = lines(decide(client, cid, "reject"))
    assert g1(client) == [] and "".join(e["delta"] for e in evs if e["type"] == "text") == "Mình không chấm nữa."
    assert not [e for e in evs if e["type"] == "card"] and len(fake.calls) == 2
    assert [r["role"] for r in rows(paths, cid)] == ["user", "assistant", "user", "assistant"]


def test_waiting_turn_is_not_rewound_or_pruned(paths, client, w):
    evs, cid = ask_grading(client, paths, w)
    log = rows(paths, cid)
    assert assistant._resume(log) is None and assistant._waiting(log)
    store = client.app.state.chat
    n = lambda sql: store.conn.execute(sql, (cid,)).fetchone()[0]  # noqa: E731
    assert n("SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?") == 1
    assert n("SELECT COUNT(*) FROM writes WHERE thread_id = ? AND channel = '__interrupt__'") == 1


def test_waiting_survives_a_new_app(paths, app, w):
    base = f"http://127.0.0.1:{PORT}"
    with TestClient(app, base_url=base) as c:
        _, cid = ask_grading(c, paths, w, [text("Đã bắt đầu.")])
    with TestClient(create_app(paths, port=PORT), base_url=base) as c:
        got = c.get("/api/assistant/pending").json()
        [item] = [i for i in got["items"] if i["kind"] == "approval"]
        assert item["conversation_id"] == cid and item["description"] == "Chấm s01.tex cho HS-01, buổi 15/11?"
        assert got["counts"]["assistant"] == 1
        assert lines(decide(c, cid, "approve"))[-1] == {"type": "done", "stopped": None}
        assert g1(c) == ["g1-hs01-20261115"]
        assert not [i for i in c.get("/api/assistant/pending").json()["items"] if i["kind"] == "approval"]


def test_edited_args_are_masked_and_checked(paths, client, w):
    _, cid = ask_grading(client, paths, w, [text("Đã bắt đầu.")])
    late = {"code": "HS-01", "file": "s01.tex", "held_on": "2999-01-01"}
    r = decide(client, cid, "edit", late)
    assert r.status_code == 422 and "sau hôm nay" in r.json()["error"]["message"]
    named = {"code": "HS-01", "file": "Nguyễn Văn An.tex", "held_on": EARLIER}
    lines(decide(client, cid, "edit", named))
    blob = chat_db_bytes(paths) + (paths.logs / "chat" / f"{cid}.jsonl").read_bytes()
    assert (
        "Nguyễn Văn An".encode() not in blob and "Nguyễn Văn An".encode() not in (paths.logs / "llm.jsonl").read_bytes()
    )


def test_decide_without_a_waiting_call(paths, client, w):
    script([text("Chào.")])
    cid = lines(send(client, "Chào"))[0]["conversation_id"]
    assert decide(client, cid, "approve").status_code == 409
    assert decide(client, "2026-01-01-9", "approve").status_code == 404
    assert (
        client.post(f"/api/assistant/conversations/{cid}/decide", json={"decision": "edit"}, headers=W).status_code
        == 422
    )


def test_message_waits_for_the_decision(paths, client, w):
    _, cid = ask_grading(client, paths, w, [text("Đã bắt đầu.")])
    r = send(client, "Thôi", cid=cid)
    assert r.status_code == 409 and "duyệt" in r.json()["error"]["message"]
    assert lines(decide(client, cid, "approve"))[-1]["type"] == "done"


def waiting_state(client, cid) -> tuple[bool, bool]:
    """(GET says waiting, /pending lists it): one rule, so both agree."""
    got = client.get(f"/api/assistant/conversations/{cid}").json()["waiting"]
    listed = any(i["kind"] == "approval" for i in client.get("/api/assistant/pending").json()["items"])
    assert got == listed
    return got, listed


def test_decision_is_final_once_the_tool_ran(paths, client, w):
    """P4-14 (b): the grading started, then the model failed; the tutor is not asked again and nothing starts twice."""
    _, cid = ask_grading(client, paths, w, llm.LLMUnavailable("00: overloaded"), [text("Ừ.")])
    assert lines(decide(client, cid, "approve"))[-1]["type"] == "error"
    assert g1(client) == ["g1-hs01-20261115"] and waiting_state(client, cid) == (False, False)
    assert decide(client, cid, "reject").status_code == 409
    assert lines(send(client, "Tiếp nhé", cid=cid))[-1] == {"type": "done", "stopped": None}
    assert g1(client) == ["g1-hs01-20261115"]


def test_decision_stays_open_until_the_tool_ran(paths, client, w, monkeypatch):
    """P4-14 (a): the stream ended before the tool ran; a retry with Bỏ is honoured, not the first Duyệt."""
    real, boom = Toolbox.tool_start_grading, []

    def once(self, a):
        if not boom:
            boom.append(1)
            raise RuntimeError("tool broke")
        return real(self, a)

    monkeypatch.setattr(Toolbox, "tool_start_grading", once)
    _, cid = ask_grading(client, paths, w, [text("Không chấm.")])
    assert lines(decide(client, cid, "approve"))[-1]["code"] == "internal" and g1(client) == []
    assert waiting_state(client, cid) == (True, True)
    refused = send(client, "Thôi", cid=cid)
    assert (refused.status_code, refused.json()["error"]["message"]) == (409, assistant.WAITING)
    evs = lines(decide(client, cid, "reject"))
    assert "".join(e["delta"] for e in evs if e["type"] == "text") == "Không chấm." and g1(client) == []
    assert waiting_state(client, cid) == (False, False)


def test_edit_by_full_name_starts_that_students_thread(paths, client, w):
    _, cid = ask_grading(client, paths, w, [text("Đã bắt đầu.")])
    lines(decide(client, cid, "edit", {"code": "Nguyễn Văn An", "file": "s01.tex", "held_on": EARLIER}))
    assert g1(client) == ["g1-hs01-20261114"]
    assert "Nguyễn Văn An".encode() not in chat_db_bytes(paths) + (paths.logs / "chat" / f"{cid}.jsonl").read_bytes()


def test_decision_row_keeps_no_args_unless_edited(paths, client, w):
    _, cid = ask_grading(client, paths, w, [text("Đã bắt đầu.")])
    lines(decide(client, cid, "approve", {"code": "HS-09", "file": "x", "held_on": "x"}))
    [row] = [r for r in rows(paths, cid) if r.get("decision")]
    assert row["args"] is None
