"""P2-T10: the eval harness end to end on the P1-T07 fixtures, with label oracles instead of the API (C-34)."""

import json
import sqlite3
from contextlib import closing

import pytest

from tests.eval import run
from tutor.agents.a02_grader import grader
from tutor.agents.a03_diagnoser import diagnoser


def test_label_oracle_scores_perfect_and_stable(tmp_path):
    res = run.evaluate(run.oracle, work=tmp_path, runs=3)
    assert res["errors"] == []
    assert res["files"] == [f"s{i:02d}.tex" for i in range(1, 11)]  # s10-dup is a duplicate-check fixture
    for s in res["metrics"]["per_run"]:
        assert s["n_problems"] == 40 and s["n_labels"] == s["n_proposals"] == s["n_pairs"] == 21
        assert (s["first_wrong_step_acc"], s["precision"], s["recall"], s["kappa"]) == (1, 1, 1, 1)
        assert (s["drop_rate"], s["add_rate"]) == (0, 0)
    st = res["metrics"]["stability"]
    assert (st["runs"], st["n_problems"], st["items_changed_pct"], st["pass_k"]) == (3, 40, 0, 1)
    assert st["n_items"] > 40
    assert {"02", "03", "04"} <= set(res["prompt_versions"])
    assert all(v[0].startswith(f"{a}-") for a, v in res["prompt_versions"].items())


def _count(db, table):
    with closing(sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True)) as c:
        return c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_each_run_starts_from_a_new_world(tmp_path):
    run.evaluate(run.oracle, work=tmp_path, files=["s01.tex"], runs=2)
    for k in (1, 2):
        data = tmp_path / f"run{k}" / "data"
        assert _count(data / "tutor.db", "student") == 1 and _count(data / "tutor.db", "session") == 1
        assert _count(data / "checkpoints.db", "tutor_thread") == 1


def test_traces_are_kept_per_run(tmp_path):
    made = []

    def backend(conn, labels):
        made.append(run.oracle(conn, labels))
        return made[-1]

    res = run.evaluate(backend, work=tmp_path / "w", files=["s01.tex"], runs=2, traces=tmp_path / "tr")
    lines = sum(len((tmp_path / "tr" / f"run{k}.jsonl").read_text(encoding="utf-8").splitlines()) for k in (1, 2))
    assert len(made) == 1 and lines == sum(made[0][0].count.values()) > 0 and res["errors"] == []


def test_labels_never_enter_the_trial_data(tmp_path):
    run.evaluate(run.oracle, work=tmp_path, files=["s04.tex"], runs=1, traces=tmp_path / "tr")
    assert (tmp_path / "tr" / "run1.jsonl").exists()
    for f in [*(tmp_path / "run1" / "data").rglob("*"), *(tmp_path / "tr").rglob("*")]:
        if f.is_file():
            data = f.read_bytes()
            assert b"propagates_to" not in data and b"labels.json" not in data, f


def wrong_oracle(conn, labels):
    """Keeps only each problem's first mistake, always as other.unclear; invents step 1 on clean problems;
    02 passes every item in run 1 and fails them all after (9 problems a run)."""
    fake, models = run.oracle(conn, labels)
    right02, right03 = fake.handlers["02"], fake.handlers["03"]

    def h03(user, system):
        ms = right03(user=user, system=system).mistakes[:1] or [
            diagnoser.MistakeOut(step_idx=1, code="x", kc_id=None, description="bịa", evidence_latex="x",
                                 confidence=0.9)]  # fmt: skip
        return diagnoser.DiagnosisOut(corrected_latex="", mistakes=[m.model_copy(update={"code": "other.unclear"})
                                                                    for m in ms])  # fmt: skip

    def h02(user, system):
        out = right02(user=user, system=system)
        if fake.count["02"] <= 9:
            return out
        return grader.GradeOut(items=[i.model_copy(update={"passed": False}) for i in out.items], score=0)

    fake.handlers |= {"02": h02, "03": h03}
    return fake, models


def test_wrong_oracle_metrics_drop(tmp_path):
    res = run.evaluate(wrong_oracle, work=tmp_path, files=["s01.tex", "s04.tex"], runs=2)
    assert res["errors"] == []
    s = res["metrics"]["per_run"][0]
    # 9 problems, 4 with mistakes (first step kept -> right), 5 clean (step 1 invented -> wrong)
    assert s["first_wrong_step_acc"] == 4 / 9
    assert s["kappa"] == 0  # every LLM code other.unclear, never a teacher code: po = pe = 0
    assert s["drop_rate"] == 1 / 5  # s04 #4 step 6
    assert s["add_rate"] == 5 / 9
    assert res["metrics"]["stability"]["items_changed_pct"] == 100
    assert res["metrics"]["stability"]["pass_k"] == 4 / 9
    assert res["metrics"]["components"][0]["clean_flagged"] == 1


