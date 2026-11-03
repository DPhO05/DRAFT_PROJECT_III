"""MCP server and client for role 00 (design T7): same tools as Toolbox, H3 allowlist, H5 start limits."""

import json
import re
import threading
import traceback
from contextlib import closing

import anyio
import pytest
from mcp import Client

from tests.agents.test_tools import CALLS, box, recorder
from tests.assistant_fix import world
from tutor.agents.a00_orchestrator import tools
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
