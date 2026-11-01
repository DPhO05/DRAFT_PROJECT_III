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
    "api": {"graphs", "db", "services", "llm", "config", "devfake", "agents"},  # agents: see API_AGENTS
    "cli": {"api", "graphs", "db", "services", "llm", "config", "devfake"},  # cli runs create_app() for `tutor app`
}
LLM_READ_ONLY = {"iter_log", "cost"}  # what api / cli may take from tutor.llm
API_AGENTS = {"orchestrator", "tools"}  # what api/assistant.py, the only api file that imports agents, may take


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
                    if me == "api" and t == "agents":
                        mods = {full[2]} if len(full) > 2 else set(names) if tl else {"agents"}
                        if rel != Path("tutor/api/assistant.py") or mods - API_AGENTS:
                            bad(
                                node,
                                "api may import only agents.orchestrator / agents.tools, and only in api/assistant.py",
                            )
                if tl == "llm" and me in ("api", "cli") and len(full) == 2:
                    for n in set(names) - LLM_READ_ONLY:
                        bad(node, f"{me} may only use llm.iter_log / llm.cost, not {n}")
            if isinstance(node, ast.Call):
                fn = node.func
                name = fn.attr if isinstance(fn, ast.Attribute) else fn.id if isinstance(fn, ast.Name) else ""
                if name.startswith("commit_") and me != "graphs" and rel != Path("tutor/db/repo.py"):
                    bad(node, f"{name}() only from tutor/graphs/")
                if (
                    isinstance(fn, ast.Attribute)
                    and fn.attr == "call"
                    and isinstance(fn.value, ast.Name)
                    and fn.value.id == "llm"
                    and me != "agents"
                ):
                    bad(node, "llm.call() only from tutor/agents/")
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


def test_only_assistant_api_file_may_import_agents(tmp_path):
    write(
        tmp_path,
        "tutor/api/assistant.py",
        "from tutor.agents.tools import Starters\nfrom tutor.agents import orchestrator\n",
    )
    write(tmp_path, "tutor/api/other.py", "from tutor.agents import tools\nimport tutor.agents.orchestrator\n")
    write(tmp_path, "tutor/api/assistant_extra.py", "from tutor.agents.grader import GradeOut\n")
    write(tmp_path, "tutor/agents/tools.py", "from tutor.db import repo\n")
    msg = "api may import only agents.orchestrator / agents.tools, and only in api/assistant.py"
    assert violations(tmp_path / "tutor") == [
        "tutor/agents/tools.py:1: agents must not import tutor.db",
        f"tutor/api/assistant_extra.py:1: {msg}",
        f"tutor/api/other.py:1: {msg}",
        f"tutor/api/other.py:2: {msg}",
    ]
