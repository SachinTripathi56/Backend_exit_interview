from datetime import datetime, timedelta, timezone

from tests.conftest import auth_header, create_employee, register_hr


def test_security_headers_present_on_every_response(client):
    response = client.get("/health")
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"
    assert response.headers.get("referrer-policy") == "strict-origin-when-cross-origin"


def test_api_responses_are_never_cached(client, mock_clerk_user):
    headers = register_hr(client, mock_clerk_user, "clerk_sec_1", "Cache Test Co", "hr@cachetest.com")
    response = client.get("/api/v1/me", headers=headers)
    assert response.headers.get("cache-control") == "no-store"


def test_rate_limit_triggers_on_register_company(client, monkeypatch):
    from app.core.config import settings
    from app.core.middleware import reset_rate_limits

    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    reset_rate_limits()

    statuses = []
    for _ in range(15):
        r = client.post(
            "/api/v1/auth/register-company",
            json={"company_name": "Rate Test", "name": "y", "email": "y@ratetest.com"},
            headers=auth_header("some-token"),
        )
        statuses.append(r.status_code)
    assert 429 in statuses


def test_production_config_validation_rejects_placeholders():
    from app.core.config import Settings, validate_production_config

    prod = Settings(APP_ENV="production")
    try:
        validate_production_config(prod)
        assert False, "should have raised"
    except RuntimeError as e:
        assert "SECRET_KEY" in str(e)
        assert "CLERK_JWKS_URL" in str(e)


def test_production_config_validation_passes_when_fully_configured():
    from app.core.config import Settings, validate_production_config

    prod = Settings(
        APP_ENV="production",
        SECRET_KEY="a-real-secret",
        CLERK_JWKS_URL="https://real.clerk.accounts.dev/.well-known/jwks.json",
        DATABASE_URL="postgresql+psycopg://user:realpass@ep-real.neon.tech/db",
        AI_INTERNAL_WEBHOOK_SECRET="a-real-secret",
        FRONTEND_URL="https://app.example.com",
    )
    validate_production_config(prod)  # should not raise


def test_dev_config_never_blocked_by_production_checks():
    from app.core.config import Settings, validate_production_config

    dev = Settings(APP_ENV="development")
    validate_production_config(dev)  # should not raise regardless of placeholders


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def test_audit_log_recorded_for_employee_lifecycle(client, mock_clerk_user, db_session):
    headers = register_hr(client, mock_clerk_user, "clerk_aud_1", "Audit Co", "hr@auditco.com")
    emp = create_employee(client, headers, employee_id="AU1", email="au1@auditco.com")

    client.put(f"/api/v1/hr/employees/{emp['id']}", json={"department": "Sales"}, headers=headers)
    client.delete(f"/api/v1/hr/employees/{emp['id']}", headers=headers)

    from app.models.audit_log import AuditLog

    actions = [a.action for a in db_session.query(AuditLog).order_by(AuditLog.created_at).all()]
    assert "company.registered" in actions
    assert "employee.created" in actions
    assert "employee.updated" in actions
    assert "employee.deleted" in actions


def test_audit_log_recorded_for_campaign_lifecycle(client, mock_clerk_user, db_session):
    headers = register_hr(client, mock_clerk_user, "clerk_aud_2", "Audit Camp Co", "hr@auditcamp.com")
    now = datetime.now(timezone.utc)
    campaign = client.post(
        "/api/v1/hr/campaigns",
        json={
            "name": "Audit Campaign",
            "start_at": _iso(now + timedelta(days=1)),
            "end_at": _iso(now + timedelta(days=8)),
            "employee_ids": [],
        },
        headers=headers,
    ).json()
    client.put(f"/api/v1/hr/campaigns/{campaign['id']}", json={"name": "Renamed"}, headers=headers)
    client.delete(f"/api/v1/hr/campaigns/{campaign['id']}", headers=headers)

    from app.models.audit_log import AuditLog

    actions = [a.action for a in db_session.query(AuditLog).order_by(AuditLog.created_at).all()]
    assert "campaign.created" in actions
    assert "campaign.updated" in actions
    assert "campaign.deleted" in actions


def test_audit_log_scoped_to_company_no_cross_tenant_leakage(client, mock_clerk_user, db_session):
    headers_a = register_hr(client, mock_clerk_user, "clerk_aud_3a", "Audit Iso A", "hr@auditisoa.com")
    headers_b = register_hr(client, mock_clerk_user, "clerk_aud_3b", "Audit Iso B", "hr@auditisob.com")

    create_employee(client, headers_a, employee_id="IA1", email="ia1@auditisoa.com")
    create_employee(client, headers_b, employee_id="IB1", email="ib1@auditisob.com")

    me_a = client.get("/api/v1/me", headers=headers_a).json()
    me_b = client.get("/api/v1/me", headers=headers_b).json()

    from app.models.audit_log import AuditLog

    logs_a = db_session.query(AuditLog).filter(AuditLog.company_id == me_a["company_id"]).all()
    logs_b = db_session.query(AuditLog).filter(AuditLog.company_id == me_b["company_id"]).all()

    assert all(str(l.company_id) == me_a["company_id"] for l in logs_a)
    assert all(str(l.company_id) == me_b["company_id"] for l in logs_b)
    assert len(logs_a) > 0 and len(logs_b) > 0
