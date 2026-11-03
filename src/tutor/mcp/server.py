"""In-process MCP server around one tutor message's Toolbox (design T7): only the role's tools (H3 layer 1)."""

import json
from functools import cache

from mcp import MCPError, types
from mcp.server import Server

from tutor.agents.a00_orchestrator import tools
from tutor.agents.a00_orchestrator.tools import LABELS, Toolbox, tool_defs
from tutor.db import repo
from tutor.services import facts, students

ERROR_CODES = "tutor://catalog/error-codes"
KCS = "tutor://catalog/kcs"
REPORT_FACTS = tools._tool(  # tool 14: only code calls it (R13), so it is not in 00's TOOLS
    "report_facts",
    "Số liệu báo cáo một kỳ của một học sinh: facts có fact_id, điểm cần nói, kỳ trước.",
    {
        "code": tools._CODE,
        "period_kind": {"type": "string", "enum": list(facts.KINDS)},
        "period_start": {"type": "string", "description": "Ngày bắt đầu kỳ, dạng yyyy-mm-dd"},
    },
    ("code", "period_kind", "period_start"),
)
ROLES: dict[str, tuple[str, ...]] = {"00": tuple(LABELS), "09": ("rank_problems", "report_facts")}
RESOURCES: dict[str, tuple[str, ...]] = {"00": (ERROR_CODES, KCS), "09": ()}  # read by code, not offered to the model


def error(message: str) -> str:
    """Tool error content, the same JSON as Toolbox.run's."""
    return json.dumps({"error": message}, ensure_ascii=False, separators=(",", ":"))


def _report_facts(box: Toolbox, a: dict) -> tuple[str, bool]:
    """(content, is_error): an empty or malformed period is a tool error in words (R13)."""
    try:
        sid = students.student_id(box.conn, a["code"])
        out = facts.report_facts(box.conn, sid, a["period_kind"], a["period_start"], today=box.today,
                                 low_pass_rate=box.settings["report"]["low_pass_rate"])  # fmt: skip
    except facts.NotReady:
        return error("Kỳ này chưa có buổi học nào đã duyệt"), True
    except ValueError as e:
        return error(str(e)), True
    return json.dumps(out, ensure_ascii=False, separators=(",", ":")), False


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
        defs = [*tool_defs([c["code"] for c in codes()]), REPORT_FACTS]
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
        if params.name == "report_facts":  # before box.run: Toolbox knows only LABELS
            text, is_error = _report_facts(box, params.arguments or {})
            return types.CallToolResult(content=[types.TextContent(type="text", text=text)], is_error=is_error)
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
