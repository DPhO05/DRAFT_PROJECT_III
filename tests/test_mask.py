"""P6-T02: masking of every student name before an agent 00 call."""

import json

from tests.fakes import FakeLLM
from tutor import llm

MINH = {"Nguyễn Văn Minh": "HS-03"}


def test_full_name_to_code():
    assert llm.mask("Nguyễn Văn Minh làm sai", MINH) == "HS-03 làm sai"
    assert llm.mask("NGUYEN VAN MINH", MINH) == "HS-03"


def test_short_word_untouched():
    assert llm.mask("chứng minh rằng", MINH) == "chứng minh rằng"


def test_same_given_name_other_family():
    redact = MINH | {"Trần Văn Minh": "HS-05"}
    assert llm.mask("Trần Văn Minh và Nguyễn Văn Minh", redact) == "HS-05 và HS-03"


def test_nested_names_longest_wins():
    redact = {"Văn Minh": "HS-02"} | MINH
    assert llm.mask("Nguyễn Văn Minh làm sai, Văn Minh đúng", redact) == "HS-03 làm sai, HS-02 đúng"


def test_chat_masks_pasted_tex(tmp_path):
    llm.configure(tmp_path / "llm.jsonl", {})
    fake = FakeLLM({"00": [[{"type": "text", "text": "Đã nhận."}]]})
    llm.set_backend(fake)
    tex = "Chấm giúp: \\begin{problem}[8DS-PT1-001] Bài làm của Nguyễn Văn Minh: $4x=20$ \\end{problem}"
    ctx = llm.CallContext(graph=None, conversation_id="2026-11-01-1", redact=MINH)
    list(llm.chat("00", ["f"], [], [{"role": "user", "content": tex}], run_tool=lambda n, i: ("", False),
                  context=ctx, max_tool_turns=8))  # fmt: skip
    sent = json.dumps(fake.calls, ensure_ascii=False)
    assert "Văn Minh" not in sent and "HS-03" in sent


def test_name_split_by_line_break_or_double_space():
    assert llm.mask("Nguyễn Văn\nAn làm sai", {"Nguyễn Văn An": "HS-01"}) == "HS-01 làm sai"
    assert llm.mask("Nguyễn  Văn   An", {"Nguyễn Văn An": "HS-01"}) == "HS-01"


def test_mask_latex_spaced_names():
    redact = {"Nguyễn Văn An": "HS-01"}
    for text in ("Nguyễn~Văn~An", "Nguyễn\\ Văn\\ An", "Nguyễn\\,Văn~An", "nguyen~van an"):
        assert llm.mask(text, redact) == "HS-01"
    assert llm.mask("An~ và Nguyễn~", redact) == "An~ và Nguyễn~"


def test_mask_name_split_by_braces():
    redact = {"Nguyễn Văn An": "HS-01"}
    for text in ("\\textbf{Nguyễn} Văn An", "{Nguyễn}{Văn}{An}"):
        out = llm.mask(text, redact)
        assert "HS-01" in out and "Nguyễn" not in out
