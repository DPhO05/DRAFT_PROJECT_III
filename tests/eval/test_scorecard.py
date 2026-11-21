import json

from tests.eval import scorecard


def _res(created="2026-11-21T10:00:00Z", backend="fake", set_="00-dev", **kw) -> dict:
    res = {
        "backend": backend, "set": set_, "target": "00", "split": "dev", "source": "synthetic",
        "created": created, "runs": 3, "prompt_versions": {"00": ["00-ab"]}, "models": {"00": ["m1"]},
        "metrics": {
            "per_run": [{"n_questions": 8, "tools_ok": x} for x in (1.0, 0.5, 0.0)],
            "pass_k": 0.875, "success": 23 / 24,
            "tally": {"trials_passed": 23, "trials": 24, "tasks_passed": 7, "tasks": 8, "success": 23 / 24,
                      "pass_k": 0.875, "task_pass": {"q1": True}},
            "extra": {"name_leaks": 0},
        },
        "calls": {"logged": 10, "usd": 0.5},
    }  # fmt: skip
    return res | kw


def _write(d, name, res):
    d.mkdir(exist_ok=True)
    (d / name).write_text(json.dumps(res), encoding="utf-8")


def test_row_is_flat_and_has_fractions():
    r = scorecard.row(_res(), "a.json")
    assert r["metrics"] == {"n_questions": 8, "tools_ok": 0.5, "name_leaks": 0}
    assert (r["k"], r["n_tasks"], r["file"], r["calls"], r["usd"]) == (3, 8, "a.json", 10, 0.5)
    out = scorecard.table([r])
    assert "23/24" in out and "7/8" in out


def test_missing_extra_key_shows_dash_not_zero():
    res = _res()
    res["metrics"]["extra"] = {}
    r = scorecard.row(res, "a.json")
    assert "name_leaks" not in r["metrics"]
    assert "name_leaks=-" in scorecard.table([r])


def test_newest_file_per_set_and_backend(tmp_path):
    _write(tmp_path, "a.json", _res(created="2026-11-21T10:00:00Z"))
    _write(tmp_path, "b.json", _res(created="2026-11-21T11:00:00Z"))
    _write(tmp_path, "c.json", _res(backend="real"))
    rows = scorecard.build(tmp_path)
    assert {(x["set"], x["backend"]) for x in rows} == {("00-dev", "fake"), ("00-dev", "real")}
    assert next(x for x in rows if x["backend"] == "fake")["file"] == "b.json"
    assert [x["backend"] for x in scorecard.build(tmp_path, backend="real")] == ["real"]


def test_legacy_result_files_still_make_a_row(tmp_path):
    g1 = {
        "backend": "real", "created": "2026-11-04T08:00:00Z", "runs": 3, "files": ["s01.tex"], "prompt_versions": {},
        "metrics": {"per_run": [{"n_problems": 20, "recall": 0.9}], "stability": {"pass_k": 0.8}},
        "errors": [], "problems": [], "calls": {"backend_requests": 5, "logged": 7, "usd": 1.25, "by_agent": {}},
    }  # fmt: skip
    a00 = {
        "backend": "real", "agent": "00", "created": "2026-11-04T09:00:00Z", "runs": 3, "prompt_versions": {},
        "metrics": {"per_run": [{"n_questions": 20, "tools_ok": 1.0}], "pass_k": 0.7},
        "errors": [], "answers": [], "calls": {"logged": 9, "usd": 2.5},
    }  # fmt: skip
    _write(tmp_path, "g.json", g1)
    _write(tmp_path, "z.json", a00)
    rows = {x["set"]: x for x in scorecard.build(tmp_path)}
    assert set(rows) == {"g1-dev", "00-dev"}
    assert (rows["g1-dev"]["backend"], rows["g1-dev"]["calls"], rows["g1-dev"]["usd"]) == ("real", 7, 1.25)
    assert (rows["g1-dev"]["tasks"], rows["g1-dev"]["pass_k"], rows["g1-dev"]["trials_passed"]) == (20, 0.8, None)
    assert (rows["00-dev"]["tasks"], rows["00-dev"]["pass_k"]) == (20, 0.7)
    assert "0.700" in scorecard.table(list(rows.values()))


def test_kind_counts_against_a_baseline():
    res = _res()
    res["metrics"]["tally"]["task_pass"] = {"q1": True, "q2": True, "q3": False}
    base = {"00-dev": {"task_pass": {"q1": True, "q2": False}}}
    assert scorecard.row(res, "a.json", base)["kind_counts"] == {"regression": 1, "capability": 2}
    assert scorecard.row(res, "a.json")["kind_counts"] is None
    assert scorecard.row(res, "a.json", {})["kind_counts"] is None


def test_main_writes_scorecard_json_and_prints_a_table(tmp_path, capsys):
    d, o = tmp_path / "res", tmp_path / "out"
    _write(d, "a.json", _res())
    _write(d, "b.json", _res(set_="09-dev"))
    assert scorecard.main(["--results", str(d), "--out", str(o), "--baseline", str(tmp_path / "none.json")]) == 0
    (f,) = o.glob("*.json")
    assert len(json.loads(f.read_text())["rows"]) == 2
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0].startswith("| set") and len(lines) == 2 + 2


def test_with_tests_adds_one_row_per_target(tmp_path, monkeypatch, capsys):
    flows = tmp_path / "workflows.json"
    flows.write_text(json.dumps([
        {"target": "G2", "level": "outcome", "check": "x",
         "tests": ["tests/eval/test_metrics.py::test_first_wrong_step"]},
        {"target": "G2", "level": "trajectory", "check": "y", "tests": ["tests/eval/test_metrics.py::test_score_00"]},
    ]), encoding="utf-8")  # fmt: skip
    monkeypatch.setattr(scorecard, "WORKFLOWS", flows)
    (tmp_path / "results").mkdir()
    assert scorecard.main(["--results", str(tmp_path / "results"), "--out", str(tmp_path / "o"), "--with-tests"]) == 0
    (f,) = (tmp_path / "o").glob("*.json")
    [row] = json.loads(f.read_text(encoding="utf-8"))["rows"]
    assert (row["set"], row["target"], row["backend"], row["k"]) == ("G2-tests", "G2", "code", 1)
    assert (row["tasks_passed"], row["tasks"], row["pass_k"], row["calls"], row["usd"]) == (2, 2, 1, 0, 0)
    assert row["metrics"] == {"outcome": 1, "trajectory": 1}


def test_count_reads_the_last_pytest_line():
    out = "FAILED a::b - x\n3 passed, 1 failed, 2 errors in 1.2s\n"
    assert (scorecard._count(out, "passed"), scorecard._count(out, "failed|errors?")) == (3, 3)
    assert (scorecard._count("1 error in 0.1s\n", "passed"), scorecard._count("1 error in 0.1s", "failed|errors?")) == (
        0,
        1,
    )
    assert scorecard._count("", "passed") == 0
