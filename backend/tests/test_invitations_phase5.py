from datetime import datetime, timedelta, timezone

from tests.conftest import auth_header, create_employee, register_hr


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _create_active_campaign(client, headers, employee_ids):
    now = datetime.now(timezone.utc)
    payload = {
        "name": "Invitation Test Campaign",
        "start_at": _iso(now - timedelta(minutes=1)),
        "end_at": _iso(now + timedelta(days=7)),
        "employee_ids": employee_ids,
    }
    return client.post("/api/v1/hr/campaigns", json=payload, headers=headers).json()


def test_send_invitations_updates_status_and_logs_email(client, mock_clerk_user):
    headers = register_hr(client, mock_clerk_user, "clerk_inv_1", "Nova Inc", "hr@nova.com")
    emp = create_employee(client, headers, employee_id="N1", email="n1@nova.com")
    campaign = _create_active_campaign(client, headers, [emp["id"]])

    response = client.post(f"/api/v1/hr/campaigns/{campaign['id']}/invitations", json={}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["sent_count"] == 1
    assert body["failed_count"] == 0
    assert body["results"][0]["status"] == "SENT"

    detail = client.get(f"/api/v1/hr/campaigns/{campaign['id']}", headers=headers).json()
    assert detail["assignments"][0]["invitation_status"] == "SENT"
    assert detail["invited_count"] == 1

    employee_detail = client.get(f"/api/v1/hr/employees/{emp['id']}", headers=headers).json()
    assert employee_detail["status"] == "INVITED"


def test_invitations_skip_already_invited_by_default(client, mock_clerk_user):
    headers = register_hr(client, mock_clerk_user, "clerk_inv_2", "Orbit Inc", "hr@orbit.com")
    emp = create_employee(client, headers, employee_id="O1", email="o1@orbit.com")
    campaign = _create_active_campaign(client, headers, [emp["id"]])

    first = client.post(f"/api/v1/hr/campaigns/{campaign['id']}/invitations", json={}, headers=headers)
    assert first.json()["sent_count"] == 1

    second = client.post(f"/api/v1/hr/campaigns/{campaign['id']}/invitations", json={}, headers=headers)
    assert second.json()["sent_count"] == 0
    assert second.json()["skipped_count"] == 0  # nothing eligible -> empty target set, not "skipped"
    assert second.json()["results"] == []


def test_invitations_can_be_explicitly_resent(client, mock_clerk_user):
    headers = register_hr(client, mock_clerk_user, "clerk_inv_3", "Pulse Inc", "hr@pulse.com")
    emp = create_employee(client, headers, employee_id="P1", email="p1@pulse.com")
    campaign = _create_active_campaign(client, headers, [emp["id"]])

    client.post(f"/api/v1/hr/campaigns/{campaign['id']}/invitations", json={}, headers=headers)
    resend = client.post(
        f"/api/v1/hr/campaigns/{campaign['id']}/invitations",
        json={"employee_ids": [emp["id"]]},
        headers=headers,
    )
    assert resend.json()["sent_count"] == 1


def test_reminders_only_go_to_eligible_employees(client, mock_clerk_user):
    headers = register_hr(client, mock_clerk_user, "clerk_inv_4", "Quartz Inc", "hr@quartz.com")
    emp1 = create_employee(client, headers, employee_id="Q1", email="q1@quartz.com")
    emp2 = create_employee(client, headers, employee_id="Q2", email="q2@quartz.com")
    campaign = _create_active_campaign(client, headers, [emp1["id"], emp2["id"]])

    # Reminder before any invitation was ever sent -> nobody eligible.
    before = client.post(f"/api/v1/hr/campaigns/{campaign['id']}/reminders", json={}, headers=headers)
    assert before.json()["sent_count"] == 0
    assert all(r["status"] == "SKIPPED" for r in before.json()["results"])

    client.post(f"/api/v1/hr/campaigns/{campaign['id']}/invitations", json={}, headers=headers)
    after = client.post(f"/api/v1/hr/campaigns/{campaign['id']}/reminders", json={}, headers=headers)
    assert after.json()["sent_count"] == 2


def test_invitations_rejected_for_expired_campaign(client, mock_clerk_user):
    headers = register_hr(client, mock_clerk_user, "clerk_inv_5", "Rune Inc", "hr@rune.com")
    emp = create_employee(client, headers, employee_id="R1", email="r1@rune.com")
    now = datetime.now(timezone.utc)
    campaign = client.post(
        "/api/v1/hr/campaigns",
        json={
            "name": "Already over",
            "start_at": _iso(now - timedelta(days=10)),
            "end_at": _iso(now - timedelta(days=1)),
            "employee_ids": [emp["id"]],
        },
        headers=headers,
    ).json()

    response = client.post(f"/api/v1/hr/campaigns/{campaign['id']}/invitations", json={}, headers=headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CAMPAIGN_EXPIRED"


def test_employee_access_token_redemption_creates_employee_user(client, mock_clerk_user, monkeypatch):
    headers = register_hr(client, mock_clerk_user, "clerk_inv_6", "Solace Inc", "hr@solace.com")
    emp = create_employee(client, headers, employee_id="S1", email="s1@solace.com")
    campaign = _create_active_campaign(client, headers, [emp["id"]])

    captured_urls = []

    def _capture_send_invitation(to_email, employee_name, campaign_name, access_url):
        from app.services.email_service import EmailSendResult

        captured_urls.append(access_url)
        return EmailSendResult(success=True, provider_response="captured")

    import app.services.invitation_service as invitation_service_module

    monkeypatch.setattr(invitation_service_module.email_service, "send_invitation", _capture_send_invitation)

    invite_resp = client.post(f"/api/v1/hr/campaigns/{campaign['id']}/invitations", json={}, headers=headers)
    assert invite_resp.json()["sent_count"] == 1
    assert len(captured_urls) == 1

    raw_token = captured_urls[0].split("token=")[1]

    mock_clerk_user("clerk_employee_s1")
    access_response = client.post(
        "/api/v1/auth/employee-access",
        json={"token": raw_token},
        headers=auth_header("token-clerk_employee_s1"),
    )
    assert access_response.status_code == 200
    body = access_response.json()
    assert body["role"] == "EMPLOYEE"
    assert body["email"] == "s1@solace.com"

    me = client.get("/api/v1/employee/me", headers=auth_header("token-clerk_employee_s1"))
    assert me.status_code == 200
    assert me.json()["employee_id"] == "S1"


def test_employee_access_token_cannot_be_reused(client, mock_clerk_user, monkeypatch):
    headers = register_hr(client, mock_clerk_user, "clerk_inv_7", "Tundra Inc", "hr@tundra.com")
    emp = create_employee(client, headers, employee_id="T1", email="t1@tundra.com")
    campaign = _create_active_campaign(client, headers, [emp["id"]])

    captured_urls = []

    def _capture_send_invitation(to_email, employee_name, campaign_name, access_url):
        from app.services.email_service import EmailSendResult

        captured_urls.append(access_url)
        return EmailSendResult(success=True, provider_response="captured")

    import app.services.invitation_service as invitation_service_module

    monkeypatch.setattr(invitation_service_module.email_service, "send_invitation", _capture_send_invitation)
    client.post(f"/api/v1/hr/campaigns/{campaign['id']}/invitations", json={}, headers=headers)
    raw_token = captured_urls[0].split("token=")[1]

    mock_clerk_user("clerk_employee_t1_a")
    first = client.post(
        "/api/v1/auth/employee-access", json={"token": raw_token}, headers=auth_header("token-a")
    )
    assert first.status_code == 200

    mock_clerk_user("clerk_employee_t1_b")
    second = client.post(
        "/api/v1/auth/employee-access", json={"token": raw_token}, headers=auth_header("token-b")
    )
    assert second.status_code == 404
