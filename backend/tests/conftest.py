"""Shared test fixtures.  Owner: Pile 1 (Platform) — put extra fixtures in your own test files.

- `session`: a Session on a fresh in-memory SQLite DB (per test)
- `client`:  FastAPI TestClient whose requests use that same DB
The app lifespan (background loop) does NOT run in tests.
"""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app import models  # noqa: F401  (registers the tables)
from app.db import get_session
from app.main import app


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


@pytest.fixture
def client(engine):
    def _session_override():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = _session_override
    yield TestClient(app)  # no `with`: lifespan/background loop stays off
    app.dependency_overrides.clear()
