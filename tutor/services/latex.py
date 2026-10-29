"""Cut LaTeX into problems, solutions and steps, keeping source positions (P1-T02)."""

import re
from dataclasses import dataclass, field
from typing import Literal

from pylatexenc import macrospec
from pylatexenc.latexwalker import LatexCommentNode, LatexEnvironmentNode, LatexWalker, get_default_latex_context_db

_DB = get_default_latex_context_db()
_DB.add_context_category(
    "tutor",
    environments=[macrospec.EnvironmentSpec("problem", "["), macrospec.EnvironmentSpec("solution", "[")],
    prepend=True,
)


@dataclass
class Step:
    idx: int  # 1-based
    latex: str
    pos: int
    pos_end: int


@dataclass
class Solution:
    label: str | None  # "cách 2" in \begin{solution}[cách 2]
    pos: int  # body, without \begin / \end
    pos_end: int


@dataclass
class Problem:
    ref: str | None  # None: student left out [id]
    pos: int  # whole environment
    pos_end: int
    body_pos: int  # inside \begin{problem}[id] … \end{problem}
    body_pos_end: int
    meta: dict[str, str] = field(default_factory=dict)  # "% key: value" comments
    statement: str = ""  # bank: text before the first solution, comments removed
    solutions: list[Solution] = field(default_factory=list)


def _walk(nodes):
    for n in nodes or []:
        yield n
        yield from _walk(getattr(n, "nodelist", None))


def _opt_arg(env: LatexEnvironmentNode) -> str | None:
    args = env.nodeargd.argnlist if env.nodeargd else []
    return args[0].latex_verbatim()[1:-1].strip() if args and args[0] is not None else None


def _span(env: LatexEnvironmentNode) -> tuple[int, int]:
    """Body span of an environment: between the end of \\begin{…}[arg] and the start of \\end{…}."""
    end_tag = env.pos + env.len - len(f"\\end{{{env.environmentname}}}")
    if env.nodelist:
        return env.nodelist[0].pos, end_tag
    return end_tag, end_tag


def split_problems(tex: str) -> list[Problem]:
    nodes, _, _ = LatexWalker(tex, latex_context=_DB, tolerant_parsing=True).get_latex_nodes()
    out = []
    for p in _walk(nodes):
        if not (isinstance(p, LatexEnvironmentNode) and p.environmentname == "problem"):
            continue
        b0, b1 = _span(p)
        meta, sols = {}, []
        for c in p.nodelist:
            if isinstance(c, LatexCommentNode) and ":" in c.comment:
                k, v = c.comment.split(":", 1)
                meta[k.strip()] = v.strip()
            elif isinstance(c, LatexEnvironmentNode) and c.environmentname == "solution":
                s0, s1 = _span(c)
                sols.append(Solution(_opt_arg(c), s0, s1))
        stmt_end = (
            next(c.pos for c in p.nodelist if isinstance(c, LatexEnvironmentNode) and c.environmentname == "solution")
            if sols
            else b1
        )
        stmt = re.sub(r"(?m)^[ \t]*%.*\n?", "", tex[b0:stmt_end]).strip()
        out.append(Problem(_opt_arg(p), p.pos, p.pos + p.len, b0, b1, meta, stmt, sols))
    return out


_OPEN = re.compile(r"\\\[|\\begin\{")
_CLOSE = re.compile(r"\\\]|\\end\{")


def split_steps(tex: str, start: int, end: int, *, by: Literal["paragraph", "line"]) -> list[Step]:
    """Steps of tex[start:end].

    paragraph: bank solutions, steps separated by a blank line.
    line: student work, one step per line; comment lines skipped; a display block
    (\\[ … \\] or \\begin … \\end) spanning several lines is one step.
    """
    spans: list[tuple[int, int]] = []
    if by == "paragraph":
        a = start
        for m in re.finditer(r"\n[ \t]*\n\s*", tex[start:end]):
            spans.append((a, start + m.start()))
            a = start + m.end()
        spans.append((a, end))
    else:
        lines, a = [], start
        for ln in tex[start:end].split("\n"):
            lines.append((a, a + len(ln)))
            a += len(ln) + 1
        i = 0
        while i < len(lines):
            s = tex[lines[i][0] : lines[i][1]].strip()
            if not s or s.startswith("%"):
                i += 1
                continue
            first, depth = i, len(_OPEN.findall(s)) - len(_CLOSE.findall(s))
            while depth > 0 and i + 1 < len(lines):
                i += 1
                t = tex[lines[i][0] : lines[i][1]]
                depth += len(_OPEN.findall(t)) - len(_CLOSE.findall(t))
            spans.append((lines[first][0], lines[i][1]))
            i += 1
    steps = []
    for a, b in spans:
        seg = tex[a:b]
        lead = len(seg) - len(seg.lstrip())
        text = seg.strip()
        if text:
            steps.append(Step(len(steps) + 1, text, a + lead, a + lead + len(text)))
    return steps
