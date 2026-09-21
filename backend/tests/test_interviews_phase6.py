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


def _onboard_employee_with_active_campaign(client, mock_clerk_user, db_session, monkeypatch, *, clerk_hr_id, clerk_employee_id, company_name, hr_email, employee_email, start_offset, end_offset):
    headers = register_hr(client, mock_clerk_user, clerk_hr_id, company_name, hr_email)
    emp = create_employee(client, headers, employee_id="E1", email=employee_email)

    now = datetime.now(timezone.utc)
    campaign = client.post(
        "/api/v1/hr/campaigns",
        json={
            "name": "Interview Campaign",
            "start_at": _iso(now + start_offset),
            "end_at": _iso(now + end_offset),
            "employee_ids": [emp["id"]],
        },
        headers=headers,
    ).json()

    captured_urls = _capture_invitation_token(monkeypatch)
    client.post(f"/api/v1/hr/campaigns/{campaign['id']}/invitations", json={}, headers=headers)
    raw_token = captured_urls[0].split("token=")[1]

    mock_clerk_user(clerk_employee_id)
    access = client.post(
        "/api/v1/auth/employee-access",
        json={"token": raw_token},
        headers=auth_header(f"token-{clerk_employee_id}"),
    )
    assert access.status_code == 200

    return headers, emp, campaign, auth_header(f"token-{clerk_employee_id}")


