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


def _onboard_and_start_interview(client, mock_clerk_user, monkeypatch, *, clerk_hr_id, clerk_employee_id, company_name, hr_email, employee_email):
    headers = register_hr(client, mock_clerk_user, clerk_hr_id, company_name, hr_email)
    emp = create_employee(client, headers, employee_id="E1", email=employee_email)

    now = datetime.now(timezone.utc)
    campaign = client.post(
        "/api/v1/hr/campaigns",
        json={
            "name": "Completion Test Campaign",
            "start_at": _iso(now - timedelta(minutes=1)),
            "end_at": _iso(now + timedelta(hours=1)),
            "employee_ids": [emp["id"]],
        },
        headers=headers,
    ).json()

    captured_urls = _capture_invitation_token(monkeypatch)
    client.post(f"/api/v1/hr/campaigns/{campaign['id']}/invitations", json={}, headers=headers)
    raw_token = captured_urls[0].split("token=")[1]

    mock_clerk_user(clerk_employee_id)
    employee_headers = auth_header(f"token-{clerk_employee_id}")
    client.post("/api/v1/auth/employee-access", json={"token": raw_token}, headers=employee_headers)

    start = client.post("/api/v1/employee/interview/start", headers=employee_headers)
    assert start.status_code == 200
    ai_session_id = start.json()["session_id"]

    return headers, emp, campaign, employee_headers, ai_session_id


def _webhook(client, payload, secret="test-webhook-secret"):
    return client.post(
        "/api/v1/internal/ai/interview-completed", json=payload, headers={"X-Webhook-Secret": secret}
    )


def test_webhook_requires_valid_secret(client, mock_clerk_user, monkeypatch):
    _, _, _, _, ai_session_id = _onboard_and_start_interview(
        client,
        mock_clerk_user,
        monkeypatch,
        clerk_hr_id="clerk_c7_1_hr",
        clerk_employee_id="clerk_c7_1_emp",
        company_name="Nimbus Co",
        hr_email="hr@nimbus.com",
        employee_email="emp@nimbus.com",
    )

    from app.core.config import settings

    monkeypatch.setattr(settings, "AI_INTERNAL_WEBHOOK_SECRET", "correct-secret")

    wrong = client.post(
        "/api/v1/internal/ai/interview-completed",
        json={"ai_session_id": ai_session_id, "status": "COMPLETED"},
        headers={"X-Webhook-Secret": "wrong-secret"},
    )
    assert wrong.status_code == 401

    missing = client.post(
        "/api/v1/internal/ai/interview-completed", json={"ai_session_id": ai_session_id, "status": "COMPLETED"}
    )
    assert missing.status_code == 401


def test_webhook_completes_interview_and_propagates_status(client, mock_clerk_user, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "AI_INTERNAL_WEBHOOK_SECRET", "test-webhook-secret")

    hr_headers, emp, campaign, employee_headers, ai_session_id = _onboard_and_start_interview(
        client,
        mock_clerk_user,
        monkeypatch,
        clerk_hr_id="clerk_c7_2_hr",
        clerk_employee_id="clerk_c7_2_emp",
        company_name="Orion Co",
        hr_email="hr@orion.com",
        employee_email="emp@orion.com",
    )

    response = _webhook(
        client,
        {
            "ai_session_id": ai_session_id,
            "status": "COMPLETED",
            "result": {
                "summary": "Left for better pay.",
                "satisfaction_score": 7.5,
                "exit_reasons": ["Compensation"],
                "themes": ["Growth"],
                "recommendations": ["Review pay bands"],
            },
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "COMPLETED"

    # Employee-side status reflects completion.
    mock_clerk_user("clerk_c7_2_emp")
    status_resp = client.get("/api/v1/employee/interview/status", headers=employee_headers)
    assert status_resp.json()["status"] == "COMPLETED"

    # Employee record status updated.
    employee_detail = client.get(f"/api/v1/hr/employees/{emp['id']}", headers=hr_headers).json()
    assert employee_detail["status"] == "INTERVIEW_COMPLETED"

    # Campaign detail shows the assignment as completed.
    campaign_detail = client.get(f"/api/v1/hr/campaigns/{campaign['id']}", headers=hr_headers).json()
    assert campaign_detail["assignments"][0]["interview_status"] == "COMPLETED"
    assert campaign_detail["completed_count"] == 1

    # Re-starting the interview is now rejected.
    restart = client.post("/api/v1/employee/interview/start", headers=employee_headers)
    assert restart.status_code == 409
    assert restart.json()["error"]["code"] == "INTERVIEW_ALREADY_COMPLETED"


def test_webhook_is_idempotent_on_redelivery(client, mock_clerk_user, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "AI_INTERNAL_WEBHOOK_SECRET", "test-webhook-secret")

    hr_headers, emp, campaign, employee_headers, ai_session_id = _onboard_and_start_interview(
        client,
        mock_clerk_user,
        monkeypatch,
        clerk_hr_id="clerk_c7_3_hr",
        clerk_employee_id="clerk_c7_3_emp",
        company_name="Polaris Co",
        hr_email="hr@polaris.com",
        employee_email="emp@polaris.com",
    )

    payload = {
        "ai_session_id": ai_session_id,
        "status": "COMPLETED",
        "result": {"summary": "Fine.", "satisfaction_score": 5.0},
    }
    first = _webhook(client, payload)
    assert first.status_code == 200

    second = _webhook(client, payload)
    assert second.status_code == 200
    assert second.json()["status"] == "COMPLETED"

    # Only one InterviewResult should exist — verified indirectly via
    # analytics not double-counting this company's single completion.
    analytics = client.get("/api/v1/hr/analytics", headers=hr_headers)
    assert analytics.json()["total_completed"] == 1


def test_webhook_unknown_session_returns_404(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "AI_INTERNAL_WEBHOOK_SECRET", "test-webhook-secret")

    response = _webhook(client, {"ai_session_id": "totally-unknown", "status": "COMPLETED"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
