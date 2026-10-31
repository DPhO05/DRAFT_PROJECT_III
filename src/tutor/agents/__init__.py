"""Agents 01–09: fixed prompt + Pydantic output + run(); proposals only, never write the DB."""

from pydantic import BaseModel

from tutor.llm import CallContext, LLMUnavailable, SchemaFlag


class LaneFlag(BaseModel):
    """Something the code check found in an agent's output; shown to the teacher at review."""

    type: str
    detail: str


def numbered(steps: list[dict]) -> str:
    """Student steps as sent to 02 · 03 · 04: one '[idx] latex' line per step."""
    return "\n".join(f"[{s['idx']}] {s['latex']}" for s in steps)


__all__ = ["CallContext", "LLMUnavailable", "LaneFlag", "SchemaFlag", "numbered"]