def test_start_interview_happy_path_uses_ai_stub(client, mock_clerk_user, db_session, monkeypatch):
    hr_headers, emp, campaign, employee_headers = _onboard_employee_with_active_campaign(
        client,
        mock_clerk_user,
        db_session,
        monkeypatch,
        clerk_hr_id="clerk_iv_1_hr",
        clerk_employee_id="clerk_iv_1_emp",
        company_name="Umbra Co",
        hr_email="hr@umbra.com",
        employee_email="emp@umbra.com",
        start_offset=timedelta(minutes=-1),
        end_offset=timedelta(hours=1),
    )

    response = client.post("/api/v1/employee/interview/start", headers=employee_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "IN_PROGRESS"
    assert body["session_id"].startswith("stub-")
    assert body["interview_url"] is not None

    status_resp = client.get("/api/v1/employee/interview/status", headers=employee_headers)
    assert status_resp.json()["status"] == "IN_PROGRESS"


def test_start_interview_is_idempotent(client, mock_clerk_user, db_session, monkeypatch):
    _, _, _, employee_headers = _onboard_employee_with_active_campaign(
        client,
        mock_clerk_user,
        db_session,
        monkeypatch,
        clerk_hr_id="clerk_iv_2_hr",
        clerk_employee_id="clerk_iv_2_emp",
        company_name="Vertex Co",
        hr_email="hr@vertex.com",
        employee_email="emp@vertex.com",
        start_offset=timedelta(minutes=-1),
        end_offset=timedelta(hours=1),
    )

    first = client.post("/api/v1/employee/interview/start", headers=employee_headers)
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["session_id"].startswith("stub-")

    second = client.post("/api/v1/employee/interview/start", headers=employee_headers)
    assert second.status_code == 200
    second_body = second.json()

    # Resuming an already IN_PROGRESS session must return the SAME
    # interview_id/session_id rather than creating a second AI session.
    assert second_body["interview_id"] == first_body["interview_id"]
    assert second_body["session_id"] == first_body["session_id"]
    assert second_body["status"] == "IN_PROGRESS"


def test_start_interview_before_campaign_window_is_rejected(client, mock_clerk_user, db_session, monkeypatch):
    _, _, _, employee_headers = _onboard_employee_with_active_campaign(
        client,
        mock_clerk_user,
        db_session,
        monkeypatch,
        clerk_hr_id="clerk_iv_3_hr",
        clerk_employee_id="clerk_iv_3_emp",
        company_name="Wren Co",
        hr_email="hr@wren.com",
        employee_email="emp@wren.com",
        start_offset=timedelta(hours=1),
        end_offset=timedelta(hours=2),
    )

    response = client.post("/api/v1/employee/interview/start", headers=employee_headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INTERVIEW_NOT_AVAILABLE"


def test_start_interview_after_campaign_window_is_rejected(client, mock_clerk_user, db_session, monkeypatch):
    _, _, _, employee_headers = _onboard_employee_with_active_campaign(
        client,
        mock_clerk_user,
        db_session,
        monkeypatch,
        clerk_hr_id="clerk_iv_4_hr",
        clerk_employee_id="clerk_iv_4_emp",
        company_name="Xenon Co",
        hr_email="hr@xenon.com",
        employee_email="emp@xenon.com",
        start_offset=timedelta(seconds=-2),
        end_offset=timedelta(seconds=2),
    )

    import time as _time

    _time.sleep(3)

    response = client.post("/api/v1/employee/interview/start", headers=employee_headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INTERVIEW_NOT_AVAILABLE"


def test_start_interview_when_already_completed_is_rejected(client, mock_clerk_user, db_session, monkeypatch):
    _, emp, campaign, employee_headers = _onboard_employee_with_active_campaign(
        client,
        mock_clerk_user,
        db_session,
        monkeypatch,
        clerk_hr_id="clerk_iv_5_hr",
        clerk_employee_id="clerk_iv_5_emp",
        company_name="Yara Co",
        hr_email="hr@yara.com",
        employee_email="emp@yara.com",
        start_offset=timedelta(minutes=-1),
        end_offset=timedelta(hours=1),
    )

    client.post("/api/v1/employee/interview/start", headers=employee_headers)

    # Simulate completion directly (Phase 7 will do this via the AI webhook).
    from app.models.campaign_employee import CampaignEmployee, CampaignInterviewStatus

    assignment = (
        db_session.query(CampaignEmployee)
        .filter(CampaignEmployee.campaign_id == campaign["id"], CampaignEmployee.employee_id == emp["id"])
        .first()
    )
    assignment.interview_status = CampaignInterviewStatus.COMPLETED
    db_session.flush()

    response = client.post("/api/v1/employee/interview/start", headers=employee_headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INTERVIEW_ALREADY_COMPLETED"


def test_start_interview_for_disabled_employee_is_forbidden(client, mock_clerk_user, db_session, monkeypatch):
    _, emp, campaign, employee_headers = _onboard_employee_with_active_campaign(
        client,
        mock_clerk_user,
        db_session,
        monkeypatch,
        clerk_hr_id="clerk_iv_6_hr",
        clerk_employee_id="clerk_iv_6_emp",
        company_name="Zircon Co",
        hr_email="hr@zircon.com",
        employee_email="emp@zircon.com",
        start_offset=timedelta(minutes=-1),
        end_offset=timedelta(hours=1),
    )

    from app.models.employee import Employee, EmployeeStatus
    import uuid as _uuid

    employee_row = db_session.get(Employee, _uuid.UUID(emp["id"]))
    employee_row.status = EmployeeStatus.DISABLED
    db_session.flush()

    response = client.post("/api/v1/employee/interview/start", headers=employee_headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_employee_without_assigned_campaign_gets_graceful_unavailable_view(client, mock_clerk_user, db_session):
    headers = register_hr(client, mock_clerk_user, "clerk_iv_7_hr", "Aurora Co", "hr@aurora.com")
    me = client.get("/api/v1/me", headers=headers).json()

    from tests.conftest import create_employee_user

    create_employee_user(db_session, me["company_id"], "clerk_iv_7_emp", "unassigned@aurora.com")

    mock_clerk_user("clerk_iv_7_emp")
    response = client.get("/api/v1/employee/interview", headers=auth_header("token-clerk_iv_7_emp"))
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["campaign"] is None


def test_hr_role_cannot_call_employee_interview_endpoints(client, mock_clerk_user):
    headers = register_hr(client, mock_clerk_user, "clerk_iv_8_hr", "Borealis Co", "hr@borealis.com")
    response = client.get("/api/v1/employee/interview", headers=headers)
    assert response.status_code == 403
