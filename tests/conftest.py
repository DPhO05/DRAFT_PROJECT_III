import pytest

from tests.fakes import FakeLLM
from tutor import config, llm
from tutor.db import repo


@pytest.fixture(autouse=True)
def no_real_llm(monkeypatch):
    """C-34: tests never reach the Anthropic API; an agent call no test expected fails with KeyError."""
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
