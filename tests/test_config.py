import json
import os
import stat

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
    assert s["models"] == {f"{i:02d}": "openai:gpt-5.6-sol" for i in (*range(0, 5), 9)}
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
    for k in ("OPENAI_API_KEY", "X_ONE", "LANGSMITH_TRACING"):
        monkeypatch.setenv(k, "")  # records the original so what load_env sets is undone
        monkeypatch.delenv(k)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "old")
    f = tmp_path / ".env"
    f.write_text(
        '# c\n\nOPENAI_API_KEY="sk-test"\nexport X_ONE=1\nANTHROPIC_API_KEY=new\nLANGSMITH_TRACING=true\n',
        encoding="utf-8",
    )
    assert config.load_env(f) is None
    assert os.environ["OPENAI_API_KEY"] == "sk-test"
    assert "X_ONE" not in os.environ  # only the two API keys come from .env
    assert os.environ["ANTHROPIC_API_KEY"] == "old"
    assert os.environ["LANGSMITH_TRACING"] == "false"
    config.load_env(tmp_path / "absent.env")
    assert capsys.readouterr() == ("", "")


def test_no_tracing_turns_langsmith_off(monkeypatch):
    from langsmith import utils

    for k in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "LANGSMITH_API_KEY", "LANGSMITH_ENDPOINT"):
        monkeypatch.setenv(k, "true" if "TRACING" in k else "x")
    utils.get_env_var.cache_clear()
    config.no_tracing()
    utils.get_env_var.cache_clear()
    assert utils.tracing_is_enabled() is False
    assert "LANGSMITH_API_KEY" not in os.environ and "LANGSMITH_ENDPOINT" not in os.environ


def test_patch_writes_only_changed_keys(tmp_path):
    p = tmp_path / "settings.json"
    got = config.patch(p, {"reco": {"n_problems": 8}})
    assert json.loads(p.read_text(encoding="utf-8")) == {"reco": {"n_problems": 8}}  # not the merged defaults
    assert got["reco"]["n_problems"] == 8 and got["models"] == config.defaults()["models"]
    config.patch(p, {"budget_usd_month": 12})
    assert json.loads(p.read_text(encoding="utf-8")) == {"reco": {"n_problems": 8}, "budget_usd_month": 12}


def test_patch_corrupt_file_raises(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("{oops", encoding="utf-8")
    with pytest.raises(config.SettingsError):
        config.patch(p, {"budget_usd_month": 1})
    assert p.read_text(encoding="utf-8") == "{oops"


def test_load_env_non_utf8_is_skipped_with_one_line(tmp_path, capsys):
    f = tmp_path / ".env"
    f.write_bytes(b"OPENAI_API_KEY=sk-test-fake\xff\xfe\n")
    config.load_env(f)
    out, err = capsys.readouterr()
    assert out == "" and err == "File khoá .env không đọc được (không phải UTF-8), bỏ qua.\n"
    assert "OPENAI_API_KEY" not in os.environ and "sk-test" not in err


def test_save_env_keeps_other_lines_and_0600(tmp_path):
    f = tmp_path / ".env"
    f.write_text("A=1\nexport OPENAI_API_KEY=old\n# OPENAI_API_KEY=note\nOPENAI_API_KEY = older\nB=2", encoding="utf-8")
    f.chmod(0o644)
    config.save_env(f, "OPENAI_API_KEY", "sk-test-new")
    assert f.read_text(encoding="utf-8").splitlines() == [
        "A=1",
        "# OPENAI_API_KEY=note",
        "B=2",
        "OPENAI_API_KEY=sk-test-new",
    ]
    assert stat.S_IMODE(f.stat().st_mode) == 0o600
    assert not list(tmp_path.glob(".env.*"))  # no temp file left
    config.load_env(f)
    assert os.environ["OPENAI_API_KEY"] == "sk-test-new"


def test_save_env_creates_file_0600_and_refuses_a_line_break(tmp_path):
    f = tmp_path / ".env"
    config.save_env(f, "ANTHROPIC_API_KEY", "sk-test-1")
    assert f.read_text(encoding="utf-8") == "ANTHROPIC_API_KEY=sk-test-1\n" and stat.S_IMODE(f.stat().st_mode) == 0o600
    with pytest.raises(ValueError) as e:
        config.save_env(f, "ANTHROPIC_API_KEY", "sk-test-2\nX=1")
    assert "sk-test-2" not in str(e.value) and f.read_text(encoding="utf-8") == "ANTHROPIC_API_KEY=sk-test-1\n"


def test_save_env_does_not_follow_a_planted_temp_symlink(tmp_path):
    victim = tmp_path / "victim"
    victim.write_text("keep", encoding="utf-8")
    (tmp_path / ".env.tmp").symlink_to(victim)  # the name an attacker would guess
    f = tmp_path / ".env"
    config.save_env(f, "ANTHROPIC_API_KEY", "sk-test-1")
    assert victim.read_text(encoding="utf-8") == "keep" and (tmp_path / ".env.tmp").is_symlink()
    assert f.read_text(encoding="utf-8") == "ANTHROPIC_API_KEY=sk-test-1\n" and not f.is_symlink()


def test_save_env_removes_its_temp_file_when_the_write_fails(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("A=1\n", encoding="utf-8")

    def boom(src, dst):
        raise OSError("disk full")

    with monkeypatch.context() as m:
        m.setattr(config.os, "replace", boom)
        with pytest.raises(OSError, match="disk full"):
            config.save_env(f, "ANTHROPIC_API_KEY", "sk-test-1")
    assert f.read_text(encoding="utf-8") == "A=1\n" and not list(tmp_path.glob(".env.*"))


def test_save_env_non_utf8_file_is_an_oserror_that_quotes_nothing(tmp_path):
    f = tmp_path / ".env"
    f.write_bytes(b"A=\xff\xfe\nOPENAI_API_KEY=old\n")
    with pytest.raises(OSError) as e:  # a ValueError would reach the teacher as a 422 about the key
        config.save_env(f, "OPENAI_API_KEY", "sk-test-new")
    assert not isinstance(e.value, ValueError)
    assert "sk-test-new" not in str(e.value) and "0xff" not in str(e.value) and "=old" not in str(e.value)
    # no decode error behind it: Starlette re-raises an exception's __context__ and the log would name the bad byte
    assert e.value.__cause__ is None and e.value.__context__ is None
    assert f.read_bytes() == b"A=\xff\xfe\nOPENAI_API_KEY=old\n" and not list(tmp_path.glob(".env.*"))


def test_student_code():
    assert config.student_code(3) == "HS-03"
    assert config.student_code(12) == "HS-12"


def test_paths_default_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("TUTOR_DATA", str(tmp_path))
    p = config.paths()
    assert p.tutor_db == tmp_path / "tutor.db"
    assert p.runner_lock == tmp_path / "runner.lock"
    assert config.paths(tmp_path / "x").backup == tmp_path / "x" / "backup"