def test_oracle_components_are_perfect(tmp_path):
    res = run.evaluate(run.oracle, work=tmp_path, files=["s03.tex", "s04.tex"], runs=1)
    c = res["metrics"]["components"][0]
    assert (c["evidence_02"], c["evidence_03"], c["clean_full_marks"], c["clean_flagged"]) == (1, 1, 1, 0)
    assert c["flags"] == {} and c["agree_on_right"] == 1
    assert res["metrics"]["extra"]["name_leaks"] == 0  # s03 holds a full name, with and without diacritics


def test_real_backend_needs_yes(monkeypatch, capsys):
    monkeypatch.setattr(run, "evaluate", lambda *a, **k: pytest.fail("ran the real API without --yes"))
    assert run.main(["--backend", "real"]) == 2
    assert "tốn tiền" in capsys.readouterr().out


def test_unknown_set_exits_2(capsys):
    assert run.main(["--set", "nope", "--backend", "fake"]) == 2
    assert "nope" in capsys.readouterr().out


def test_result_names_its_set(tmp_path):
    out = tmp_path / "results"
    assert run.main(["--backend", "fake", "--runs", "1", "--files", "s01.tex", "--out", str(out)]) == 0
    (f,) = out.glob("*.json")
    res = json.loads(f.read_text(encoding="utf-8"))
    assert (res["set"], res["target"], res["split"], res["source"]) == ("g1-dev", "g1", "dev", "synthetic")


def test_local_sets_extend_committed_ones(tmp_path, monkeypatch):
    local = tmp_path / "sets.json"
    local.write_text(
        '{"mine": {"dir": "data/eval/tasks/mine", "split": "dev", "source": "production"}}', encoding="utf-8"
    )
    monkeypatch.setattr(run, "LOCAL_SETS", local)
    assert {"g1-dev", "mine"} <= set(run.load_sets())


def test_heldout_oracle_scores_perfect(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "LOCAL_SETS", tmp_path / "none.json")
    fix = run.ROOT / run.load_sets()["g1-heldout"]["dir"]
    res = run.evaluate(run.oracle, work=tmp_path, runs=1, fix=fix)
    assert res["errors"] == [] and len(res["files"]) == 10
    s = res["metrics"]["per_run"][0]
    assert (s["n_problems"], s["n_labels"], s["n_proposals"]) == (20, 12, 12)
    assert (s["precision"], s["recall"], s["first_wrong_step_acc"]) == (1, 1, 1)


def test_committed_task_files_are_not_production_data():
    assert all(s["source"] != "production" for s in json.loads(run.SETS.read_text(encoding="utf-8")).values())
    for f in (run.ROOT / "tests" / "eval").rglob("*.json"):
        assert '"source": "production"' not in f.read_text(encoding="utf-8"), f


def test_g1_result_has_calls_tally_and_models(tmp_path):
    res = run.evaluate(run.oracle, work=tmp_path, files=["s01.tex"], runs=2)
    assert res["calls"]["logged"] > 0 and {"02", "03"} <= set(res["calls"]["by_agent"])
    t = res["metrics"]["tally"]
    assert (t["trials"], t["tasks"], t["tasks_passed"]) == (10, 5, 5) and res["metrics"]["pass_k"] == 1
    assert res["metrics"]["extra"]["flow_errors"] == 0


def test_heldout_trajectory_stays_in_budget(tmp_path):
    fix = run.ROOT / run.load_sets()["g1-heldout"]["dir"]
    res = run.evaluate(run.oracle, work=tmp_path, runs=1, fix=fix, files=["hs11-2026-11-13.tex", "hs12-2026-11-12.tex"])
    t = res["metrics"]["trajectory"]
    assert (t["threads"], t["over_budget"], t["order_ok"], t["retries"], t["schema_errors"]) == (2, 0, 1, 0, 0)
    assert res["metrics"]["extra"]["confirm_ok"] == 1


def test_dev_set_has_no_budget(tmp_path):
    res = run.evaluate(run.oracle, work=tmp_path, files=["s04.tex"], runs=1)
    assert res["metrics"]["trajectory"]["over_budget"] is None and res["metrics"]["extra"]["confirm_ok"] == 1


def test_crashed_file_stays_in_confirm_and_budget_counts(tmp_path):
    def backend(conn, labels):
        labels["s04.tex"]["max_calls"] = 0  # any logged call of the crashed thread is over budget
        fake, models = run.oracle(conn, labels)
        fake.handlers["02"] = RuntimeError("down")
        return fake, models

    res = run.evaluate(backend, work=tmp_path, files=["s04.tex"], runs=1)
    assert len(res["errors"]) == 1
    assert res["metrics"]["extra"]["confirm_ok"] == 0
    assert res["metrics"]["trajectory"]["threads"] == 1 and res["metrics"]["trajectory"]["over_budget"] == 1
