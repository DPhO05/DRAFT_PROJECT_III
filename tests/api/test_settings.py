"""P8-T02: /api/settings and PUT /api/settings/key (api-v3 §7.3, R3, R6, R18; Review Focus 3 and 4)."""

import json
import os
import stat

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import PORT
from tests.api.test_sessions import W
from tutor import llm
from tutor.api.app import create_app
from tutor.db import repo

KEY = "sk-test-" + "a" * 30
KEY2 = "sk-test-" + "b" * 30
URL = "/api/settings"
PUT = f"{URL}/key"
JSON = W | {"Content-Type": "application/json"}


@pytest.fixture(autouse=True)
def no_live_backend(monkeypatch):
    monkeypatch.setattr(llm, "_live", {})


def put(client, body):
    return client.put(PUT, json=body, headers=W)


def app_log(paths) -> str:
    return (paths.logs / "app.log").read_text(encoding="utf-8")


def started(paths) -> TestClient:
    repo.init_db(paths.tutor_db, paths.backup)
    return TestClient(create_app(paths, port=PORT), base_url=f"http://127.0.0.1:{PORT}")


def test_get_defaults_and_no_key(client):
    assert client.get(URL).json() == {
        "reco": {"n_problems": 6, "no_repeat_days": 30},
        "budget_usd_month": 30,
        "settings_error": None,
        "keys": {"openai": False},
    }


def test_get_lists_the_providers_of_models(paths):
    paths.settings.write_text(json.dumps({"models": {"00": "claude-opus-5-5"}}), encoding="utf-8")
    with started(paths) as c:
        assert c.get(URL).json()["keys"] == {"openai": False, "anthropic": False}  # 01-04 and 09 keep the default


def test_patch_then_get_reads_back(paths, app, client):
    r = client.patch(URL, json={"reco": {"n_problems": 8}, "budget_usd_month": 12.5}, headers=W)
    assert r.status_code == 200
    assert r.json() == {
        "reco": {"n_problems": 8, "no_repeat_days": 30},
        "budget_usd_month": 12.5,
        "settings_error": None,
        "keys": {"openai": False},
    }
    assert client.get(URL).json() == r.json()
    assert json.loads(paths.settings.read_text(encoding="utf-8")) == {
        "reco": {"n_problems": 8},
        "budget_usd_month": 12.5,
    }  # Review Focus 4: only what the tutor changed, so later code defaults still apply
    assert app.state.settings["reco"]["n_problems"] == 8 and app.state.settings["reco"]["ratios"]["zpd"] == 0.5
    client.patch(URL, json={"reco": {"no_repeat_days": 0}}, headers=W)
    assert json.loads(paths.settings.read_text(encoding="utf-8"))["reco"] == {"n_problems": 8, "no_repeat_days": 0}
    with started(paths) as c2:  # a new start reads the file
        assert c2.get(URL).json()["reco"] == {"n_problems": 8, "no_repeat_days": 0}


@pytest.mark.parametrize(
    "body",
    [
        {"reco": {"n_problems": 13}},
        {"reco": {"n_problems": 2}},
        {"reco": {"no_repeat_days": -1}},
        {"reco": {"no_repeat_days": 121}},
        {"reco": {"n_problems": 6.5}},
        {"budget_usd_month": -1},
        {"models": {"00": "openai:x"}},
        {"reco": {"ratios": {"zpd": 1}}},
        {"app": {"port": 1}},
    ],
)
def test_patch_out_of_range_422(paths, client, body):
    r = client.patch(URL, json=body, headers=W)
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    assert not paths.settings.exists()


def test_patch_refused_when_settings_corrupt(paths):
    paths.settings.write_bytes(b"{oops \xff")
    with started(paths) as c:
        shown = c.get(URL).json()["settings_error"]
        assert shown == "settings.json hỏng, nhờ người cài sửa."  # no path, no parser text
        assert str(paths.root) not in shown
        r = c.patch(URL, json={"reco": {"n_problems": 8}}, headers=W)
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "not_ready"
        assert r.json()["error"]["message"] == "settings.json hỏng, sửa tay trước"
        assert put(c, {"provider": "openai", "key": KEY}).status_code == 200  # the key needs no settings.json
    assert paths.settings.read_bytes() == b"{oops \xff"


