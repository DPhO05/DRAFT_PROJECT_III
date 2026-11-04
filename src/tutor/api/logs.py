"""/api/logs: LLM calls and cost from data/logs/llm.jsonl (P2-T08, MONO-P2-02)."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from tutor.llm import cost, iter_log

router = APIRouter(prefix="/api/logs")
Month = Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")]
PARTS = (("Chấm bài", {"01", "02", "03", "04"}), ("Trợ lý", {"00"}), ("Báo cáo", {"09"}))


def _src(request: Request):
    return request.app.state.paths.logs / "llm.jsonl", request.app.state.settings


@router.get("/calls")
def calls(
    request: Request,
    agent: str | None = None,
    graph: str | None = None,
    student: str | None = None,
    thread: str | None = None,
    month: Month = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> dict:
    """Newest first."""
    path, s = _src(request)
    # shortcut: reads the whole file per request; fine for one teacher's log, index it if it grows past ~100k lines.
    rows = list(iter_log(path, s["price_assumption"], by_model=s["price_by_model"], agent=agent, graph=graph,
                         student=student, thread=thread, month=month))  # fmt: skip
    rows.reverse()
    return {"items": rows[offset : offset + limit], "total": len(rows)}


@router.get("/calls/{call_id}")
def call_detail(call_id: int, request: Request) -> dict:
    path, s = _src(request)
    for r in iter_log(path, s["price_assumption"], by_model=s["price_by_model"]):
        if r["id"] == call_id:
            return r
    raise HTTPException(404, f"Không có lời gọi #{call_id} trong llm.jsonl")


@router.get("/cost")
def month_cost(request: Request, month: Month = None) -> dict:
    path, s = _src(request)
    month = month or datetime.now(UTC).strftime("%Y-%m")  # ts in llm.jsonl is UTC
    c = cost(path, s["price_assumption"], month=month, by_model=s["price_by_model"])
    budget = s["budget_usd_month"]
    pct = c["total_usd"] / budget if budget else None
    named = dict.fromkeys((label for label, _ in PARTS), 0.0)
    for agent, a in c["by_agent"].items():
        for label, codes in PARTS:
            if agent in codes:
                named[label] += a["usd"]
    named = {label: round(usd, 6) for label, usd in named.items()}
    # the rest as a remainder, so the four lines add up to total_usd whatever the per-agent rounding
    rest = max(0.0, round(c["total_usd"] - sum(named.values()), 6))
    ratio = round(pct or 0, 6)  # 5.6 / 7 is 0.7999999999999999 and counts as 80 %
    return {
        "month": month,
        **c,
        "budget_usd": budget,
        "pct": pct,
        "warning": None if ratio < 0.8 else "over" if ratio >= 1 else "near",
        "parts": [{"label": label, "usd": usd} for label, usd in {**named, "Khác": rest}.items()],
        "prices": s["price_assumption"],
        "price_by_model": s["price_by_model"],
        "assumption": True,
    }
