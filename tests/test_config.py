import json
import os

import pytest

from tutor import config


def test_missing_file_gives_defaults(tmp_path):
    assert config.load(tmp_path / "settings.json") == config.defaults()


def test_save_then_load_round_trips(tmp_path):
    p = tmp_path / "settings.json"
    s = config.defaults()
    s["reco"]["n_problems"] = 8
    s["models"]["03"] = "claude-sonnet-5-5"
    config.save(p, s)
    assert config.load(p) == s


def test_partial_file_keeps_other_defaults(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"reco": {"n_problems": 4}}), encoding="utf-8")
    s = config.load(p)
    assert s["reco"]["n_problems"] == 4
    assert s["reco"]["ratios"] == {"review": 0.4, "zpd": 0.5, "challenge": 0.1}
    assert s["budget_usd_month"] == 30


def test_corrupt_file_raises_and_is_not_overwritten(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(config.SettingsError):
        config.load(p)
    assert p.read_text(encoding="utf-8") == "{not json"


def test_defaults_match_appendix_c():
    s = config.defaults()
    assert s["models"] == {f"{i:02d}": "claude-opus-5-5" for i in range(0, 5)}
    assert s["assistant"] == {"max_tool_turns": 8}
    assert s["backup"] == {"keep_recent": 30, "keep_monthly": True}
    assert s["app"]["port"] == 8000
    assert (config.K, config.THETA0, config.RESOLVE_STREAK) == (0.3, 0, 2)
    assert s["price_by_model"]["openai:gpt-5.6-sol"] == {
        "input_per_mtok": 4,
        "output_per_mtok": 20,
        "cache_read_per_mtok": 0.4,
        "cache_write_per_mtok": 5,
    }


def test_load_env(tmp_path, monkeypatch, capsys):
    for k in ("OPENAI_API_KEY", "X_ONE"):
        monkeypatch.setenv(k, "")  # records the original so what load_env sets is undone
        monkeypatch.delenv(k)
    monkeypatch.setenv("X_KEEP", "old")
    f = tmp_path / ".env"
    f.write_text('# c\n\nOPENAI_API_KEY="sk-test"\nexport X_ONE=1\nX_KEEP=new\n', encoding="utf-8")
    assert config.load_env(f) is None
    assert os.environ["OPENAI_API_KEY"] == "sk-test"
    assert os.environ["X_ONE"] == "1"
    assert os.environ["X_KEEP"] == "old"
    config.load_env(tmp_path / "absent.env")
    assert capsys.readouterr() == ("", "")


def test_student_code():
    assert config.student_code(3) == "HS-03"
    assert config.student_code(12) == "HS-12"


def test_paths_default_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("TUTOR_DATA", str(tmp_path))
    p = config.paths()
    assert p.tutor_db == tmp_path / "tutor.db"
    assert p.runner_lock == tmp_path / "runner.lock"
    assert config.paths(tmp_path / "x").backup == tmp_path / "x" / "backup"
