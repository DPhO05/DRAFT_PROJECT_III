"""The faithfulness judge with the fake model (C-34): one verdict per sentence, names masked (C-40)."""

from tests.eval import judges
from tests.fakes import FakeLLM
from tutor import llm

CTX = llm.CallContext(graph=None, redact={"Nguyễn Văn An": "HS-01"})


def fake(verdicts):
    items = [judges.Verdict(i=i, verdict=v, reason="r") for i, v in verdicts]
    backend = FakeLLM({"judge": judges.Verdicts(items=items)})
    llm.set_backend(backend)
    return backend


def test_one_verdict_per_sentence_and_the_score(tmp_path):
    llm.configure(tmp_path / "llm.jsonl", {})
    fake([(1, "supported"), (2, "not_supported"), (3, "unknown")])
    out = judges.faithfulness("F01 · Số buổi học: 2.", ["a", "b", "c", "d"], CTX)
    assert [v["verdict"] for v in out["verdicts"]] == ["supported", "not_supported", "unknown", "unknown"]
    assert (out["score"], out["unknown"]) == (1 / 4, 2)
    [row] = llm.iter_log(tmp_path / "llm.jsonl")
    assert row["agent"] == "judge" and row["prompt_version"].startswith("judge-")


def test_no_sentence_means_no_call(tmp_path):
    llm.configure(tmp_path / "llm.jsonl", {})
    backend = fake([])
    assert judges.faithfulness("x", [], CTX) == {"verdicts": [], "score": None, "unknown": 0}
    assert backend.count["judge"] == 0


def test_names_are_masked_before_the_judge(tmp_path):
    llm.configure(tmp_path / "llm.jsonl", {})
    backend = fake([(1, "supported")])
    judges.faithfulness("Nguyễn Văn An làm 4 trong 6 ý.", ["Bạn Nguyen Van An tiến bộ."], CTX)
    [row] = llm.iter_log(tmp_path / "llm.jsonl")
    assert "Văn An" not in row["user"] and "Van An" not in row["user"] and row["name_masked"] is True
    assert "HS-01" in backend.calls[0]["user"]


def test_schema_failure_gives_unknown_verdicts(tmp_path):
    llm.configure(tmp_path / "llm.jsonl", {})
    llm.set_backend(FakeLLM({"judge": None}))
    out = judges.faithfulness("x", ["a"], CTX)
    assert [v["verdict"] for v in out["verdicts"]] == ["unknown"] and out["score"] == 0


def test_oracle_supports_every_sentence(tmp_path):
    llm.configure(tmp_path / "llm.jsonl", {})
    llm.set_backend(FakeLLM({"judge": judges.oracle}))
    assert judges.faithfulness("x", ["a", "b"], CTX)["score"] == 1
