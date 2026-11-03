"""In-process MCP server around one tutor message's Toolbox (design T7): only the role's tools (H3 layer 1)."""

import json
from functools import cache

from mcp import MCPError, types
from mcp.server import Server

from tutor.agents.a00_orchestrator import tools
from tutor.agents.a00_orchestrator.tools import LABELS, Toolbox, tool_defs
from tutor.db import repo

ERROR_CODES = "tutor://catalog/error-codes"
KCS = "tutor://catalog/kcs"
ROLES: dict[str, tuple[str, ...]] = {"00": tuple(LABELS)}
RESOURCES: dict[str, tuple[str, ...]] = {"00": (ERROR_CODES, KCS)}  # read by code, not offered to the model


def error(message: str) -> str:
    """Tool error content, the same JSON as Toolbox.run's."""
    return json.dumps({"error": message}, ensure_ascii=False, separators=(",", ":"))


def build(role: str, box: Toolbox) -> Server:
    names, uris = ROLES[role], RESOURCES[role]

    @cache  # read once per message: the tool `kind` enum and the prompt's code list must agree (T8)
    def codes() -> list[dict]:
        return repo.error_codes(box.conn, active_only=True)

    catalogs = {
        ERROR_CODES: lambda: [{k: c[k] for k in ("code", "category", "description", "example")} for c in codes()],
        KCS: lambda: [{k: c[k] for k in ("id", "name", "lop")} for c in repo.list_kc(box.conn)],
    }

    async def list_tools(ctx, params) -> types.ListToolsResult:
        defs = tool_defs([c["code"] for c in codes()])
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

    async def list_resources(ctx, params) -> types.ListResourcesResult:
        return types.ListResourcesResult(
            resources=[types.Resource(uri=u, name=u.rsplit("/", 1)[1], mime_type="application/json") for u in uris]
        )

    async def read_resource(ctx, params) -> types.ReadResourceResult:
        if params.uri not in uris:
            raise MCPError(types.INVALID_PARAMS, f"Không có tài nguyên {params.uri}")
        text = json.dumps(catalogs[params.uri](), ensure_ascii=False, separators=(",", ":"))
        return types.ReadResourceResult(
            contents=[types.TextResourceContents(uri=params.uri, mime_type="application/json", text=text)]
        )

    return Server(
        f"tutor-{role}",
        on_list_tools=list_tools,
        on_call_tool=call_tool,
        on_list_resources=list_resources,
        on_read_resource=read_resource,
    )
