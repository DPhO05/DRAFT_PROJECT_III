"""04 Verifier: one independent pass per mistake; sees only 03's conclusion, never its reasoning or prompt."""

from typing import Literal

from pydantic import BaseModel

from tutor import llm
from tutor.agents import numbered

INSTRUCTIONS = (
    "Bạn là 04 Verifier của trợ lý gia sư Toán. Bạn nhận một kết luận về một lỗi trong bài làm của học sinh. "
    "Tự kiểm tra lại: bước đó có thật sự sai không, mã lỗi có đúng không. Trả verdict: agree (bước sai và mã "
    "đúng), wrong_code (bước sai nhưng mã khác, ghi suggested_code chỉ trong bảng mã), disagree (bước không sai). "
    "Không chắc thì chọn disagree. reason: 1 câu ngắn. Không sửa bài, không viết nhận xét cho học sinh."
)

Verdicts = Literal["agree", "disagree", "wrong_code"]


class VerdictOut(BaseModel):
    verdict: Verdicts
    reason: str
    suggested_code: str | None = None


class Verdict(BaseModel):
    verdict: Verdicts | None  # None: 04 failed the schema twice, or the call failed
    reason: str
    suggested_code: str | None


def run(mistake: dict, steps: list[dict], problem: dict, *, codes: list[dict], ctx: llm.CallContext) -> Verdict:
    table = "Bảng mã lỗi:\n" + "\n".join(f"- {c['code']}: {c['description']}" for c in codes)
    kc = f", KC {mistake['kc_id']}" if mistake.get("kc_id") is not None else ""
    claim = (
        f"Kết luận cần kiểm: bước {mistake['step_idx']}, mã {mistake['code']}{kc}. "
        f"Mô tả: {mistake['description']}. Đoạn sai: {mistake['evidence_latex']}"
    )
    extra = [f"Đề:\n{problem['statement_latex']}", f"Lời giải mẫu:\n{problem['solution_latex']}", claim]
    try:
        out = llm.call("04", [INSTRUCTIONS, table], VerdictOut, extra=extra, student_work=numbered(steps), context=ctx)
    except (llm.KeyRejected, llm.BadRequest):
        raise
    except (llm.SchemaFlag, llm.LLMUnavailable) as e:
        return Verdict(verdict=None, reason=str(e), suggested_code=None)
    active = {c["code"] for c in codes}
    return Verdict(verdict=out.verdict, reason=out.reason,
                   suggested_code=out.suggested_code if out.suggested_code in active else None)  # fmt: skip


def order_queue(cards: list[dict], low_confidence: float) -> list[dict]:
    """Review order (P2-T04): 04 disputed / wrong code / no verdict, then confidence < threshold, then the rest."""

    def key(c: dict) -> tuple:
        verdict = (c.get("verifier") or {}).get("verdict")
        group = 0 if verdict != "agree" else 1 if c["confidence"] < low_confidence else 2
        return group, c["attempt_seq"], c["step_idx"]

    return sorted(cards, key=key)
