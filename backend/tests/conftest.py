"""Test fixtures: isolated SQLite file per test session, schema reset per test."""
import os
import tempfile
from pathlib import Path

# Must be set before the app (and its engine) is imported.
_tmp = Path(tempfile.mkdtemp(prefix="hub-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_tmp / 'test.db').as_posix()}"
os.environ["ENVIRONMENT"] = "test"
os.environ["SCHEDULER_MODE"] = "off"
os.environ["EMAIL_PROVIDER"] = "none"
# The developer's real backend/.env must never leak into tests: AI off, no keys (a test must never call a live provider).
os.environ["AI_PROVIDER"] = "none"
for _k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY", "GITHUB_TOKEN"):
    os.environ[_k] = ""
os.environ.setdefault("SECRET_KEY", "test-secret-key-test-secret-key-0123456789")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.models  # noqa: E402,F401
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