def test_key_saved_never_echoed(paths, client):
    r = put(client, {"provider": "openai", "key": f"  {KEY}\n"})
    assert r.status_code == 200 and r.json() == {"keys": {"openai": True}}
    env = paths.root / ".env"
    assert env.read_text(encoding="utf-8").splitlines() == [f"OPENAI_API_KEY={KEY}"]
    assert stat.S_IMODE(env.stat().st_mode) == 0o600
    g = client.get(URL)
    assert g.json()["keys"] == {"openai": True}
    client.patch(URL, json={"reco": {"n_problems": 7}}, headers=W)
    assert KEY not in g.text and KEY not in r.text and KEY not in paths.settings.read_text(encoding="utf-8")
    assert KEY not in app_log(paths)
    assert not (paths.logs / "llm.jsonl").exists() or KEY not in (paths.logs / "llm.jsonl").read_text(encoding="utf-8")
    # a bad key: 422 that holds neither it nor any key, and nothing is written
    for bad in ("sk bad", "short", "x" * 501, "sk-test-" + "é" * 30, "sk-test-" + "a" * 30 + "\n" + "b" * 30):
        r = put(client, {"provider": "openai", "key": bad})
        assert r.status_code == 422 and r.json()["error"]["message"] == "Khoá không đúng dạng"
        assert bad not in r.text and KEY not in r.text
    assert env.read_text(encoding="utf-8").splitlines() == [f"OPENAI_API_KEY={KEY}"]
    r = put(client, {"provider": "anthropic", "key": KEY2})
    assert r.status_code == 422 and r.json()["error"]["message"] == "Không dùng provider này"
    assert KEY2 not in r.text and "ANTHROPIC_API_KEY" not in env.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "send",
    [
        lambda c: c.put(PUT, json={"key": KEY}, headers=W),  # pydantic would echo the whole body as `input`
        lambda c: c.put(PUT, json={"provider": "openai"}, headers=W),
        lambda c: c.put(PUT, json={"provider": "openai", "key": [KEY]}, headers=W),
        lambda c: c.put(PUT, json={"provider": ["openai"], "key": KEY}, headers=W),
        lambda c: c.put(PUT, json={"provider": "openai", "key": KEY + "é"}, headers=W),
        lambda c: c.put(PUT, json=KEY, headers=W),
        lambda c: c.put(PUT, json=[KEY], headers=W),
        lambda c: c.put(PUT, content=KEY, headers=JSON),
        lambda c: c.put(PUT, content=f'{{"provider": "openai", "key": "{KEY}"', headers=JSON),
    ],
)
def test_malformed_key_body_422_never_echoes(paths, client, send):
    r = send(client)
    assert r.status_code == 422 and KEY not in r.text
    assert not (paths.root / ".env").exists() and not os.environ.get("OPENAI_API_KEY")


def test_key_write_failure_leaks_nothing(paths, app):
    (paths.root / ".env").mkdir()  # the write cannot succeed
    with TestClient(app, base_url=f"http://127.0.0.1:{PORT}", raise_server_exceptions=False) as c:
        r = put(c, {"provider": "openai", "key": KEY})
    assert r.status_code == 500 and KEY not in r.text
    assert KEY not in app_log(paths) and not os.environ.get("OPENAI_API_KEY")


@pytest.mark.parametrize(
    ("method", "url", "body"),
    [("PUT", PUT, {"provider": "openai", "key": KEY}), ("PATCH", URL, {"budget_usd_month": 5})],
)
def test_writes_need_the_x_tutor_header(paths, client, method, url, body):
    r = client.request(method, url, json=body)
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden" and KEY not in r.text
    assert not (paths.root / ".env").exists() and not paths.settings.exists()
    assert not os.environ.get("OPENAI_API_KEY")


def test_unreadable_env_file_is_a_500_that_quotes_nothing(paths, app):
    env = paths.root / ".env"
    env.write_bytes(b"A=\xff\xfe\n")  # not UTF-8: a ValueError here would read as "Khoá không đúng dạng"
    with TestClient(app, base_url=f"http://127.0.0.1:{PORT}", raise_server_exceptions=False) as c:
        r = put(c, {"provider": "openai", "key": KEY})
    assert r.status_code == 500 and r.json()["error"]["code"] == "internal"
    assert KEY not in r.text and "0xff" not in r.text and "Khoá không đúng dạng" not in r.text
    log = app_log(paths)
    assert KEY not in log and "UnicodeDecodeError" not in log and "0xff" not in log
    assert env.read_bytes() == b"A=\xff\xfe\n" and not os.environ.get("OPENAI_API_KEY")


def test_second_key_takes_effect(paths, client, monkeypatch):
    built = object()  # a real backend made with the first (wrong) key
    monkeypatch.setitem(llm._live, "openai", built)
    assert put(client, {"provider": "openai", "key": KEY}).status_code == 200
    assert os.environ["OPENAI_API_KEY"] == KEY and "openai" not in llm._live
    monkeypatch.setitem(llm._live, "openai", built)
    assert put(client, {"provider": "openai", "key": KEY2}).json() == {"keys": {"openai": True}}
    assert os.environ["OPENAI_API_KEY"] == KEY2 and "openai" not in llm._live
    assert (paths.root / ".env").read_text(encoding="utf-8").splitlines() == [f"OPENAI_API_KEY={KEY2}"]
