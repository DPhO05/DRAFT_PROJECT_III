"""MONO-P0-02: module boundaries (SDD monolith §4.3), checked with ast."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "tutor"

# layer -> tutor.* layers it may import (its own layer is always allowed)
ALLOWED = {
    "config": set(),
    "services": {"config"},
    "llm": {"config"},
    "devfake": {"llm"},
    "db": {"config", "services"},
    "agents": {"llm", "services", "config"},
    "graphs": {"agents", "db", "services", "config"},
    "mcp": {"agents", "services", "db", "config"},  # R12
    "api": {"graphs", "db", "services", "llm", "config", "devfake", "agents", "mcp"},  # agents: see API_AGENTS
    # cli runs create_app() for `tutor app`; agents: see CLI_AGENTS
    "cli": {"api", "graphs", "db", "services", "llm", "config", "devfake", "agents"},
}
LLM_READ_ONLY = {"iter_log", "cost"}  # what api / cli may take from tutor.llm
API_AGENTS = {"a00_orchestrator"}  # what api/assistant.py, the only api file that imports agents, may take
CLI_AGENTS = {"a08_recommender"}  # what cli may take: `tutor worksheet` ranks problems with 08
ORCHESTRATOR = Path("tutor/agents/a00_orchestrator/orchestrator.py")
ASSISTANT_FILES = {
    Path("tutor/api/assistant.py"),
    ORCHESTRATOR,
    Path("tutor/agents/a00_orchestrator/tools.py"),
}  # R21: no resume; nor anywhere under tutor/mcp/ (MCP_DIR)
MCP_DIR = Path("tutor/mcp")


def layer(parts: list[str]) -> str | None:
    """['tutor', 'db', 'repo'] -> 'db'; ['tutor'] -> None (root package)."""
    return parts[1] if len(parts) > 1 and parts[0] == "tutor" else None


def violations(root: Path) -> list[str]:
    out = []
    for f in sorted(root.rglob("*.py")):
        rel = f.relative_to(root.parent)
        mod = list(rel.with_suffix("").parts)
        pkg = mod[:-1]
        me = layer(pkg if f.name == "__init__.py" else mod)
        if me is None:
            continue

        def bad(node, msg, rel=rel):
            out.append(f"{rel}:{node.lineno}: {msg}")

        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            targets: list[tuple[list[str], list[str]]] = []
            if isinstance(node, ast.Import):
                targets = [(a.name.split("."), []) for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = pkg[: len(pkg) - node.level + 1] if node.level else []
                full = base + (node.module.split(".") if node.module else [])
                targets = [(full, [a.name for a in node.names])]
            for full, names in targets:
                if not full or full[0] != "tutor":
                    continue
                tl = layer(full)
                layers = [tl] if tl else [n for n in names if n in ALLOWED]
                for t in layers:
                    if t != me and t not in ALLOWED[me]:
                        bad(node, f"{me} must not import tutor.{t}")
                    if me in ("api", "cli") and t == "agents":
                        mods = {full[2]} if len(full) > 2 else set(names) if tl else {"agents"}
                        if me == "api" and (rel != Path("tutor/api/assistant.py") or mods - API_AGENTS):
                            bad(node, "api may import only agents.a00_orchestrator, and only in api/assistant.py")
                        if me == "cli" and mods - CLI_AGENTS:
                            bad(node, "cli may import only agents.a08_recommender")
                if tl == "llm" and me in ("api", "cli") and len(full) == 2:
                    for n in set(names) - LLM_READ_ONLY:
                        bad(node, f"{me} may only use llm.iter_log / llm.cost, not {n}")
            if isinstance(node, ast.Call):
                fn = node.func
                name = fn.attr if isinstance(fn, ast.Attribute) else fn.id if isinstance(fn, ast.Name) else ""
                if name.startswith("commit_") and me != "graphs" and rel != Path("tutor/db/repo.py"):
                    bad(node, f"{name}() only from tutor/graphs/")
                on_llm = isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name) and fn.value.id == "llm"
                if on_llm and name == "call" and me != "agents":
                    bad(node, "llm.call() only from tutor/agents/")
                if on_llm and name == "chat" and rel != ORCHESTRATOR:
                    bad(node, "llm.chat() only from tutor/agents/a00_orchestrator/orchestrator.py")
                if name == "resume" and (rel in ASSISTANT_FILES or rel.is_relative_to(MCP_DIR)):
                    bad(node, "resume() never from the assistant (C-39)")
    return out


def test_tutor_package_respects_boundaries():
    assert violations(ROOT) == []


def write(root: Path, rel: str, src: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(src, encoding="utf-8")


def test_forbidden_import_is_reported_with_file_and_line(tmp_path):
    write(tmp_path, "tutor/agents/grader.py", "import json\nfrom tutor.db import repo\n")
    write(tmp_path, "tutor/agents/ok.py", "from tutor import config\nfrom ..services import latex\n")
    write(tmp_path, "tutor/services/x.py", "from .. import db\n")
    assert violations(tmp_path / "tutor") == [
        "tutor/agents/grader.py:2: agents must not import tutor.db",
        "tutor/services/x.py:1: services must not import tutor.db",
    ]


def test_commit_and_llm_call_rules(tmp_path):
    write(tmp_path, "tutor/api/s.py", "from tutor.db import repo\nrepo.commit_session(1)\nrepo.add_student('a')\n")
    write(tmp_path, "tutor/graphs/g.py", "from tutor.db import repo\nrepo.commit_session(1)\n")
    write(tmp_path, "tutor/graphs/n.py", "from tutor import llm\nllm.call('03')\n")
    write(tmp_path, "tutor/cli.py", "from tutor.llm import cost, call\n")
    assert violations(tmp_path / "tutor") == [
        "tutor/api/s.py:2: commit_session() only from tutor/graphs/",
        "tutor/cli.py:1: cli may only use llm.iter_log / llm.cost, not call",
        "tutor/graphs/n.py:1: graphs must not import tutor.llm",
        "tutor/graphs/n.py:2: llm.call() only from tutor/agents/",
    ]


def test_assistant_rules(tmp_path):
    """MONO-P6-01 (R21): agents only via api/assistant.py, llm.chat only in the orchestrator, no resume (C-39)."""
    write(
        tmp_path,
        "tutor/api/assistant.py",
        "from tutor.agents.a00_orchestrator.tools import Starters\n"
        "from tutor.agents.a00_orchestrator import orchestrator\n"
        "runner.resume('t')\n",
    )
    write(
        tmp_path,
        "tutor/api/other.py",
        "from tutor.agents.a00_orchestrator import tools\nimport tutor.agents.a00_orchestrator.orchestrator\n",
    )
    write(tmp_path, "tutor/api/assistant_extra.py", "from tutor.agents.a02_grader.grader import GradeOut\n")
    write(
        tmp_path,
        "tutor/agents/a00_orchestrator/tools.py",
        "from tutor.db import repo\nfrom tutor import llm\nllm.chat('00')\n",
    )
    write(
        tmp_path,
        "tutor/agents/a00_orchestrator/orchestrator.py",
        "from tutor import llm\nllm.chat('00')\nself.resume()\n",
    )
    write(tmp_path, "tutor/api/threads.py", "runner.resume('t')\n")
    msg = "api may import only agents.a00_orchestrator, and only in api/assistant.py"
    assert violations(tmp_path / "tutor") == [
        "tutor/agents/a00_orchestrator/orchestrator.py:3: resume() never from the assistant (C-39)",
        "tutor/agents/a00_orchestrator/tools.py:1: agents must not import tutor.db",
        "tutor/agents/a00_orchestrator/tools.py:3: llm.chat() only from tutor/agents/a00_orchestrator/orchestrator.py",
        "tutor/api/assistant.py:3: resume() never from the assistant (C-39)",
        f"tutor/api/assistant_extra.py:1: {msg}",
        f"tutor/api/other.py:1: {msg}",
        f"tutor/api/other.py:2: {msg}",
    ]


def test_mcp_rules(tmp_path):
    """R12: mcp sits above agents; api may import it, agents never; no resume in tutor/mcp/ (C-39)."""
    write(tmp_path, "tutor/agents/x.py", "import tutor.mcp.client\n")
    write(
        tmp_path,
        "tutor/mcp/server.py",
        "from tutor.agents.a00_orchestrator import tools\nfrom tutor.db import repo\nrunner.resume('t')\n",
    )
    write(tmp_path, "tutor/mcp/client.py", "from mcp import Client\nrunner.resume('t')\n")
    write(tmp_path, "tutor/mcp/roles.py", "runner.resume('t')\n")
    write(tmp_path, "tutor/api/assistant.py", "from tutor.mcp.client import connect\n")
    assert violations(tmp_path / "tutor") == [
        "tutor/agents/x.py:1: agents must not import tutor.mcp",
        "tutor/mcp/client.py:2: resume() never from the assistant (C-39)",
        "tutor/mcp/roles.py:1: resume() never from the assistant (C-39)",
        "tutor/mcp/server.py:3: resume() never from the assistant (C-39)",
    ]


def test_cli_may_import_only_08(tmp_path):
    write(
        tmp_path,
        "tutor/cli.py",
        "from tutor.agents.a08_recommender import select\nfrom tutor.agents.a02_grader import grader\n",
    )
    assert violations(tmp_path / "tutor") == ["tutor/cli.py:2: cli may import only agents.a08_recommender"]


def test_one_folder_per_agent():
    agents = ROOT / "agents"

    def entries(d: Path) -> list[str]:
        return sorted(p.name for p in d.iterdir() if p.name != "__pycache__")

    assert [p.name for p in agents.glob("*.py")] == ["__init__.py"]
    assert [d for d in entries(agents) if d != "__init__.py"] == [
        "a00_orchestrator",
        "a01_ingest",
        "a02_grader",
        "a03_diagnoser",
        "a04_verifier",
        "a05_profiler",
        "a06_tagger",
        "a08_recommender",
        "a09_reporter",
    ]
    for pointer_only in ("a05_profiler", "a06_tagger"):
        assert entries(agents / pointer_only) == ["README.md"]
    assert entries(agents / "a08_recommender") == ["README.md", "__init__.py", "select.py"]
    assert entries(agents / "a09_reporter") == ["__init__.py", "reporter.py"]
