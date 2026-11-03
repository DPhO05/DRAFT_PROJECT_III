"""MCP server and client for role 00 (design T7): same tools as Toolbox, H3 allowlist, H5 start limits."""

import gc
import json
import re
import threading
import traceback
from contextlib import closing

import anyio
import pytest
from mcp import Client, MCPError, types

from tests.agents.test_orchestrator import text, tool
from tests.agents.test_tools import CALLS, box, recorder
from tests.assistant_fix import SWAP, world
from tests.fakes import FakeLLM
from tutor import config, llm
from tutor.agents.a00_orchestrator import orchestrator, tools
from tutor.agents.a00_orchestrator.orchestrator import Turn, fixed_parts
from tutor.agents.a00_orchestrator.tools import Toolbox, tool_defs
from tutor.db import repo
from tutor.mcp import client, server

GRADE = {"code": "HS-01", "file": "a.tex", "held_on": "2026-10-21"}
SHEET = {"code": "HS-01", "for_date": "2026-10-24", "refs": ["9DS-BPT-001"]}
START_ONCE = "Mỗi tin chỉ bắt đầu việc này một lần. Thầy/cô nhắn tin mới nếu cần làm thêm."
SHEET_TWICE = "Mỗi tin chỉ soạn phiếu nháp tối đa hai lần."


@pytest.fixture
def ro(conn, paths):
    w = world(conn)
    with closing(repo.connect(paths.tutor_db, readonly=True)) as c:
        yield c, w


def test_role_00_tools_equal_tool_defs(ro):
    codes = [c["code"] for c in repo.error_codes(ro[0], active_only=True)]
    got = client.connect("00", box(ro)).tools()
    assert got == tool_defs(codes) and len(got) == 10


def test_call_matches_toolbox(ro):
    s, direct = client.connect("00", box(ro)), box(ro)
    for name, args in CALLS:
        content, is_error, meta = s.call(name, args)
        out = direct.run(name, args)
        assert (content, is_error, meta) == (out.content, out.is_error, tools.meta(out)), name
        assert "tutor/" not in content and all(k.startswith("tutor/") for k in meta), name


@pytest.mark.parametrize(
    ("name", "args"),
    [("start_grading", GRADE), ("start_bank_import", {"file": "mix.tex"}), ("propose_worksheet", SHEET)],
)
def test_start_call_matches_toolbox(ro, name, args):
    """`_meta` of the start tools' cards survives the SDK's JSON dump unchanged."""
    out = box(ro, starters=recorder([])).run(name, args)
    content, is_error, meta = client.connect("00", box(ro, starters=recorder([]))).call(name, args)
    assert (content, is_error, meta) == (out.content, out.is_error, tools.meta(out))
    assert "tutor/card" in meta and not is_error


def test_unknown_name_two_layers(ro):
    b = box(ro)
    content, is_error, meta = client.connect("00", b).call("start_report", {"code": "HS-01"})
    assert json.loads(content) == {"error": "Không có công cụ start_report"}
    assert (is_error, meta, b.outcomes) == (True, {}, [])

    b = box(ro)

    async def go():
        async with Client(server.build("00", b)) as c:
            return await c.call_tool("start_report", {"code": "HS-01"})

    r = anyio.run(go)
    assert r.is_error is True and json.loads(r.content[0].text) == {"error": "Không có công cụ start_report"}
    assert b.outcomes == []


def test_start_limits(ro):
    calls = []
    s = client.connect("00", box(ro, starters=recorder(calls)))
    content, is_error, _ = s.call("start_grading", GRADE | {"code": "HS-99"})
    assert is_error and "Không có học sinh HS-99" in content  # a failed start is not counted
    grading = [s.call("start_grading", GRADE) for _ in range(5)]
    assert [e for _, e, _ in grading] == [False, True, True, True, True]
    imports = [s.call("start_bank_import", {"file": "mix.tex"}) for _ in range(2)]
    assert [e for _, e, _ in imports] == [False, True]
    sheets = [s.call("propose_worksheet", SHEET) for _ in range(3)]
    assert [e for _, e, _ in sheets] == [False, False, True]
    assert [c[0] for c in calls] == ["start_grading", "start_bank_import", "propose_worksheet", "propose_worksheet"]
    refused = [*grading[1:], imports[1], sheets[2]]
    assert [json.loads(c)["error"] for c, _, _ in refused] == [START_ONCE] * 5 + [SHEET_TWICE]
    assert all(re.search(r"\d", c) is None and m == {} for c, _, m in refused)


