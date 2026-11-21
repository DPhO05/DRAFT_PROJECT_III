import json

from tests.eval import gate, scorecard

BASE = json.loads(gate.BASELINE.read_text(encoding="utf-8"))


def _row(set_="g1-dev", backend="real", **metrics) -> dict:
    return {"set": set_, "backend": backend, "n_tasks": 20, "metrics": {"name_leaks": 0} | metrics}


def _lines(rows, **base) -> list[dict]:
    return gate.check(rows, BASE | base)


def _one(rows, metric, **base) -> dict:
    (x,) = [x for x in _lines(rows, **base) if x["metric"] == metric]
    return x


def _dev00(passing: dict) -> dict:
    return _row("00-dev", approval_ok=1.0, pass_k=1.0) | {"task_pass": passing}


def _tasks(passing: int) -> dict:
    return {f"q{i}": i < passing for i in range(20)}


def _run(tmp_path, rows, *args, **base) -> int:
    (tmp_path / "s.json").write_text(json.dumps({"rows": rows}), encoding="utf-8")
    (tmp_path / "b.json").write_text(json.dumps(BASE | base), encoding="utf-8")
    return gate.main([str(tmp_path / "s.json"), "--baseline", str(tmp_path / "b.json"), *args])


def test_baseline_floors_cover_design_8_3():
    assert {(f["set"], f["metric"]) for f in BASE["floors"]} == {
        ("*", "name_leaks"), ("00-dev", "approval_ok"), ("g1-*", "flow_errors"), ("g1-*", "recall"),
        ("g1-*", "precision"), ("00-dev", "pass_k"), ("09-dev", "dropped_pct"), ("09-dev", "faithfulness"),
        ("00-dev", "faithfulness"), ("01-dev", "hit_at_1"), ("04-dev", "recall_disagree"),
    }  # fmt: skip


def test_floor_passes_and_fails(tmp_path, capsys):
    assert _one([_row(recall=0.95)], "recall")["status"] == "ĐẠT"
    assert _run(tmp_path, [_row(recall=0.95)]) == 0
    assert _one([_row(recall=0.85)], "recall")["status"] == "TRƯỢT"
    assert _run(tmp_path, [_row(recall=0.85)]) == 1
    assert any(x.startswith("TRƯỢT g1-dev recall 0.85") for x in capsys.readouterr().out.splitlines())


def test_hard_floor_fails_on_a_missing_value():
    row = {"set": "g1-dev", "backend": "real", "metrics": {}}
    assert _one([row], "name_leaks")["status"] == "TRƯỢT"
    assert _one([_row("01-dev")], "hit_at_1")["status"] == "BỎ QUA"


def test_judge_floor_waits_for_trust():
    rows = [_row("09-dev", faithfulness=0.5)]
    assert _one(rows, "faithfulness", judge_trusted=False)["status"] == "BỎ QUA"
    assert _one(rows, "faithfulness", judge_trusted=True)["status"] == "TRƯỢT"


def test_two_tasks_down_fails_one_task_down_passes(tmp_path):
    base = {"real": {"rows": {"00-dev": {"n_tasks": 20, "task_pass": _tasks(20)}}}}
    assert _run(tmp_path, [_dev00(_tasks(18))], **base) == 1
    assert _run(tmp_path, [_dev00(_tasks(19))], **base) == 0


def test_task_drop_compares_only_shared_tasks(tmp_path):
    base = {"real": {"rows": {"00-dev": {"n_tasks": 3, "task_pass": {"a": True, "b": True, "c": True}}}}}
    now = {"a": True, "b": False, "z": False}  # z is new, c is gone: only b counts
    assert _run(tmp_path, [_dev00(now)], **base) == 0


def test_metric_drop_is_measured_in_tasks():
    base = {"real": {"rows": {"g1-dev": {"metrics": {"recall": 1.0}}}}}

    def drop(recall):  # last "recall" line is the no-drop one; the floor line (0.90) comes first
        return [x["status"] for x in _lines([_row(recall=recall)], **base) if x["metric"] == "recall"]

    assert drop(0.95) == ["ĐẠT", "ĐẠT"]
    assert drop(0.94) == ["ĐẠT", "TRƯỢT"]


def test_only_the_chosen_backend_is_gated(tmp_path):
    rows = [_row(recall=0.5, backend="fake"), _row(recall=0.95)]
    assert _run(tmp_path, rows) == 0
    assert _run(tmp_path, rows, "--backend", "fake") == 1


def test_missing_set_is_skipped(tmp_path):
    base = {"real": {"rows": {"04-dev": {"n_tasks": 20, "task_pass": _tasks(20)}}}}
    assert {x["status"] for x in _lines([_row()], **base) if x["set"] == "04-dev"} == {"BỎ QUA"}
    assert _run(tmp_path, [_row(recall=0.95)], **base) == 0


def test_unverified_names_changed_and_new_versions():
    now = {"09": ["09-aaaa"], "02": ["02-bbbb"], "judge": ["judge-cc"]}
    assert gate.unverified(now, {"09": ["09-zzzz"], "02": ["02-bbbb"]}) == ["09 09-aaaa", "judge judge-cc"]


def test_scorecard_baseline_option_fills_kind_counts(tmp_path):
    res = {
        "backend": "real", "set": "00-dev", "target": "00", "created": "2026-11-21T10:00:00Z",
        "metrics": {"per_run": [{"n_questions": 2}], "tally": {"tasks": 2, "task_pass": {"q1": True, "q2": True}}},
    }  # fmt: skip
    other = res | {"set": "09-dev", "target": "09"}
    (tmp_path / "res").mkdir()
    for name, r in (("a.json", res), ("b.json", other)):
        (tmp_path / "res" / name).write_text(json.dumps(r), encoding="utf-8")
    base = BASE | {"real": {"rows": {"00-dev": {"task_pass": {"q1": True}}}}}
    (tmp_path / "b.json").write_text(json.dumps(base), encoding="utf-8")
    args = ["--results", str(tmp_path / "res"), "--out", str(tmp_path / "out"), "--baseline", str(tmp_path / "b.json")]
    assert scorecard.main(args) == 0
    (f,) = (tmp_path / "out").glob("*.json")
    kinds = {r["set"]: r["kind_counts"] for r in json.loads(f.read_text(encoding="utf-8"))["rows"]}
    assert kinds == {"00-dev": {"regression": 1, "capability": 1}, "09-dev": None}
