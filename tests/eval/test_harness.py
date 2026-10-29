"""P2-T10: the eval harness end to end on the P1-T07 fixtures, with label oracles instead of the API (C-34)."""

import pytest

from tests.eval import run
from tutor.agents import diagnoser, grader


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


def test_real_backend_needs_yes(monkeypatch, capsys):
    monkeypatch.setattr(run, "evaluate", lambda *a, **k: pytest.fail("ran the real API without --yes"))
    assert run.main(["--backend", "real"]) == 2
    assert "tốn tiền" in capsys.readouterr().out
