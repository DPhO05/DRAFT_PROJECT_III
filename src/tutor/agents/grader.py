"""02 Grader: grade one attempt item by item against the approved rubric; draft a rubric from the model solution."""

from pydantic import BaseModel, Field

from tutor import llm
from tutor.agents import LaneFlag, numbered

INSTRUCTIONS = (
    "Bạn là 02 Grader của trợ lý gia sư Toán. Chấm bài làm của học sinh theo rubric: mỗi mục chỉ đạt (đủ điểm) "
    "hoặc không đạt (0 điểm). Mục đạt phải trích nguyên văn đoạn LaTeX trong bài làm làm bằng chứng; mục không đạt "
    "để trống bằng chứng. score = tổng điểm các mục đạt. Học sinh làm đúng bằng cách khác lời giải mẫu thì vẫn "
    "chấm đạt các mục tương ứng và đặt alt_method = true. Không viết nhận xét, không chép lời giải mẫu ra."
)
EXAMPLE = (
    "Ví dụ chấm. Rubric: [r1] (1 điểm) Chuyển vế: 4x = 20; [r2] (1 điểm) Đáp số x = 5. "
    'Bài làm: [1] $4x = 20$ [2] $x = 4$. Kết quả: r1 đạt, bằng chứng "4x = 20"; r2 không đạt; score = 1; '
    "alt_method = false."
)
RUBRIC_INSTRUCTIONS = (
    "Bạn là 02 Grader của trợ lý gia sư Toán. Từ đề và lời giải mẫu, viết rubric chấm: tách các bước / ý chính "
    "thành mục nhị phân (đạt đủ điểm hoặc 0), mỗi mục bám một bước hoặc một ý của bài con, điểm là số dương. "
    "item_id dạng r1, r2, … theo thứ tự lời giải. Ghi vào alt_methods các cách giải khác được chấp nhận (nếu có)."
)


class GradeItem(BaseModel):
    item_id: str
    passed: bool
    evidence_latex: str = ""


class GradeOut(BaseModel):
    items: list[GradeItem]
    score: float
    alt_method: bool = False


class Grade(BaseModel):
    rubric_version: int | None
    items: list[GradeItem]
    score: float
    max_score: float
    alt_method: bool
    flags: list[LaneFlag]


class RubricItem(BaseModel):
    item_id: str
    text: str
    points: float = Field(gt=0)


class RubricDraftOut(BaseModel):
    items: list[RubricItem] = Field(min_length=1)
    alt_methods: str | None = None


def _rubric_text(rubric: dict) -> str:
    return "\n".join(f"[{i['item_id']}] ({i['points']:g} điểm) {i['text']}" for i in rubric["items"])


def grade(steps: list[dict], problem: dict, rubric: dict, *, ctx: llm.CallContext) -> Grade:
    """rubric: {version, items: [{item_id, text, points}], max_score}. Score is recomputed from the items."""
    points = {i["item_id"]: i["points"] for i in rubric["items"]}
    extra = [
        f"Đề:\n{problem['statement_latex']}",
        f"Lời giải mẫu:\n{problem['solution_latex']}",
        f"Rubric:\n{_rubric_text(rubric)}",
    ]
    flags = []
    try:
        out = llm.call("02", [INSTRUCTIONS, EXAMPLE], GradeOut, extra=extra, student_work=numbered(steps), context=ctx)
    except llm.SchemaFlag as e:
        out = GradeOut(items=[], score=0)
        flags.append(LaneFlag(type="schema", detail=str(e)))
    got = {i.item_id: i for i in out.items if i.item_id in points}
    missing = [k for k in points if k not in got]
    if missing and not flags:
        flags.append(LaneFlag(type="missing_item", detail=f"02 không chấm mục {', '.join(missing)}: tính là không đạt"))
    items = [got.get(k) or GradeItem(item_id=k, passed=False) for k in points]
    score = sum(points[i.item_id] for i in items if i.passed)
    if out.score != score and not flags:
        flags.append(LaneFlag(type="score_mismatch", detail=f"02 ghi {out.score:g}, tổng các mục đạt = {score:g}"))
    if bare := [i.item_id for i in items if i.passed and not i.evidence_latex.strip()]:
        flags.append(LaneFlag(type="no_evidence", detail=f"Mục đạt không có bằng chứng: {', '.join(bare)}"))
    if out.alt_method:
        flags.append(LaneFlag(type="alt_method", detail="02: học sinh làm cách khác lời giải mẫu"))
    return Grade(rubric_version=rubric.get("version"), items=items, score=score, max_score=sum(points.values()),
                 alt_method=out.alt_method, flags=flags)  # fmt: skip


def generate_rubric(problem: dict, *, ctx: llm.CallContext) -> dict | None:
    """{items, max_score, alt_methods} for the teacher to edit and approve; None if 02 failed the schema twice."""
    extra = [f"Đề:\n{problem['statement_latex']}", f"Lời giải mẫu:\n{problem['solution_latex']}"]
    try:
        out = llm.call("02", [RUBRIC_INSTRUCTIONS], RubricDraftOut, extra=extra, context=ctx)
    except llm.SchemaFlag:
        return None
    items = [i.model_dump() for i in out.items]
    return {"items": items, "max_score": sum(i["points"] for i in items), "alt_methods": out.alt_methods}
