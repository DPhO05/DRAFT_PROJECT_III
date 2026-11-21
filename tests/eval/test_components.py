"""Component targets 01, 04, 02r, 08 end to end with oracles instead of the API (C-34)."""

import pytest

from tests.eval import components, run
from tests.fakes import FakeLLM
from tutor.agents.a01_ingest import ingest
from tutor.agents.a04_verifier import verifier


def test_01_tasks_are_wellformed():
    assert [t["id"] for t in components.TASKS_01] == [f"m{i}" for i in range(1, 11)]
    assert sum(t["expect_ref"] is None for t in components.TASKS_01) == 2
    heads = [components.body(t)[:40] for t in components.TASKS_01]
    assert len(set(heads)) == 10 and all("[" not in t["tex"].split("\n", 1)[0] for t in components.TASKS_01)


def test_01_oracle_matches_every_problem(tmp_path):
    res = components.evaluate_01(components.oracle_01, work=tmp_path, runs=3)
    assert res["errors"] == [] and res["metrics"]["pass_k"] == 1 and res["calls"]["logged"] == 30
    for s in res["metrics"]["per_run"]:
        assert (s["n_tasks"], s["hit_at_1"], s["hit_at_3"], s["mrr"], s["low_match_precision"]) == (10, 1, 1, 1, 1)


def second_best(conn):
    fake, models = components.oracle_01(conn)
    right = fake.handlers["01"]

    def handle(user, system):
        out = right(user=user, system=system)
        other = ingest.Candidate(ref="9DS-BPT-001", score=0.99)
        return ingest.MatchResult(candidates=[other, *out.candidates]) if out.candidates else out

    fake.handlers["01"] = handle
    return fake, models


def test_01_wrong_first_candidate_drops_hit_at_1_only(tmp_path):
    s = components.evaluate_01(second_best, work=tmp_path, runs=1)["metrics"]["per_run"][0]
    assert s["hit_at_1"] < 1 and s["hit_at_3"] == 1 and s["passed"] < 1


def test_04_tasks_are_balanced_and_unique():
    kinds = [t["expect"] for t in components.TASKS_04]
    assert (kinds.count("agree"), kinds.count("disagree"), kinds.count("wrong_code")) == (6, 3, 3)
    assert len({t["claim"]["description"] for t in components.TASKS_04}) == 12
    assert all(t["claim"]["code"].split(".")[0] != t["expect_code"].split(".")[0]
               for t in components.TASKS_04 if t["expect"] == "wrong_code")  # fmt: skip


def test_04_oracle_gives_every_expected_verdict(tmp_path):
    res = components.evaluate_04(components.oracle_04, work=tmp_path, runs=3)
    assert res["errors"] == [] and res["metrics"]["pass_k"] == 1 and res["calls"]["logged"] == 36
    for s in res["metrics"]["per_run"]:
        assert (s["n_tasks"], s["accuracy"], s["recall_disagree"], s["empty"]) == (12, 1, 1, 0)


def always_agree(conn):
    return FakeLLM({"04": verifier.VerdictOut(verdict="agree", reason="x")}), {}


def test_04_always_agree_misses_every_wrong_conclusion(tmp_path):
    s = components.evaluate_04(always_agree, work=tmp_path, runs=1)["metrics"]["per_run"][0]
    assert s["accuracy"] == 6 / 12 and s["recall_disagree"] == 0


def test_02r_oracle_drafts_pass(tmp_path):
    res = components.evaluate_02r(components.oracle_02r, work=tmp_path, runs=3)
    assert res["errors"] == [] and res["metrics"]["pass_k"] == 1 and res["calls"]["logged"] == 12
    assert list(res["prompt_versions"]) == ["02"]


def test_02r_schema_failure_fails_the_task(tmp_path):
    res = components.evaluate_02r(lambda conn: (FakeLLM({"02": None}), {}), work=tmp_path, runs=1)
    assert res["metrics"]["pass_k"] == 0 and res["errors"] == []


@pytest.mark.parametrize("agent", ["01", "04", "02r"])
def test_real_backend_needs_yes(agent, capsys):
    assert run.main(["--agent", agent, "--backend", "real"]) == 2
    assert "tốn tiền" in capsys.readouterr().out
