"""/api/assistant/messages over MCP (design T7): an aborted stream and a crashing tool, end to end."""

import gc
import json
import threading
from contextlib import closing
from types import SimpleNamespace

from tests.agents.test_orchestrator import text, tool
from tests.api.test_assistant import lines, rows, script, send
from tests.assistant_fix import world
from tutor.agents.a00_orchestrator.tools import Toolbox
from tutor.api import assistant
from tutor.db import repo


def test_closed_stream_frees_conversation(paths, client, monkeypatch):
    """Review Focus 1: the tab closes after a tool call; the next message of that conversation runs."""
    with closing(repo.connect(paths.tutor_db)) as c:
        world(c)
    script([text("Chào.")], [tool("list_students")], [text("Lại.")])
    cid = lines(send(client, "Chào"))[0]["conversation_id"]
    streams, real = [], assistant._stream
    monkeypatch.setattr(assistant, "_stream", lambda *a: streams.append(g := real(*a)) or g)
    before = threading.active_count()
    resp = assistant.message(assistant.Message(conversation_id=cid, text="Ai yếu?"), SimpleNamespace(app=client.app))
    [g] = streams
    next(x for x in g if json.loads(x).get("state") == "done")
    g.close()
    streams.clear()
    del resp, g
    gc.collect()
    assert threading.active_count() == before
    assert lines(send(client, "Lại", cid=cid))[-1] == {"type": "done", "stopped": None}
    got = rows(paths, cid)
    assert [(r["role"], r["text"]) for r in got[2:]] == [("user", "Ai yếu?"), ("assistant", ""), ("user", "Lại"),
                                                         ("assistant", "Lại.")]  # fmt: skip
    assert [t["name"] for t in got[3]["tools"]] == ["list_students"]


def test_tool_crash_is_internal(paths, client, monkeypatch):
    """Review Focus 4: a tool body's RuntimeError is `internal`, logged as itself, not as an ExceptionGroup."""
    with closing(repo.connect(paths.tutor_db)) as c:
        world(c)

    def boom(self, a):
        raise RuntimeError("tool broke")

    monkeypatch.setattr(Toolbox, "tool_list_students", boom)
    script([tool("list_students")])
    evs = lines(send(client, "Ai yếu?"))
    assert evs[-1] == {"type": "error", "code": "internal", "message": assistant.INTERNAL}
    logged = (paths.logs / "app.log").read_text(encoding="utf-8")
    assert "RuntimeError: tool broke" in logged and "in boom" in logged
    assert "tutor/mcp/client.py" in logged  # it went through the Session, not the direct path
    assert "ExceptionGroup" not in logged and "MCPError" not in logged
