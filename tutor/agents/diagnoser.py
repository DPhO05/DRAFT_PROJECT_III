"""03 Diagnoser: find the first wrong step and the other wrong steps, tag each with an active error code."""

from pydantic import BaseModel, Field

from tutor import llm
from tutor.agents import LaneFlag, numbered

INSTRUCTIONS = (
    "Bạn là 03 Diagnoser của trợ lý gia sư Toán. Bài làm của học sinh chia bước, mỗi dòng [i] là bước i.\n"
    "Lượt 1 (corrected_latex): viết lại lời giải ĐÚNG theo chính cách làm của học sinh, chỉ sửa tối thiểu, "
    "giữ đánh số bước.\n"
    "Lượt 2 (mistakes): so bài làm với bản vừa sửa, liệt kê bước sai đầu tiên và mọi bước sai khác. Mỗi lỗi: "
    "step_idx (số bước trong bài làm), code (chỉ dùng mã trong bảng mã lỗi bên dưới), kc_id (chỉ chọn trong danh "
    "sách KC của bài; null nếu là lỗi trình bày chung), description (mô tả ngắn), evidence_latex (trích nguyên văn "
    "đoạn LaTeX sai trong bài làm), confidence từ 0 đến 1. Lỗi kéo theo từ một lỗi trước dùng mã "
    "computational.propagated. Bài không có lỗi thì mistakes rỗng. Lịch sử lỗi chỉ để tham khảo, không suy lỗi từ "
    "lịch sử."
)


class MistakeOut(BaseModel):
    step_idx: int
    code: str
    kc_id: int | None
    description: str
    evidence_latex: str
    confidence: float = Field(ge=0, le=1)


class DiagnosisOut(BaseModel):
    corrected_latex: str  # pass 1 comes first so the model rewrites before it compares (Srivatsa et al. 2025)
    mistakes: list[MistakeOut]


class Diagnosis(BaseModel):
    corrected_latex: str
    mistakes: list[MistakeOut]
    flags: list[LaneFlag]


def fixed_prompt(codes: list[dict]) -> list[str]:
    """codes: active error codes. Their text and examples are the cached, versioned part of 03's prompt."""
    lines = []
    for c in codes:
        ex = f" Ví dụ: {c['example']}" if c.get("example") else ""
        lines.append(f"- {c['code']} ({c['category']}): {c['description']}.{ex}")
    return [INSTRUCTIONS, "Bảng mã lỗi đang dùng:\n" + "\n".join(lines)]


def prompt_version(codes: list[dict]) -> str:
    return llm.prompt_version("03", fixed_prompt(codes))


def run(
    steps: list[dict],
    problem: dict,
    *,
    codes: list[dict],
    history: list[dict],
    failed_items: list[str],
    ctx: llm.CallContext,
) -> Diagnosis:
    """problem: {statement_latex, solution_latex, kcs: [{id, code, name}]}; history: repo.recent_mistakes()."""
    kcs = {k["id"] for k in problem["kcs"]}
    extra = [
        f"Đề:\n{problem['statement_latex']}",
        f"Lời giải mẫu:\n{problem['solution_latex']}",
        "KC của bài (kc_id):\n" + "\n".join(f"[{k['id']}] {k['code']} {k['name']}" for k in problem["kcs"]),
        "Mục rubric học sinh chưa đạt (theo 02):\n" + ("\n".join(f"- {t}" for t in failed_items) or "(không có)"),
        "5 lỗi đã duyệt gần nhất của học sinh (tham khảo):\n"
        + ("\n".join(f"- {h['held_on']} {h['code']}: {h['description']}" for h in history) or "(chưa có)"),
    ]
    try:
        out = llm.call("03", fixed_prompt(codes), DiagnosisOut, extra=extra, student_work=numbered(steps), context=ctx)
    except llm.SchemaFlag as e:
        return Diagnosis(corrected_latex="", mistakes=[], flags=[LaneFlag(type="schema", detail=str(e))])
    active, idxs = {c["code"] for c in codes}, {s["idx"] for s in steps}
    kept, flags = [], []
    for m in out.mistakes:
        if m.code not in active:
            flags.append(LaneFlag(type="bad_code", detail=f"Bỏ lỗi bước {m.step_idx}: mã {m.code} không đang bật"))
        elif m.kc_id is not None and m.kc_id not in kcs:
            flags.append(LaneFlag(type="bad_kc", detail=f"Bỏ lỗi bước {m.step_idx}: KC {m.kc_id} không thuộc bài"))
        elif m.step_idx not in idxs:
            flags.append(LaneFlag(type="bad_step", detail=f"Bỏ lỗi: bài làm không có bước {m.step_idx}"))
        else:
            kept.append(m)
    return Diagnosis(corrected_latex=out.corrected_latex, mistakes=kept, flags=flags)
