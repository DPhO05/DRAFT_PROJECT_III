"""P1-T02: cut problems / solutions / steps with pylatexenc, keep positions."""

import re
from pathlib import Path

from tutor.services import latex

BANK = Path(__file__).resolve().parents[2] / "data" / "dummy" / "bank"
REF_LINE = re.compile(r"^\\begin\{problem\}\[([^\]]+)\]", re.M)


def bank():
    for f in sorted(BANK.glob("*.tex")):
        src = f.read_text(encoding="utf-8")
        yield f, src, latex.split_problems(src)


def test_bank_counts_and_ids_match_source():
    probs = sols = 0
    for f, src, ps in bank():
        assert [p.ref for p in ps] == REF_LINE.findall(src), f.name
        probs += len(ps)
        sols += sum(len(p.solutions) for p in ps)
    assert (probs, sols) == (310, 343)


def test_every_solution_step_is_a_paragraph_with_exact_positions():
    for f, src, ps in bank():
        for p in ps:
            for sol in p.solutions:
                steps = latex.split_steps(src, sol.pos, sol.pos_end, by="paragraph")
                paras = [x.strip() for x in re.split(r"\n\s*\n", src[sol.pos : sol.pos_end]) if x.strip()]
                assert [s.latex for s in steps] == paras, (f.name, p.ref)
                assert all(src[s.pos : s.pos_end] == s.latex for s in steps)
                assert [s.idx for s in steps] == list(range(1, len(steps) + 1))
                assert steps[-1].latex.startswith("Đáp số:")


def test_meta_and_statement():
    src = (BANK / "8-phuong-trinh-bac-nhat.tex").read_text(encoding="utf-8")
    p = latex.split_problems(src)[0]
    assert p.ref == "8DS-PT1-001"
    assert p.meta == {"nguon": "dummy (tự sinh để test)", "lop": "8", "kc_du_kien": "8DS-PT1-01", "do_kho_du_kien": "1"}
    assert p.statement.startswith("Giải các phương trình sau:") and p.statement.endswith("$5x + 8 = 3x - 4$.")
    assert "%" not in p.statement and "solution" not in p.statement
    assert len(latex.split_steps(src, p.solutions[0].pos, p.solutions[0].pos_end, by="paragraph")) == 6


STUDENT = r"""% Bài làm buổi 20/10
\begin{problem}[8DS-PT1-001]
a) $4x - 20 = 0$
% nháp
$4x = 20$

\[
x = 5
\]
Đáp số: $x = 5$
\end{problem}
\begin{problem}
Giải phương trình $2x = 4$.
$x = 2$
\end{problem}
"""


def test_student_work_one_step_per_line_display_block_is_one_step():
    a, b = latex.split_problems(STUDENT)
    assert (a.ref, b.ref) == ("8DS-PT1-001", None)
    steps = latex.split_steps(STUDENT, a.body_pos, a.body_pos_end, by="line")
    assert [s.latex for s in steps] == ["a) $4x - 20 = 0$", "$4x = 20$", "\\[\nx = 5\n\\]", "Đáp số: $x = 5$"]
    assert all(STUDENT[s.pos : s.pos_end] == s.latex for s in steps)
    assert len(latex.split_steps(STUDENT, b.body_pos, b.body_pos_end, by="line")) == 2


def test_problem_mentioned_in_comment_is_not_a_problem():
    assert latex.split_problems("% mẫu: \\begin{problem}[X-001] ... \\end{problem}\n") == []
