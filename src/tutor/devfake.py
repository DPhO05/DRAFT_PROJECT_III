"""Dev / test backend for `--fake-llm` (SDD §8.8): plausible, schema-valid outputs; no network, no cost.

Never used unless the flag is given. Every call it answers is logged with model "dev-fake".
"""

import difflib
import json
import re
from collections.abc import Iterator
from datetime import date, timedelta

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


def _chat_turn(messages: list[dict]) -> list[dict]:
    """R29 + S15: route on the tutor's last typed message; the tool results after it say which step is next."""
    k = max(i for i, m in enumerate(messages) if m["role"] == "user" and isinstance(m["content"], str))
    asked = messages[k]["content"]
    low = asked.lower()
    done = [json.loads(b["content"]) for m in messages[k + 1 :] if m["role"] == "user" for b in m["content"]
            if b["type"] == "tool_result"]  # fmt: skip
    code = hit.group(0) if (hit := re.search(r"HS-\d+", asked)) else "HS-01"
    if "bịa số" in low:  # a tool first: the number check only runs when one did (R16)
        calls, say = [("student_profile", {"code": code})], f"Tháng này {code} làm đúng 97 bài."
    elif "yếu gì" in low:
        calls, say = [("student_profile", {"code": code})], f"Mình đã xem hồ sơ của {code}, chi tiết ở nguồn bên dưới."
    elif "gợi ý" in low or "phiếu" in low:
        today = date.fromisoformat(re.search(r"Hôm nay: (\d{4}-\d{2}-\d{2})", asked).group(1))
        saturday = today + timedelta(days=(5 - today.weekday()) % 7 or 7)
        n = re.search(r"(\d+) bài", low)
        refs = [i["ref"] for i in done[0].get("items", [])] if done else []
        calls = [("rank_problems", {"code": code} | ({"n": int(n.group(1))} if n else {})),
                 ("propose_worksheet", {"code": code, "for_date": saturday.isoformat(), "refs": refs})]  # fmt: skip
        say = "Mình đã soạn phiếu nháp. Thầy/cô xem lại rồi bấm Tạo phiếu để lưu."
    elif re.search(r"\bai\b", low) and ("sai" in low or "nhầm" in low):
        calls = [("compare_students", {"metric": "open_repeats", "kind": "notational.operator_swap"})]
        say = "Mình đã so sánh lỗi lặp của các học sinh, chi tiết ở nguồn bên dưới."
    elif "tìm" in low:
        calls = [("search_problems", {"text": low.split("tìm", 1)[1].removeprefix(" bài").strip()})]
        say = "Đây là các bài mình tìm được."
    else:
        calls, say = [], "(dev-fake) Mình chưa hiểu câu này, thầy/cô hỏi cách khác giúp mình."
    if len(done) < len(calls):
        name, args = calls[len(done)]
        return [{"type": "tool_use", "id": f"toolu_dev{len(messages)}", "name": name, "input": args}]
    return [{"type": "text", "text": say}]


class DevFakeLLM:
    def __call__(self, *, agent: str, model: str, system: list[str], user: str, schema: type) -> llm.Reply:
        out = schema.model_validate(_answer(agent, system, user))
        raw = out.model_dump_json()
        usage = {"input": (len("".join(system)) + len(user)) // 4, "output": len(raw) // 4, "cache_read": 0,
                 "cache_write": 0}  # fmt: skip
        return llm.Reply(out, raw, usage)

    def chat(
        self, *, agent: str, model: str, system: list[str], tools: list[dict], messages: list[dict]
    ) -> Iterator[dict]:
        content = _chat_turn(messages)
        for b in content:
            if b["type"] == "text":
                for i in range(0, len(b["text"]), 7):
                    yield {"type": "text", "delta": b["text"][i : i + 7]}
        stop = "tool_use" if content[0]["type"] == "tool_use" else "end_turn"
        usage = {"input": len(json.dumps(messages, ensure_ascii=False)) // 4, "output": 20, "cache_read": 0,
                 "cache_write": 0}  # fmt: skip
        yield {"type": "message", "content": content, "stop_reason": stop, "usage": usage}