def test_limit_without_refusal_text_is_worded(ro, monkeypatch):
    """A tool given a LIMITS entry alone (P7's start_report) is refused in words, not by a KeyError."""
    monkeypatch.setitem(client.LIMITS, "list_students", 1)
    s = client.connect("00", box(ro))
    assert s.call("list_students", {})[1] is False
    content, is_error, meta = s.call("list_students", {})
    assert is_error and meta == {} and json.loads(content)["error"]
    assert re.search(r"\d", content) is None


def test_bare_mcperror_is_unwrapped(ro, monkeypatch):
    """If the SDK stops wrapping in an ExceptionGroup, the tool's own error still comes out."""
    cause = KeyError("k")

    def bare(_):
        raise MCPError(types.INTERNAL_ERROR, "x") from cause

    monkeypatch.setattr(client.anyio, "run", bare)
    with pytest.raises(KeyError) as e:
        client.connect("00", box(ro)).tools()
    assert e.value is cause


@pytest.mark.parametrize("cause", [None, KeyError("k")])
def test_crash_keeps_original_error(ro, monkeypatch, cause):
    def boom(self, a):
        raise RuntimeError("x") from cause

    monkeypatch.setattr(Toolbox, "tool_list_students", boom)
    with pytest.raises(RuntimeError, match="x") as e:
        client.connect("00", box(ro)).call("list_students", {})
    assert e.value.__cause__ is cause  # the tool error's own chain survives, like the direct path
    logged = "".join(traceback.format_exception(e.value))  # what log.exception writes to app.log
    assert "in boom" in logged and "ExceptionGroup" not in logged and "MCPError" not in logged


def test_no_thread_left(ro):
    before = threading.active_count()
    s = client.connect("00", box(ro))
    for _ in range(20):
        s.call("list_students", {})
    assert threading.active_count() == before


CHATS = [  # the FakeLLM scripts of tests/agents/test_orchestrator.py
    ("Tháng này @HS-01 yếu gì?", [[tool("student_profile", code="HS-01")], [text("HS-01 có 2 buổi.")]]),
    ("@HS-01 sai dấu mấy lần?", [[tool("student_mistakes", code="HS-01")], [text(
        "HS-01 sai 5 lần nhầm dấu. Hôm nay 21/10, lần gần nhất là 14/10.\n1. Bài 9DS-BPT-001: $x^2 = 4$ còn sai.")]]),
    ("@HS-01 thế nào?", [[tool("student_mistakes", code="HS-01"), tool("student_profile", code="HS-01")],
                         [tool("student_mistakes", code="HS-01")], [text("HS-01 còn 1 lỗi lặp.")]]),
    ("Học sinh nào yếu nhất?", [[tool("list_students"), tool("student_profile", code="HS-99")],
                                [text("Thầy chọn học sinh nhé.")]]),
    ("8DS-PT1-004, 8ds-pt1-005", None),
    (" 8ds-xxx-999 ", None),
]  # fmt: skip


def reply(ro, text_, script=None, s=None):
    """orchestrator.reply as test_orchestrator's `say` runs it, unread; s = a Session, None = the direct path."""
    c, w = ro
    everyone = repo.list_students(c, include_archived=True)
    codes = repo.error_codes(c, active_only=True)
    llm.set_backend(fake := FakeLLM({} if script is None else {"00": script}))
    events = orchestrator.reply(
        Turn(text_),
        history=[],
        conn=c,
        starters=None,
        settings=config.defaults(),
        today=w["today"],
        redact={x["name"]: x["code"] for x in everyone},
        students={x["id"]: x for x in everyone},
        conversation_id="2026-10-21-1",
        fixed=fixed_parts(repo.list_kc(c), codes),
        tools=s.tools() if s else tool_defs([x["code"] for x in codes]),
        call=s.call if s else None,
    )
    return events, fake


