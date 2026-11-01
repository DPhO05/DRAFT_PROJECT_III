"""Dev / test backend for `--fake-llm` (SDD §8.8): plausible, schema-valid outputs; no network, no cost.

Never used unless the flag is given. Every call it answers is logged with model "dev-fake".
"""

import difflib
import re

from tutor import llm

MODEL = "dev-fake"


def models() -> dict[str, str]:
    return {f"{i:02d}": MODEL for i in range(0, 5)}


def _section(user: str, title: str) -> str:
    """Text of one 'Title:\\n…' block of the user turn (blocks are separated by a blank line)."""
    end = rf"(?=\n\n\S[^\n]*:\n|\n\n{re.escape(llm.OPEN[:3])}|\Z)"
    m = re.search(rf"(?:^|\n){re.escape(title)}:\n(.*?){end}", user, re.S)
    return m.group(1) if m else ""


def _work(user: str) -> str:
    return user.split(llm.OPEN, 1)[1].split(llm.CLOSE, 1)[0] if llm.OPEN in user else ""


def _steps(user: str) -> list[tuple[int, str]]:
    return [(int(i), t) for i, t in re.findall(r"^\[(\d+)\] (.*)$", _work(user), re.M)]


def _answer(agent: str, system: list[str], user: str) -> dict:
    if agent == "01":
        parts = re.split(r"^\[([0-9]+DS-[^\]]+)\] ", system[-1], flags=re.M)[1:]
        bank = list(zip(parts[::2], parts[1::2], strict=True))
        work = _work(user).strip()
        scored = sorted(((difflib.SequenceMatcher(None, work[: len(st) + 20], st).ratio(), ref) for ref, st in bank),
                        reverse=True)  # fmt: skip
        # capped under the 0.8 match threshold so the teacher always sees the step-3 choice
        return {"candidates": [{"ref": ref, "score": round(min(s, 0.79), 2)} for s, ref in scored[:3]]}
    if agent == "02" and "Rubric:" in user:
        items = re.findall(r"^\[(\w+)\] \(([\d.]+) điểm\)", _section(user, "Rubric"), re.M)
        steps = _steps(user)
        evidence = steps[0][1] if steps else "—"
        passed = [i for i, _ in items[:-1]] if len(items) > 1 else []
        return {"items": [{"item_id": i, "passed": i in passed, "evidence_latex": evidence if i in passed else ""}
                          for i, _ in items],
                "score": sum(float(p) for i, p in items if i in passed), "alt_method": False}  # fmt: skip
    if agent == "02":
        paras = [p.strip() for p in _section(user, "Lời giải mẫu").split("\n\n") if p.strip()] or ["Đáp số"]
        return {"items": [{"item_id": f"r{k}", "text": p, "points": 1} for k, p in enumerate(paras, 1)]}
    if agent == "03":
        steps = _steps(user)
        codes = re.findall(r"^- ([a-z]+\.[a-z_]+) ", system[-1], re.M)
        kcs = [int(k) for k in re.findall(r"^\[(\d+)\] ", _section(user, "KC của bài (kc_id)"), re.M)]
        if not steps or not codes:
            return {"corrected_latex": "", "mistakes": []}
        idx, text = steps[-1]
        code = "computational.final_answer" if "computational.final_answer" in codes else codes[0]
        return {"corrected_latex": "(dev-fake: không viết lại)", "mistakes": [
            {"step_idx": idx, "code": code, "kc_id": kcs[0] if kcs else None, "evidence_latex": text,
             "description": "dev-fake: lỗi mẫu ở bước cuối", "confidence": 0.55}]}  # fmt: skip
    if agent == "04":
        return {"verdict": "agree", "reason": "dev-fake: đồng ý"}
    raise NotImplementedError(f"--fake-llm chưa có output cho agent {agent}")


class DevFakeLLM:
    def __call__(self, *, agent: str, model: str, system: list[str], user: str, schema: type) -> llm.Reply:
        out = schema.model_validate(_answer(agent, system, user))
        raw = out.model_dump_json()
        usage = {"input": (len("".join(system)) + len(user)) // 4, "output": len(raw) // 4, "cache_read": 0,
                 "cache_write": 0}  # fmt: skip
        return llm.Reply(out, raw, usage)
