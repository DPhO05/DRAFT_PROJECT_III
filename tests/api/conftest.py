import pytest
from fastapi.testclient import TestClient

from tutor.api.app import create_app
from tutor.db import repo

PORT = 8000


@pytest.fixture
def app(paths):
    repo.init_db(paths.tutor_db, paths.backup)
    return create_app(paths, port=PORT)


@pytest.fixture
def client(app):
    with TestClient(app, base_url=f"http://127.0.0.1:{PORT}") as c:
        yield c
