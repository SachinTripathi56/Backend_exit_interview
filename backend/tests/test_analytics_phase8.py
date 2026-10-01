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


def _complete_interview_for(client, mock_clerk_user, monkeypatch, hr_headers, employee_payload, campaign_id, clerk_employee_id, result):
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


def test_analytics_aggregates_across_completed_interviews(client, mock_clerk_user, monkeypatch):
    hr_headers = register_hr(client, mock_clerk_user, "clerk_an_1_hr", "Nebula Co", "hr@nebula.com")

    now = datetime.now(timezone.utc)
    emp1 = create_employee(client, hr_headers, employee_id="N1", email="n1@nebula.com", department="Engineering")
    emp2 = create_employee(client, hr_headers, employee_id="N2", email="n2@nebula.com", department="Engineering")
    emp3 = create_employee(client, hr_headers, employee_id="N3", email="n3@nebula.com", department="Sales")

    campaign = client.post(
        "/api/v1/hr/campaigns",
        json={
            "name": "Analytics Campaign",
            "start_at": _iso(now - timedelta(minutes=1)),
            "end_at": _iso(now + timedelta(hours=1)),
            "employee_ids": [emp1["id"], emp2["id"], emp3["id"]],
        },
        headers=hr_headers,
    ).json()

    _complete_interview_for(
        client, mock_clerk_user, monkeypatch, hr_headers, emp1, campaign["id"], "clerk_an_1_e1",
        {"summary": "Left for pay.", "satisfaction_score": 8.0, "exit_reasons": ["Compensation"], "themes": ["Management"], "recommendations": ["Raise budgets"]},
    )
    _complete_interview_for(
        client, mock_clerk_user, monkeypatch, hr_headers, emp2, campaign["id"], "clerk_an_1_e2",
        {"summary": "Wanted growth.", "satisfaction_score": 6.0, "exit_reasons": ["Compensation", "Growth"], "themes": ["Management"], "recommendations": ["Raise budgets"]},
    )
    _complete_interview_for(
        client, mock_clerk_user, monkeypatch, hr_headers, emp3, campaign["id"], "clerk_an_1_e3",
        {"summary": "Relocation.", "satisfaction_score": 9.0, "exit_reasons": ["Relocation"], "themes": ["Culture"], "recommendations": ["Remote options"]},
    )

    response = client.get("/api/v1/hr/analytics", headers=hr_headers)
    assert response.status_code == 200
    body = response.json()

    assert body["total_assigned"] == 3
    assert body["total_completed"] == 3
    assert body["completion_rate"] == 100.0
    assert body["overall_satisfaction"] == round((8.0 + 6.0 + 9.0) / 3, 2)

    dept_participation = {d["department"]: d for d in body["department_participation"]}
    assert dept_participation["Engineering"]["assigned_count"] == 2
    assert dept_participation["Engineering"]["completed_count"] == 2
    assert dept_participation["Sales"]["completed_count"] == 1

    reasons = {r["label"]: r["count"] for r in body["common_exit_reasons"]}
    assert reasons["Compensation"] == 2

    # 3 completed results meets the privacy threshold -> comments included.
    assert len(body["key_comments"]) == 3

    # No employee-identifying fields anywhere in the top-level response shape.
    for key in body:
        assert key not in ("employee_id", "employee_name", "transcript")


def test_analytics_hides_key_comments_below_privacy_threshold(client, mock_clerk_user, monkeypatch):
    hr_headers = register_hr(client, mock_clerk_user, "clerk_an_2_hr", "Vega Co", "hr@vega.com")
    now = datetime.now(timezone.utc)
    emp = create_employee(client, hr_headers, employee_id="V1", email="v1@vega.com", department="Engineering")

    campaign = client.post(
        "/api/v1/hr/campaigns",
        json={
            "name": "Small Campaign",
            "start_at": _iso(now - timedelta(minutes=1)),
            "end_at": _iso(now + timedelta(hours=1)),
            "employee_ids": [emp["id"]],
        },
        headers=hr_headers,
    ).json()

    _complete_interview_for(
        client, mock_clerk_user, monkeypatch, hr_headers, emp, campaign["id"], "clerk_an_2_e1",
        {"summary": "This would be identifiable in a company this small.", "satisfaction_score": 5.0},
    )

    response = client.get("/api/v1/hr/analytics", headers=hr_headers).json()
    assert response["total_completed"] == 1
    assert response["key_comments"] == []


def test_analytics_scoped_to_company(client, mock_clerk_user, monkeypatch):
    hr_headers_a = register_hr(client, mock_clerk_user, "clerk_an_3_hr_a", "Willow Co", "hr@willow.com")
    now = datetime.now(timezone.utc)
    emp = create_employee(client, hr_headers_a, employee_id="W1", email="w1@willow.com")
    campaign = client.post(
        "/api/v1/hr/campaigns",
        json={
            "name": "Willow Campaign",
            "start_at": _iso(now - timedelta(minutes=1)),
            "end_at": _iso(now + timedelta(hours=1)),
            "employee_ids": [emp["id"]],
        },
        headers=hr_headers_a,
    ).json()
    _complete_interview_for(
        client, mock_clerk_user, monkeypatch, hr_headers_a, emp, campaign["id"], "clerk_an_3_emp",
        {"summary": "x", "satisfaction_score": 3.0},
    )

    hr_headers_b = register_hr(client, mock_clerk_user, "clerk_an_3_hr_b", "Yew Co", "hr@yew.com")
    response = client.get("/api/v1/hr/analytics", headers=hr_headers_b).json()
    assert response["total_completed"] == 0
    assert response["overall_satisfaction"] is None
