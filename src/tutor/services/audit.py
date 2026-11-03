"""Number check (P6-T06): numbers in an answer that no tool result holds. Pure text, no DB; P7 checks each sentence."""

import json
import re
from collections.abc import Iterable

# "." is a thousands mark only in 1.000 / 12.345.678 (never after a leading 0); "," is the decimal mark
_NUM = r"[1-9]\d{0,2}(?:\.\d{3})+(?!\d)(?:,\d+)?|\d+(?:[.,]\d+)?"
_TOKEN = re.compile(rf"(?<![\w.,])(?:{_NUM})(?:/(?:{_NUM}))*%?")
# problem refs / student codes: first segment holds a letter, a digit somewhere (so not 2026-10-07T14 or 10-A)
_CODE_PAT = r"(?<![\w-])(?=[\w-]*\d)[0-9]*[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+(?![\w-])"
# never audited in the answer: LaTeX, codes, list markers
_IGNORED = re.compile(rf"(?s:\$\$.+?\$\$)|\$[^$\n]+\$|{_CODE_PAT}|(?m:^[ \t]*\d+[.)](?=[ \t]))")
_CODE = re.compile(_CODE_PAT)
_SENTENCE = re.compile(r"\S[^\n]*?(?:[.!?…]+(?=\s)|$)", re.M)
# a digit run after a letter or digit belongs to a name (kc2), except "_10" (score_10) and the hour of 2026-10-07T14
_PLAIN = re.compile(r"(?:(?<![^\W_.])|(?<=\dT))\d+(?:\.\d+)?")
_DATE = re.compile(r"\d{1,2}/\d{1,2}(?:/\d{4})?")
PRAISE = ("xuất sắc", "tuyệt vời", "hoàn hảo", "rất tốt", "rất giỏi")


def values(token: str) -> set[float]:
    """Readings of one number: "0,5" -> {0.5}, "1.000" -> {1000}, "40%" -> {40, 0.4}."""
    pct = token.endswith("%")
    text = token.rstrip("%")
    if re.fullmatch(r"[1-9]\d{0,2}(?:\.\d{3})+(?:,\d+)?", text):
        text = text.replace(".", "")
    out = float(text.replace(",", "."))
    return {out, out / 100} if pct else {out}


def _parts(token: str) -> list[str]:
    """Split a fraction or date into its numbers; a trailing "%" goes to the last part."""
    parts = token.rstrip("%").split("/")
    if token.endswith("%"):
        parts[-1] += "%"
    return parts


def known_numbers(texts: Iterable[str]) -> set[float]:
    """Every number in the strings (tool-result JSON), dates and fraction parts included."""
    out: set[float] = set()
    for raw in texts:
        text = _CODE.sub(lambda m: "_" * len(m.group()), raw)  # digits of HS-05 / 9DS-PT2-012 are not data
        for tok in _TOKEN.finditer(text):
            for part in _parts(tok.group()):
                out |= values(part)
        # JSON writes decimals with ".", and "[3,4]" holds two numbers, not 3.4
        out |= {float(n) for n in _PLAIN.findall(text)}
    return out


def unverified(text: str, known: set[float]) -> list[dict]:
    """Sentences holding a number outside `known`: [{"sentence", "numbers": [original tokens]}]."""
    seen = {round(k, 6) for k in known}
    masked = _IGNORED.sub(lambda m: "_" * len(m.group()), text)
    out = []
    for sentence in _SENTENCE.finditer(masked):
        bad = [
            tok.group()
            for tok in _TOKEN.finditer(sentence.group())
            if not all(any(round(v, 6) in seen for v in values(p)) for p in _parts(tok.group()))
        ]
        if bad:
            out.append({"sentence": text[sentence.start() : sentence.end()], "numbers": list(dict.fromkeys(bad))})
    return out


def check_sentence(text: str, cited: list[dict], *, low: bool, need_fact: bool) -> dict | None:
    """Report sentence vs cited facts (C-41): None = pass, else the first flag of percent, no_fact, number, tone."""
    if "%" in text:
        return {"flag": "percent", "why": "Báo cáo cho phụ huynh không dùng phần trăm.", "detail": "câu có dấu %"}
    if need_fact and not cited:
        return {"flag": "no_fact", "why": "Câu chưa dựa vào số liệu đã duyệt.", "detail": "câu không trích fact nào"}
    # facts write scores "x trong y", so stripping d/m dates cannot eat a score
    known = known_numbers(json.dumps(f["value"], ensure_ascii=False) for f in cited)
    bad = [n for u in unverified(_DATE.sub(" ", text), known) for n in u["numbers"]]
    if bad:
        shown = ", ".join(f"{f['fact_id']} = {json.dumps(f['value'], ensure_ascii=False)}" for f in cited)
        return {
            "flag": "number",
            "why": f"Số {', '.join(f'“{n}”' for n in bad)} không có trong dữ liệu đã duyệt.",
            "detail": f"số {', '.join(bad)} không khớp {shown}",
        }
    praised = [w for w in PRAISE if w in text.lower()]
    if low and praised:
        return {
            "flag": "tone",
            "why": "Câu khen hơi quá so với kết quả kỳ này.",
            "detail": "kết quả kỳ thấp, câu có: " + ", ".join(praised),
        }
    return None
