from datetime import datetime, timedelta, timezone

from tests.conftest import auth_header, create_employee, register_hr


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _capture_invitation_token(monkeypatch):
    captured_urls = []

    def _capture(to_email, employee_name, campaign_name, access_url):
        from app.services.email_service import EmailSendResult

        captured_urls.append(access_url)
        return EmailSendResult(success=True, provider_response="captured")

    import app.services.invitation_service as invitation_service_module

    monkeypatch.setattr(invitation_service_module.email_service, "send_invitation", _capture)
    return captured_urls


def _complete_interview(client, mock_clerk_user, monkeypatch, hr_headers, employee_payload, campaign_id, clerk_employee_id, result):
    captured_urls = _capture_invitation_token(monkeypatch)
    client.post(
        f"/api/v1/hr/campaigns/{campaign_id}/invitations",
        json={"employee_ids": [employee_payload["id"]]},
        headers=hr_headers,
    )
    raw_token = captured_urls[-1].split("token=")[1]

    mock_clerk_user(clerk_employee_id)
    employee_headers = auth_header(f"token-{clerk_employee_id}")
    client.post("/api/v1/auth/employee-access", json={"token": raw_token}, headers=employee_headers)
    start = client.post("/api/v1/employee/interview/start", headers=employee_headers)
    ai_session_id = start.json()["session_id"]

    from app.core.config import settings

    monkeypatch.setattr(settings, "AI_INTERNAL_WEBHOOK_SECRET", "test-webhook-secret")
    client.post(
        "/api/v1/internal/ai/interview-completed",
        json={"ai_session_id": ai_session_id, "status": "COMPLETED", "result": result},
        headers={"X-Webhook-Secret": "test-webhook-secret"},
    )


def _setup_company_with_completed_interview(client, mock_clerk_user, monkeypatch, *, clerk_hr_id, clerk_employee_id, company_name, hr_email, employee_email):
    hr_headers = register_hr(client, mock_clerk_user, clerk_hr_id, company_name, hr_email)
    now = datetime.now(timezone.utc)
    emp = create_employee(client, hr_headers, employee_id="R1", email=employee_email, department="Engineering")

    campaign = client.post(
        "/api/v1/hr/campaigns",
        json={
            "name": "Report Test Campaign",
            "start_at": _iso(now - timedelta(minutes=1)),
            "end_at": _iso(now + timedelta(hours=1)),
            "employee_ids": [emp["id"]],
        },
        headers=hr_headers,
    ).json()

    _complete_interview(
        client, mock_clerk_user, monkeypatch, hr_headers, emp, campaign["id"], clerk_employee_id,
        {"summary": "Left for growth.", "satisfaction_score": 8.0, "exit_reasons": ["Growth"], "themes": ["Career"], "recommendations": ["More mentorship"]},
    )
    return hr_headers, emp, campaign


def test_generate_company_wide_pdf_report(client, mock_clerk_user, monkeypatch):
    hr_headers, emp, campaign = _setup_company_with_completed_interview(
        client, mock_clerk_user, monkeypatch,
        clerk_hr_id="clerk_rp_1_hr", clerk_employee_id="clerk_rp_1_emp",
        company_name="Report Co A", hr_email="hr@reportco-a.com", employee_email="e1@reportco-a.com",
    )

    response = client.post("/api/v1/hr/reports/generate", json={"format": "PDF"}, headers=hr_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "COMPLETED"
    assert body["format"] == "PDF"
    assert body["campaign_id"] is None
    assert body["file_name"].endswith(".pdf")

    download = client.get(f"/api/v1/hr/reports/{body['id']}/download", headers=hr_headers)
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"
    assert download.content[:4] == b"%PDF"


def test_generate_campaign_scoped_excel_report(client, mock_clerk_user, monkeypatch):
    hr_headers, emp, campaign = _setup_company_with_completed_interview(
        client, mock_clerk_user, monkeypatch,
        clerk_hr_id="clerk_rp_2_hr", clerk_employee_id="clerk_rp_2_emp",
        company_name="Report Co B", hr_email="hr@reportco-b.com", employee_email="e1@reportco-b.com",
    )

    response = client.post(
        "/api/v1/hr/reports/generate", json={"format": "EXCEL", "campaign_id": campaign["id"]}, headers=hr_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "COMPLETED"
    assert body["campaign_id"] == campaign["id"]

    download = client.get(f"/api/v1/hr/reports/{body['id']}/download", headers=hr_headers)
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert download.content[:2] == b"PK"


def test_generate_report_for_nonexistent_campaign_404s(client, mock_clerk_user):
    hr_headers = register_hr(client, mock_clerk_user, "clerk_rp_3_hr", "Report Co C", "hr@reportco-c.com")
    fake_id = "00000000-0000-0000-0000-000000000000"
    response = client.post("/api/v1/hr/reports/generate", json={"format": "PDF", "campaign_id": fake_id}, headers=hr_headers)
    assert response.status_code == 404


def test_list_reports_pagination(client, mock_clerk_user):
    hr_headers = register_hr(client, mock_clerk_user, "clerk_rp_4_hr", "Report Co D", "hr@reportco-d.com")
    client.post("/api/v1/hr/reports/generate", json={"format": "PDF"}, headers=hr_headers)
    client.post("/api/v1/hr/reports/generate", json={"format": "EXCEL"}, headers=hr_headers)

    listing = client.get("/api/v1/hr/reports", headers=hr_headers)
    assert listing.status_code == 200
    assert listing.json()["total"] == 2


def test_company_a_cannot_access_company_b_report(client, mock_clerk_user):
    hr_headers_a = register_hr(client, mock_clerk_user, "clerk_rp_5a_hr", "Report Co E", "hr@reportco-e.com")
    created = client.post("/api/v1/hr/reports/generate", json={"format": "PDF"}, headers=hr_headers_a).json()

    hr_headers_b = register_hr(client, mock_clerk_user, "clerk_rp_5b_hr", "Report Co F", "hr@reportco-f.com")
    response = client.get(f"/api/v1/hr/reports/{created['id']}", headers=hr_headers_b)
    assert response.status_code == 404

    download = client.get(f"/api/v1/hr/reports/{created['id']}/download", headers=hr_headers_b)
    assert download.status_code == 404


def test_employee_role_cannot_generate_reports(client, mock_clerk_user, db_session):
    hr_headers = register_hr(client, mock_clerk_user, "clerk_rp_6_hr", "Report Co G", "hr@reportco-g.com")
    me = client.get("/api/v1/me", headers=hr_headers).json()

    from tests.conftest import create_employee_user

    create_employee_user(db_session, me["company_id"], "clerk_rp_6_emp", "worker@reportco-g.com")

    mock_clerk_user("clerk_rp_6_emp")
    response = client.post(
        "/api/v1/hr/reports/generate", json={"format": "PDF"}, headers=auth_header("token-clerk_rp_6_emp")
    )
    assert response.status_code == 403
