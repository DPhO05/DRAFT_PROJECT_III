"""Sync MCP client for one tutor message (design T7): each operation is its own `anyio.run`, nothing held between.

Never call it from an `async def` or a thread already running an event loop (design §11 M8)."""

from collections import Counter

import anyio
from mcp import Client, MCPError
from mcp.server import Server

from tutor.agents.a00_orchestrator.tools import _ONCE, _REFUSED, LIMITS, Toolbox
from tutor.mcp import server


def _origin(e: BaseException) -> BaseException:
    """The tool body's own error out of anyio's task groups and the SDK's MCPError (R11)."""
    while isinstance(e, BaseExceptionGroup) and len(e.exceptions) == 1:
        e = e.exceptions[0]
    return e.__cause__ if isinstance(e, MCPError) and e.__cause__ else e


class Session:
    """H3 layer 2 and H5 run here, before the server; a refused call never reaches it."""

    def __init__(self, srv: Server):
        self.server = srv
        self._tools: list[dict] | None = None
        self.started: Counter[str] = Counter()  # successful calls per tool name (R9)

    def _run(self, op):
        async def go():
            # raise_exceptions: the SDK chains the handler's error instead of logging and masking it
            async with Client(self.server, raise_exceptions=True) as c:
                return await op(c)

        try:
            return anyio.run(go)
        except (BaseExceptionGroup, MCPError) as e:  # MCPError bare: an SDK patch that stops wrapping
            err = _origin(e)
        raise err  # outside the except, so the tool error keeps its own cause and context

    def tools(self) -> list[dict]:
        if self._tools is None:
            listed = self._run(lambda c: c.list_tools()).tools
            self._tools = [
                {"name": t.name, "description": t.description, "strict": True, "input_schema": t.input_schema}
                for t in listed
            ]
        return self._tools

    def call(self, name: str, args: dict) -> tuple[str, bool, dict]:
        """(content for the model, is_error, `tutor/` keys of `_meta` for the UI)."""
        if name not in {t["name"] for t in self.tools()}:
            return server.error(f"Không có công cụ {name}"), True, {}
        if name in LIMITS and self.started[name] >= LIMITS[name]:
            return server.error(_REFUSED.get(name, _ONCE)), True, {}
        r = self._run(lambda c: c.call_tool(name, args))
        self.started[name] += not r.is_error
        meta = {k: v for k, v in (r.meta or {}).items() if k.startswith("tutor/")}
        return r.content[0].text, r.is_error, meta

    def resource(self, uri: str) -> str:
        """JSON text of a catalog in the role (T8); the server refuses any other URI."""
        return self._run(lambda c: c.read_resource(uri)).contents[0].text


def connect(role: str, box: Toolbox) -> Session:
    return Session(server.build(role, box))
