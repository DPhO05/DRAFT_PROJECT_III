"""Number check (P6-T06): numbers in an answer that no tool result holds. Pure text, no DB; P7 checks each sentence."""

import json
import re
import unicodedata
from collections.abc import Iterable
from datetime import date

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
# m/yyyy or dd/mm[/yyyy]: zero-padded as facts write dates, so a score like 7/10 is never a date;
# not glued to a digit, "," or ".", so "8,05/10" and "10/2026" keep their numbers
_DATE = re.compile(r"(?<![\d,.])(?:(?P<m>\d{1,2})/(?P<y>\d{4})|(?P<d>\d\d)/(?P<mo>\d\d)(?:/\d{4})?)(?!\d)")
# number words the digit check cannot see; một, ba, năm are left out: they mean other things too
_WORDS = re.compile(r"(?<!\w)(?:hai|bốn|sáu|bảy|tám|chín|mười|mươi|trăm)(?!\w)", re.IGNORECASE)
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


def _drop_dates(text: str, dates: Iterable[date]) -> str:
    """Blank out dd/mm[/yyyy] naming a day of `dates` and m/yyyy naming one of their months (dd/mm ignores the year)."""
    days = {(d.day, d.month) for d in dates}
    months = {(d.month, d.year) for d in dates}

    def drop(m: re.Match) -> str:
        real = (int(m["m"]), int(m["y"])) in months if m["m"] else (int(m["d"]), int(m["mo"])) in days
        return " " if real else m.group()

    return _DATE.sub(drop, text)


def check_sentence(text: str, cited: list[dict], *, low: bool, need_fact: bool, dates: Iterable[date]) -> dict | None:
    """Report sentence vs cited facts (C-41): None = pass, else the first flag of percent, no_fact, number, tone.

    A number written in words (hai, sáu, bảy…) is flagged `number`: it cannot be checked against the facts,
    unless a cited fact's text holds the same word (a skill name).

    `dates` = the report's real days (period bounds, session days, previous span); only those are exempt from the check.
    """
    text = unicodedata.normalize("NFC", text)  # a typed "bảy" may be b-a + combining hook
    if "%" in text or "phần trăm" in text.lower():
        return {
            "flag": "percent",
            "why": "Báo cáo cho phụ huynh không dùng phần trăm.",
            "detail": "câu có dấu %" if "%" in text else "câu có chữ phần trăm",
        }
    if need_fact and not cited:
        return {"flag": "no_fact", "why": "Câu chưa dựa vào số liệu đã duyệt.", "detail": "câu không trích fact nào"}
    known = known_numbers(json.dumps(f["value"], ensure_ascii=False) for f in cited)
    bad = [n for u in unverified(_drop_dates(text, dates), known) for n in u["numbers"]]
    if bad:
        shown = ", ".join(f"{f['fact_id']} = {json.dumps(f['value'], ensure_ascii=False)}" for f in cited)
        return {
            "flag": "number",
            "why": f"Số {', '.join(f'“{n}”' for n in bad)} không có trong dữ liệu đã duyệt.",
            "detail": f"số {', '.join(bad)} không khớp {shown}",
        }
    # shortcut: a word in a cited fact's text (a skill name like "bậc hai") is known for the whole sentence, so a
    # real "hai" beside it passes; upgrade by masking the fact's names out of the sentence first
    known_words = {w.lower() for f in cited for w in _WORDS.findall(unicodedata.normalize("NFC", f["text"]))}
    if words := [w for w in dict.fromkeys(_WORDS.findall(text)) if w.lower() not in known_words]:
        shown = ", ".join(f"“{w}”" for w in words)
        return {
            "flag": "number",
            "why": f"Số viết bằng chữ ({shown}): viết bằng chữ số để kiểm được.",
            "detail": "số viết bằng chữ: " + ", ".join(words),
        }
    praised = [w for w in PRAISE if w in text.lower()]
    if low and praised:
        return {
            "flag": "tone",
            "why": "Câu khen hơi quá so với kết quả kỳ này.",
            "detail": "kết quả kỳ thấp, câu có: " + ", ".join(praised),
        }
    return None
