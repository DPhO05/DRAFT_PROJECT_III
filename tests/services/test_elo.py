"""P4-T01/T03: Elo update, repeated misconceptions, level words (pure, no DB)."""

import json

from tutor.services import elo


def test_update_matches_spec_example():
    p, t = elo.update(0.10, 0.35, 0)
    assert (round(p, 2), round(t, 2)) == (0.44, -0.03)


def test_wrong_answer_never_raises_theta():
    for theta, delta in [(-2, 2), (0, 0), (2, -2)]:
        assert elo.update(theta, delta, 0)[1] < theta


def test_levels_at_bounds():
    levels = ["chưa vững", "đang hình thành", "đang hình thành", "vững"]
    assert [elo.level(t) for t in (-0.51, -0.5, 0.5, 0.51)] == levels
    assert [elo.trend(d) for d in (0.05, 0.049, -0.049, -0.05)] == ["tiến bộ", "giữ", "giữ", "cần ôn"]
    assert [elo.difficulty_word(d, True) for d in (-0.6, -0.3, 0.3, 0.6)] == ["dễ", "vừa", "vừa", "khó"]
    assert elo.difficulty_word(0.6, False) == "chưa đặt mức"


def test_trend_ignores_float_noise():
    assert elo.trend(0.05 - 1e-12) == "tiến bộ"
    assert elo.trend(-0.05 + 1e-12) == "cần ôn"


def test_one_session_three_attempts():
    # bài 1 đúng, bài 2 sai KC 7 (mã a.b), bài 3 đúng; δ = 0; HS mới
    att = [
        {"seq": 1, "delta": 0, "kcs": [7], "mistakes": [{"code": "x.y", "kc_id": None}]},
        {"seq": 2, "delta": 0, "kcs": [7], "mistakes": [{"code": "a.b", "kc_id": 7}]},
        {"seq": 3, "delta": 0, "kcs": [7], "mistakes": []},
    ]
    out = elo.profile(elo.empty_prior(), att, "2026-10-20")
    assert [(e["seq"], e["outcome"], round(e["theta_after"], 4)) for e in out["events"]] == [
        (1, 1, 0.15),
        (2, 0, -0.0112),
        (3, 1, 0.1396),
    ]
    assert out["kcs"] == [
        {
            "kc_id": 7,
            "theta_before": 0.0,
            "theta_after": out["events"][-1]["theta_after"],
            "d_theta": out["events"][-1]["theta_after"],
            "level_before": "đang hình thành",
            "level_after": "đang hình thành",
            "trend": "tiến bộ",
        }
    ]
    assert out["miscon_change"] == {"new": [["a.b", 7]], "again": [], "resolved": []}
    assert out["codes"] == {"repeat": [], "new": ["a.b", "x.y"], "gone": []}
    assert out["after"]["prev_codes"] == ["a.b", "x.y"]
    assert json.loads(json.dumps(out)) == out


def test_two_correct_in_a_row_resolve_and_reappear_reopens():
    bad = [{"seq": 1, "delta": 0, "kcs": [7], "mistakes": [{"code": "a.b", "kc_id": 7}]}]
    s1 = elo.profile(elo.empty_prior(), bad, "2026-10-01")
    ok = [{"seq": i, "delta": 0, "kcs": [7], "mistakes": []} for i in (1, 2)]
    s2 = elo.profile(s1["after"], ok, "2026-10-08")
    assert s2["miscon_change"]["resolved"] == [["a.b", 7]] and s2["miscon"][0]["resolved_at"] == "2026-10-08"
    assert s2["codes"] == {"repeat": [], "new": [], "gone": ["a.b"]}
    s3 = elo.profile(s2["after"], bad, "2026-10-15")
    row = s3["miscon"][0]
    assert (row["count"], row["resolved_at"], row["first_seen"]) == (2, None, "2026-10-01")
    assert s3["miscon_change"]["again"] == [["a.b", 7]]


def test_no_kc_no_events():
    att = [{"seq": 1, "delta": 0, "kcs": [], "mistakes": [{"code": "x.y", "kc_id": None}]}]
    out = elo.profile(elo.empty_prior(), att, "2026-10-20")
    assert out["events"] == [] and out["kcs"] == [] and out["miscon"] == []


def test_mistake_kc_outside_problem_kcs_still_counts():  # R1
    att = [{"seq": 1, "delta": 0, "kcs": [7], "mistakes": [{"code": "a.b", "kc_id": 9}]}]
    out = elo.profile(elo.empty_prior(), att, "2026-10-20")
    assert {(e["kc_id"], e["outcome"]) for e in out["events"]} == {(7, 1), (9, 0)}


def test_profile_does_not_mutate_prior():
    prior = elo.empty_prior()
    bad = [{"seq": 1, "delta": 0, "kcs": [7], "mistakes": [{"code": "a.b", "kc_id": 7}]}]
    s1 = elo.profile(prior, bad, "2026-10-01")["after"]
    snap = json.dumps(s1)
    elo.profile(s1, bad, "2026-10-08")
    assert json.dumps(s1) == snap and prior == elo.empty_prior()


def test_repeat_code_across_sessions():  # R3
    bad = [{"seq": 1, "delta": 0, "kcs": [7], "mistakes": [{"code": "a.b", "kc_id": 7}]}]
    s1 = elo.profile(elo.empty_prior(), bad, "2026-10-01")
    s2 = elo.profile(s1["after"], bad, "2026-10-08")
    assert s2["codes"] == {"repeat": ["a.b"], "new": [], "gone": []}


def test_miscon_counts_once_per_attempt():  # R2
    hit = {"code": "a.b", "kc_id": 7}
    two_attempts = [{"seq": i, "delta": 0, "kcs": [7], "mistakes": [hit]} for i in (1, 2)]
    out = elo.profile(elo.empty_prior(), two_attempts, "2026-10-01")
    assert out["miscon"][0]["count"] == 2
    assert out["miscon_change"] == {"new": [["a.b", 7]], "again": [], "resolved": []}
    dup = [{"seq": 1, "delta": 0, "kcs": [7], "mistakes": [hit, dict(hit)]}]
    assert elo.profile(elo.empty_prior(), dup, "2026-10-01")["miscon"][0]["count"] == 1
