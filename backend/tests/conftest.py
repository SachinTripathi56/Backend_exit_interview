"""
Shared test fixtures.

Tests run against a real Postgres instance (Neon-compatible SQL, including
UUID/enum types actually used in production) rather than SQLite, since the
schema relies on Postgres-specific types. Point TEST_DATABASE_URL at a
throwaway database — e.g. the `db` service in docker-compose.yml:

    TEST_DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/exit_interview_test

Clerk token verification is monkeypatched in these tests: we're testing our
own authorization/tenant logic, not Clerk's signature verification, which
has no business logic of ours to break.
"""
from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.database import Base, get_db
from app.main import app

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://user:password@localhost:5432/exit_interview_test",
)


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(TEST_DATABASE_URL)
    # Import all models so metadata is complete before create_all.
    from app.models import (
        audit_log,
        campaign,
        campaign_employee,
        company,
        email_log,
        employee,
        employee_import,
        employee_invitation,
        interview_result,
        interview_session,
        report,
        user,
    )  # noqa: F401

    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture()
def db_session(engine):
    connection = engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(bind=connection, autoflush=False, autocommit=False)
    session = SessionLocal()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(autouse=True)
def _disable_rate_limiting_by_default(monkeypatch):
    """
    The rate limiter's counters are process-lifetime, not per-request, and
    every test's TestClient reports the same fake client IP — so without
    this, unrelated tests across the whole suite would share one bucket
    and start tripping 429s on each other after ~10 total calls to
    register-company. Disabled globally here; the one test that actually
    exercises the limiter (test_rate_limit_triggers_on_register_company)
    re-enables it and resets counters for just that test.
    """
    from app.core.config import settings
    from app.core.middleware import reset_rate_limits

    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    reset_rate_limits()
    yield
    reset_rate_limits()


@pytest.fixture()
def client(db_session, monkeypatch):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    yield TestClient(app)

    app.dependency_overrides.clear()


@pytest.fixture()
def mock_clerk_user(monkeypatch):
    """
    Patch verify_clerk_token so tests can simulate "as" any Clerk user
    without real signature verification. Returns a factory you call with
    the desired clerk_user_id.
    """
    from app.core.security import ClerkClaims

    def _apply(clerk_user_id: str = "clerk_test_user"):
        import app.api.dependencies as deps
        import app.api.v1.auth as auth_module

        claims = ClerkClaims(clerk_user_id=clerk_user_id, email="test@example.com", raw={})

        monkeypatch.setattr(deps, "verify_clerk_token", lambda token: claims)
        monkeypatch.setattr(auth_module, "verify_clerk_token", lambda token: claims)
        return clerk_user_id

    return _apply


def auth_header(token: str = "any-token") -> dict:
    return {"Authorization": f"Bearer {token}"}


def register_hr(client, mock_clerk_user, clerk_user_id: str, company_name: str, email: str) -> dict:
    """Convenience helper: provisions a company + HR_ADMIN and returns auth headers for them."""
    mock_clerk_user(clerk_user_id)
    response = client.post(
        "/api/v1/auth/register-company",
        json={"company_name": company_name, "name": "Test HR", "email": email},
        headers=auth_header(f"token-{clerk_user_id}"),
    )
    assert response.status_code == 200, response.text
    return auth_header(f"token-{clerk_user_id}")


def create_employee_user(db_session, company_id, clerk_user_id: str, email: str):
    """Directly inserts a User row with role=EMPLOYEE, bypassing the (not-yet-built)
    invitation flow, since employee self-registration isn't in scope until Phase 5."""
    import uuid as _uuid

    from app.models.user import User, UserRole

    user = User(
        id=_uuid.uuid4(),
        clerk_user_id=clerk_user_id,
        company_id=company_id,
        role=UserRole.EMPLOYEE,
        name="Test Employee",
        email=email,
    )
    db_session.add(user)
    db_session.flush()
    return user


def create_employee(client, headers, **overrides) -> dict:
    """Convenience helper for phase 4+ tests that don't care about import validation details."""
    payload = {
        "name": "Test Employee",
        "email": "employee@example.com",
        "employee_id": "EMPX1",
        "department": "Engineering",
        "designation": "Engineer",
    }
    payload.update(overrides)
    response = client.post("/api/v1/hr/employees", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()
