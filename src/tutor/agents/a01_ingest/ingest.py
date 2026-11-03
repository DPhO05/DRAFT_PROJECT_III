"""01 Ingest (.tex): cut problems and steps, match problems to the bank, flag what the teacher must confirm."""

from typing import Literal

from pydantic import BaseModel, Field

from tutor import llm
from tutor.services import latex

LOW_MATCH = 0.8  # C-12 threshold (proposal): best candidate below it -> low_match
INSTRUCTIONS = (
    "Bạn là 01 Ingest của trợ lý gia sư Toán. Học sinh nộp một bài làm không ghi mã bài. "
    "So phần đề / lời giải học sinh chép với danh sách đề trong ngân hàng bên dưới, "
    "trả tối đa 3 mã bài (ref) giống nhất kèm điểm từ 0 đến 1 (1 = chắc chắn cùng một bài). "
    "Chỉ dùng mã có trong danh sách. Không có bài nào giống thì trả danh sách rỗng."
)


class Candidate(BaseModel):
    ref: str
    score: float = Field(ge=0, le=1)


class MatchResult(BaseModel):
    candidates: list[Candidate]


class StepOut(BaseModel):
    idx: int
    latex: str
    pos: int
    pos_end: int


class Attempt(BaseModel):
    seq: int
    ref: str | None
    problem_id: int | None
    pos: int
    pos_end: int
    steps: list[StepOut]
    candidates: list[Candidate] = []


class Flag(BaseModel):
    type: Literal["low_match", "mismatch", "no_rubric"]
    seq: int
    detail: str
    resolved: bool = False


class IngestResult(BaseModel):
    attempts: list[Attempt]
    flags: list[Flag]


def run(tex: str, bank: list[dict], *, grade: int | None, ctx: llm.CallContext) -> IngestResult:
    """bank: repo.bank_problems() rows. The transcript is the source file itself (FR1), never rewritten."""
    by_ref = {b["ref"]: b for b in bank}
    problems = latex.split_problems(tex)
    if not problems:
        raise ValueError("File không có \\begin{problem} nào")
    pool = [b for b in bank if grade is None or b["ref"].startswith(str(grade))] or bank
    fixed = [INSTRUCTIONS, "\n".join(f"[{b['ref']}] {b['statement_latex']}" for b in pool)]
    attempts, flags = [], []
    for seq, p in enumerate(problems, 1):
        steps = latex.split_steps(tex, p.body_pos, p.body_pos_end, by="line")
        ref, cands = (p.ref if p.ref in by_ref else None), []
        if ref is None:
            out = llm.call("01", fixed, MatchResult, student_work=tex[p.body_pos : p.body_pos_end], context=ctx)
            cands = sorted((c for c in out.candidates if c.ref in by_ref), key=lambda c: -c.score)[:3]
            if cands and cands[0].score >= LOW_MATCH:
                ref = cands[0].ref
            else:
                why = f"mã bài lạ {p.ref}" if p.ref else "không ghi mã bài"
                best = ", ".join(f"{c.ref} ({c.score:.2f})" for c in cands) or "không có ứng viên"
                flags.append(Flag(type="low_match", seq=seq, detail=f"Bài {seq}: {why}; ứng viên: {best}"))
        if ref is not None and not by_ref[ref]["has_rubric"]:
            flags.append(Flag(type="no_rubric", seq=seq, detail=f"Bài {seq} ({ref}) chưa có rubric đã duyệt"))
        attempts.append(
            Attempt(
                seq=seq,
                ref=ref,
                problem_id=by_ref[ref]["id"] if ref else None,
                pos=p.pos,
                pos_end=p.pos_end,
                steps=[StepOut(idx=s.idx, latex=s.latex, pos=s.pos, pos_end=s.pos_end) for s in steps],
                candidates=cands,
            )
        )
    return IngestResult(attempts=attempts, flags=flags)
