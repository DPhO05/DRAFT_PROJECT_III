"""In-process MCP server around one tutor message's Toolbox (design T7): only the role's tools (H3 layer 1)."""

import json

from mcp import types
from mcp.server import Server

from tutor.agents.a00_orchestrator import tools
from tutor.agents.a00_orchestrator.tools import LABELS, Toolbox, tool_defs
from tutor.db import repo

ROLES: dict[str, tuple[str, ...]] = {"00": tuple(LABELS)}


def error(message: str) -> str:
    """Tool error content, the same JSON as Toolbox.run's."""
    return json.dumps({"error": message}, ensure_ascii=False, separators=(",", ":"))


def build(role: str, box: Toolbox) -> Server:
    names = ROLES[role]

    async def list_tools(ctx, params) -> types.ListToolsResult:
        defs = tool_defs([c["code"] for c in repo.error_codes(box.conn, active_only=True)])
        return types.ListToolsResult(
            tools=[
                types.Tool(name=d["name"], description=d["description"], input_schema=d["input_schema"])
                for d in defs
                if d["name"] in names
            ]
        )

    async def call_tool(ctx, params) -> types.CallToolResult:
        if params.name not in names:  # never reaches the Toolbox, so no outcome either
            text = error(f"Không có công cụ {params.name}")
            return types.CallToolResult(content=[types.TextContent(type="text", text=text)], is_error=True)
        out = box.run(params.name, params.arguments or {})  # sync body inline: it blocks only this call's loop (M8)
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=out.content)],
            is_error=out.is_error,
            _meta=tools.meta(out) or None,
        )

    return Server(f"tutor-{role}", on_list_tools=list_tools, on_call_tool=call_tool)
