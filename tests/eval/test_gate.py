import json
import warnings

import pytest

from tests.eval import agents, gate, judges, run, scorecard
from tutor import config, llm
from tutor.agents.a09_reporter import reporter

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


G1_SETS = ["g1-dev", "g1-heldout"]
_TIER0: dict[str, dict] = {}


@pytest.fixture
def tier0(tmp_path_factory):
    """Every target with its oracle, k = 3, run once per test session and shared by the tests below."""
    if not _TIER0:
        for name in G1_SETS:
            fix = run.ROOT / run.load_sets()[name]["dir"]
            _TIER0[name] = run.evaluate(run.oracle, work=tmp_path_factory.mktemp(name), runs=3, fix=fix)
        for name, spec in run.TARGETS.items():
            oracle = judges.with_oracle(spec["oracle"]) if spec.get("judge") else spec["oracle"]
            kw = {"judge": True} if spec.get("judge") else {}
            runs = spec.get("runs", 3)
            _TIER0[f"{name}-dev"] = spec["evaluate"](oracle, work=tmp_path_factory.mktemp(name), runs=runs, **kw)
    return _TIER0


def test_tier0_every_set_passes_with_its_oracle(tier0):
    assert set(tier0) == {"g1-dev", "g1-heldout", "00-dev", "09-dev", "g5-dev", "01-dev", "04-dev", "02r-dev", "08-dev"}
    for name, res in tier0.items():
        assert res["errors"] == [], name
        assert res["metrics"]["pass_k"] == 1 and res["metrics"]["success"] == 1, name
        assert res["metrics"]["extra"]["name_leaks"] == 0, name
        assert (res["calls"]["logged"] == 0) == (name == "08-dev"), name
    assert tier0["00-dev"]["metrics"]["extra"]["approval_ok"] == 1
    assert all(tier0[n]["metrics"]["extra"]["faithfulness"] == 1 for n in ("00-dev", "09-dev", "g5-dev"))


def test_tier0_rows_pass_the_gate(tier0):
    rows = [scorecard.row(run.meta("g1" if n in G1_SETS else n.removesuffix("-dev"), n, "fake") | res, n)
            for n, res in tier0.items()]  # fmt: skip
    lines = gate.check(rows, json.loads(gate.BASELINE.read_text(encoding="utf-8")))
    assert [x for x in lines if x["status"] == "TRƯỢT"] == []


def test_dev_backend_matches_the_snapshot(tmp_path):
    res = run.evaluate(run._backend("dev"), work=tmp_path, runs=1)
    want = json.loads(gate.BASELINE.read_text(encoding="utf-8"))["dev"]["g1-dev"]
    got = res["metrics"]["per_run"][0]
    assert res["errors"] == [] and want and set(want) == set(got)
    for k, v in want.items():
        assert got[k] == pytest.approx(v), k


def test_prompt_versions_without_a_real_scorecard_only_warn(tier0):
    current: dict[str, set] = {}
    for res in tier0.values():
        for agent, versions in res["prompt_versions"].items():
            current.setdefault(agent, set()).update(versions)
    real = json.loads(gate.BASELINE.read_text(encoding="utf-8"))["real"]["prompt_versions"]
    todo = gate.unverified({a: sorted(v) for a, v in current.items()}, real)
    for line in todo:
        warnings.warn(f"chưa kiểm 3 lần: {line}", stacklevel=1)
    assert {"00", "01", "02", "03", "04", "09"} <= set(current)  # the test passes whatever `todo` holds


def test_a_changed_prompt_names_its_agent(tmp_path, monkeypatch):
    before = agents.evaluate_09(agents.oracle_09, work=tmp_path / "a", runs=1, only=[agents.PERIODS[0]["key"]])
    monkeypatch.setattr(reporter, "INSTRUCTIONS", reporter.INSTRUCTIONS + " ")
    after = agents.evaluate_09(agents.oracle_09, work=tmp_path / "b", runs=1, only=[agents.PERIODS[0]["key"]])
    assert gate.unverified(after["prompt_versions"], before["prompt_versions"]) == [
        f"09 {after['prompt_versions']['09'][0]}"
    ]


def test_real_backend_without_a_key_fails_before_any_request(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "no.env")  # run.main loads it; a real .env would hold a key
    monkeypatch.setattr(llm, "_chat", {})
    monkeypatch.setenv("TUTOR_DATA", str(tmp_path / "no-data"))
    code = run.main(["--agent", "09", "--backend", "real", "--yes", "--runs", "1", "--out", str(tmp_path / "results")])
    (f,) = (tmp_path / "results").glob("*.json")
    res = json.loads(f.read_text(encoding="utf-8"))
    assert code == 1 and len(res["errors"]) == 6 and all("KeyRejected" in e["error"] for e in res["errors"])
    assert res["calls"]["logged"] == 0
