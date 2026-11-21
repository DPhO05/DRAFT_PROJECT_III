"""Judge calibration (design 7.2, 7.3): the sample hides verdicts, the fake judge fills them."""

import csv
import json

from tests.eval import calibrate


def verdicts(kinds: list[str]) -> dict:
    return {
        "verdicts": [{"i": i, "verdict": k, "reason": ""} for i, k in enumerate(kinds, 1)],
        "score": None,
        "unknown": 0,
    }


def result_09(kinds: list[str], sentences=None) -> dict:
    """One 09 run, one report: sentence i is judged kinds[i]."""
    sentences = sentences or [f"Em tăng {i} điểm." for i in range(len(kinds))]
    row = {"key": "p1", "facts_block": "F01 · Số liệu.", "sentences": sentences, "judge": verdicts(kinds)}
    return {"reports": [[row]]}


def sample(tmp_path, result: dict, *extra: str) -> tuple[list[dict], dict]:
    tmp_path.mkdir(exist_ok=True)
    src, out = tmp_path / "result.json", tmp_path / "out"
    src.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    assert calibrate.main(["sample", "--from", str(src), "--out", str(out), *extra]) == 0
    with next(out.glob("*-human.csv")).open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(next(out.glob("*-judge.json")).read_text(encoding="utf-8"))


def files(tmp_path):
    out = tmp_path / "out"
    return next(out.glob("*-human.csv")), next(out.glob("*-judge.json"))


def test_sample_is_balanced_and_hides_verdicts(tmp_path):
    rows, judged = sample(tmp_path, result_09(["supported"] * 20 + ["not_supported"] * 20), "--n", "30")
    assert len(rows) == 30 and all(r["human"] == "" for r in rows)
    assert (
        next((tmp_path / "out").glob("*-human.csv")).read_text(encoding="utf-8").splitlines()[0]
        == "id,context,sentence,human"
    )
    assert sum(j["verdict"] == "supported" for j in judged.values()) == 15
    assert set(judged) == {r["id"] for r in rows}


def test_sample_makes_wrong_sentences_when_short(tmp_path):
    originals = [f"Em tăng {i} điểm." for i in range(20)] + [f"Bài {i} đã vững." for i in range(20)]
    rows, judged = sample(tmp_path, result_09(["supported"] * 40, originals), "--n", "30")
    made = [i for i, j in judged.items() if j["verdict"] is None]
    assert len(made) == 15 and all(judged[i]["truth"] == "not_supported" for i in made)
    by_id = {r["id"]: r["sentence"] for r in rows}
    assert all(by_id[i] not in originals for i in made)
    assert not any(j["truth"] for i, j in judged.items() if i not in made)


def test_sample_reads_00_and_09_results(tmp_path):
    kinds = ["supported", "not_supported"]
    answers = [
        [{"id": "q1", "judge": verdicts(kinds), "judge_context": "Ngữ cảnh 00", "judge_sentences": ["a.", "b."]}]
    ]
    rows, _ = sample(tmp_path / "a", {"answers": answers}, "--n", "2")
    assert {r["context"] for r in rows} == {"Ngữ cảnh 00"} and {r["sentence"] for r in rows} == {"a.", "b."}
    rows, _ = sample(tmp_path / "b", result_09(kinds, ["c.", "d."]), "--n", "2")
    assert {r["context"] for r in rows} == {"F01 · Số liệu."} and {r["sentence"] for r in rows} == {"c.", "d."}


def test_sample_skips_failed_judge_calls(tmp_path):
    bad = {"verdicts": [], "score": None, "unknown": 0, "error": "LLMUnavailable: down"}
    res = result_09(["supported", "not_supported"])
    res["reports"][0].append({"key": "p2", "facts_block": "x", "sentences": ["lỗi."], "judge": bad})
    rows, _ = sample(tmp_path, res, "--n", "2")
    assert "lỗi." not in {r["sentence"] for r in rows}


def test_judge_fills_null_verdicts_with_the_fake(tmp_path):
    sample(tmp_path, result_09(["supported"] * 40), "--n", "30")
    human, judged = files(tmp_path)
    assert calibrate.main(["judge", str(human), str(judged), "--backend", "fake"]) == 0
    assert all(j["verdict"] for j in json.loads(judged.read_text(encoding="utf-8")).values())


def test_judge_real_needs_yes_and_a_model(tmp_path):
    sample(tmp_path, result_09(["supported"] * 40), "--n", "30")
    human, judged = files(tmp_path)
    before = judged.read_bytes()
    assert calibrate.main(["judge", str(human), str(judged), "--backend", "real", "--judge-model", "openai:x"]) == 2
    assert calibrate.main(["judge", str(human), str(judged), "--backend", "real", "--yes"]) == 2
    assert judged.read_bytes() == before


def pairs_files(tmp_path, human_judge: list[tuple[str, str]], name="human.csv"):
    ids = [f"s{i}" for i in range(len(human_judge))]
    h = tmp_path / name
    with h.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, ["id", "context", "sentence", "human"])
        w.writeheader()
        w.writerows(
            {"id": i, "context": "c", "sentence": "s", "human": p[0]} for i, p in zip(ids, human_judge, strict=True)
        )
    j = tmp_path / "judge.json"
    j.write_text(
        json.dumps({i: {"verdict": p[1], "truth": None} for i, p in zip(ids, human_judge, strict=True)}),
        encoding="utf-8",
    )
    return h, j


S, N = "supported", "not_supported"
THIRTY = [(S, S)] * 12 + [(N, N)] * 12 + [(S, N)] * 3 + [(N, S)] * 3


def test_score_matches_hand_computed_numbers(tmp_path, capsys):
    h, j = pairs_files(tmp_path, THIRTY)
    assert calibrate.main(["score", "--human", str(h), str(j)]) == 0
    out = capsys.readouterr().out
    assert "alignment=0.800" in out and "kappa=0.600" in out and "recall(not_supported)=0.800" in out
    assert out.count("lệch") == 6 and "1 người chấm" in out
    assert out.splitlines()[-1] == "CHƯA TIN"


def test_score_thresholds_are_arguments(tmp_path, capsys):
    h, j = pairs_files(tmp_path, THIRTY)
    assert (
        calibrate.main(["score", "--human", str(h), str(j), "--kappa", "0.5", "--alignment", "0.8", "--recall", "0.8"])
        == 0
    )
    assert capsys.readouterr().out.splitlines()[-1] == "TIN"


def test_score_counts_unknown_as_not_supported(tmp_path, capsys):
    h, j = pairs_files(tmp_path, [(S, S), (N, "unknown")])
    calibrate.main(["score", "--human", str(h), str(j)])
    out = capsys.readouterr().out
    assert "unknown=1" in out and "alignment=1.000" in out


def test_score_refuses_an_empty_human_cell(tmp_path):
    h, j = pairs_files(tmp_path, [(S, S), ("", S)])
    assert calibrate.main(["score", "--human", str(h), str(j)]) == 2


def test_two_raters_print_their_kappa(tmp_path, capsys):
    pairs = [(S, S)] * 15 + [(N, N)] * 15
    h1, j = pairs_files(tmp_path, pairs)
    h2, _ = pairs_files(tmp_path, pairs, "human2.csv")
    assert calibrate.main(["score", "--human", str(h1), "--human", str(h2), str(j)]) == 0
    out = capsys.readouterr().out
    assert "kappa người-người=1.000" in out and "1 người chấm" not in out