@pytest.mark.parametrize(("text_", "script"), CHATS)
def test_reply_same_events_with_mcp(ro, text_, script):
    direct, fake = reply(ro, text_, script)
    direct = list(direct)
    s = client.connect("00", box(ro, text=text_))
    mcp, fake_mcp = reply(ro, text_, script, s)
    mcp = list(mcp)
    assert mcp == direct
    assert sum(s.started.values()) == sum(e["state"] == "done" for e in mcp if e["type"] == "tool")  # via the Session
    assert fake_mcp.calls == fake.calls
    assert "tutor/" not in json.dumps(fake_mcp.calls, ensure_ascii=False)  # C-40: _meta never reaches the model


def test_closed_stream_leaves_nothing(ro):
    """Review Focus 1: the tab closes after a tool call; nothing is left running and the next message works."""
    two = [[tool("list_students")], [tool("student_profile", code="HS-01")], [text("HS-01 ổn.")]]
    before = threading.active_count()
    s = client.connect("00", box(ro, text="Ai yếu?"))
    events, _ = reply(ro, "Ai yếu?", two, s)
    next(e for e in events if e["type"] == "tool" and e["state"] == "done")
    events.close()
    del events
    gc.collect()
    assert s.started == {"list_students": 1}  # the first call ran through the server, the second never started
    assert threading.active_count() == before
    s = client.connect("00", box(ro, text="Ai yếu?"))
    events, _ = reply(ro, "Ai yếu?", two, s)
    events = list(events)
    assert s.started == {"list_students": 1, "student_profile": 1}
    assert [(e["name"], e["state"]) for e in events if e["type"] == "tool"] == [
        ("list_students", "start"), ("list_students", "done"), ("student_profile", "start"),
        ("student_profile", "done")]  # fmt: skip
    assert events[-1] == {"type": "done", "stopped": None}


def read_catalogs(s):
    """What api/assistant.message reads for the prompt: the fixed parts and the version of 00."""
    kcs, codes = json.loads(s.resource(server.KCS)), json.loads(s.resource(server.ERROR_CODES))
    fixed = fixed_parts(kcs, codes)
    return kcs, codes, fixed, orchestrator.version(fixed, s.tools())


def kind_enum(s):
    return next(t for t in s.tools() if t["name"] == "student_mistakes")["input_schema"]["properties"]["kind"]["enum"]


def test_catalog_resources_keep_prompt_version(ro):
    c = ro[0]
    kcs, codes, fixed_r, version_r = read_catalogs(client.connect("00", box(ro)))
    active = repo.error_codes(c, active_only=True)
    fixed_db = fixed_parts(repo.list_kc(c), active)
    assert fixed_r == fixed_db
    assert version_r == orchestrator.version(fixed_db, tool_defs([x["code"] for x in active]))
    assert all(set(x) == {"code", "category", "description", "example"} for x in codes) and len(codes) > 1
    assert all(set(x) == {"id", "name", "lop"} for x in kcs) and len(kcs) > 1


def test_catalog_change_moves_both(conn, ro):
    """Review Focus 5: a code the tutor turns off leaves the prompt's list and the tool `kind` enum together."""
    _, codes, _, v1 = read_catalogs(s1 := client.connect("00", box(ro)))
    assert SWAP in [x["code"] for x in codes] and SWAP in kind_enum(s1)
    repo.update_error_code(conn, SWAP, active=False)  # its own writing connection, between two messages
    _, codes, _, v2 = read_catalogs(s2 := client.connect("00", box(ro)))
    assert SWAP not in [x["code"] for x in codes] and SWAP not in kind_enum(s2)
    assert [x["code"] for x in codes] == kind_enum(s2)
    assert v2 != v1


def test_catalog_one_read_per_message(conn, ro):
    """The prompt's codes and the `kind` enum come from one read: a change mid-message shows in neither."""
    s = client.connect("00", box(ro))
    read = s.resource(server.ERROR_CODES)
    repo.update_error_code(conn, SWAP, active=False)
    assert kind_enum(s) == [x["code"] for x in json.loads(read)] and SWAP in kind_enum(s)
    assert s.resource(server.ERROR_CODES) == read


def test_role_00_resources(ro):
    async def go():
        async with Client(server.build("00", box(ro))) as c:
            return await c.list_resources()

    assert server.RESOURCES == {"00": (server.ERROR_CODES, server.KCS)}
    assert [str(r.uri) for r in anyio.run(go).resources] == [server.ERROR_CODES, server.KCS]
    with pytest.raises(MCPError, match="Không có tài nguyên"):  # outside the role: an error, nothing is read
        client.connect("00", box(ro)).resource("tutor://catalog/students")
