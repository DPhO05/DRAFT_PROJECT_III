"""Component targets 01, 04, 02r, 08 end to end with oracles instead of the API (C-34)."""

import pytest

from tests.eval import components, run
from tutor.agents.a01_ingest import ingest


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


@pytest.mark.parametrize("agent", ["01"])
def test_real_backend_needs_yes(agent, capsys):
    assert run.main(["--agent", agent, "--backend", "real"]) == 2
    assert "tốn tiền" in capsys.readouterr().out
