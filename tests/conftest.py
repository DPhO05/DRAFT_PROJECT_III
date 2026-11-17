import pytest

from tests.fakes import FakeLLM
from tutor import config, llm
from tutor.db import repo


@pytest.fixture(autouse=True)
def no_real_llm(monkeypatch, tmp_path):
    """C-34: tests never reach the Anthropic API; an agent call no test expected fails with KeyError."""
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "absent.env")  # nor read the repo .env
    for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):  # nor the developer's shell
        monkeypatch.setenv(k, "")  # records the original, so a key a test sets is undone too
        monkeypatch.delenv(k)
    config.no_tracing()  # a shell with LANGSMITH_TRACING=true must not send test traces
    llm.set_backend(FakeLLM({}))
    monkeypatch.setattr(llm, "_last_result", "unknown")
    monkeypatch.setattr(llm, "_sleep", lambda s: None)
    yield
    llm.set_backend(None)


@pytest.fixture
def paths(tmp_path):
    return config.paths(tmp_path / "data").ensure()


@pytest.fixture
def conn(paths):
    repo.init_db(paths.tutor_db, paths.backup)
    c = repo.connect(paths.tutor_db)
    yield c
    c.close()
