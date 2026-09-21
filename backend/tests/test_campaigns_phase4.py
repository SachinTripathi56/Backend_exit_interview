from datetime import datetime, timedelta, timezone

from tests.conftest import create_employee, register_hr


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def test_create_campaign_with_valid_schedule_and_employees(client, mock_clerk_user):
    headers = register_hr(client, mock_clerk_user, "clerk_camp_1", "Alpha Inc", "hr@alpha.com")
    emp = create_employee(client, headers, employee_id="A1", email="a1@alpha.com")

    now = datetime.now(timezone.utc)
    payload = {
        "name": "Q3 Exit Interviews",
        "description": "Standard exit interview campaign",
        "instructions": "Please answer honestly.",
        "start_at": _iso(now + timedelta(hours=1)),
        "end_at": _iso(now + timedelta(days=7)),
        "employee_ids": [emp["id"]],
    }
    response = client.post("/api/v1/hr/campaigns", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "SCHEDULED"
    assert body["employee_count"] == 1


def test_create_campaign_with_invalid_schedule_rejected(client, mock_clerk_user):
    headers = register_hr(client, mock_clerk_user, "clerk_camp_2", "Beta Inc", "hr@beta.com")
    now = datetime.now(timezone.utc)
    payload = {
        "name": "Bad Campaign",
        "start_at": _iso(now + timedelta(days=7)),
        "end_at": _iso(now + timedelta(hours=1)),  # end before start
        "employee_ids": [],
    }
    response = client.post("/api/v1/hr/campaigns", json=payload, headers=headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "CAMPAIGN_INVALID_SCHEDULE"


def test_create_campaign_with_no_employees_is_draft(client, mock_clerk_user):
    headers = register_hr(client, mock_clerk_user, "clerk_camp_3", "Gamma Inc", "hr@gamma.com")
    now = datetime.now(timezone.utc)
    payload = {
        "name": "Draft Campaign",
        "start_at": _iso(now + timedelta(hours=1)),
        "end_at": _iso(now + timedelta(days=7)),
        "employee_ids": [],
    }
    response = client.post("/api/v1/hr/campaigns", json=payload, headers=headers)
    assert response.status_code == 201
    assert response.json()["status"] == "DRAFT"


def test_create_campaign_with_employee_from_another_company_rejected(client, mock_clerk_user):
    headers_a = register_hr(client, mock_clerk_user, "clerk_camp_4a", "Delta Inc", "hr@delta.com")
    headers_b = register_hr(client, mock_clerk_user, "clerk_camp_4b", "Epsilon Inc", "hr@epsilon.com")
    emp_b = create_employee(client, headers_b, employee_id="B1", email="b1@epsilon.com")

    now = datetime.now(timezone.utc)
    payload = {
        "name": "Cross-tenant attempt",
        "start_at": _iso(now + timedelta(hours=1)),
        "end_at": _iso(now + timedelta(days=7)),
        "employee_ids": [emp_b["id"]],
    }
    response = client.post("/api/v1/hr/campaigns", json=payload, headers=headers_a)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_campaign_becomes_active_within_window_and_expired_after(client, mock_clerk_user):
    headers = register_hr(client, mock_clerk_user, "clerk_camp_5", "Zeta Inc", "hr@zeta.com")
    emp = create_employee(client, headers, employee_id="Z1", email="z1@zeta.com")

    now = datetime.now(timezone.utc)
    payload = {
        "name": "Active Now",
        "start_at": _iso(now - timedelta(minutes=1)),
        "end_at": _iso(now + timedelta(hours=1)),
        "employee_ids": [emp["id"]],
    }
    created = client.post("/api/v1/hr/campaigns", json=payload, headers=headers).json()
    fetched = client.get(f"/api/v1/hr/campaigns/{created['id']}", headers=headers)
    assert fetched.json()["status"] == "ACTIVE"

    # Now create one already in the past with an incomplete employee -> EXPIRED.
    past_payload = {
        "name": "Already Over",
        "start_at": _iso(now - timedelta(days=2)),
        "end_at": _iso(now - timedelta(days=1)),
        "employee_ids": [emp["id"]],
    }
    created_past = client.post("/api/v1/hr/campaigns", json=past_payload, headers=headers).json()
    fetched_past = client.get(f"/api/v1/hr/campaigns/{created_past['id']}", headers=headers)
    assert fetched_past.json()["status"] == "EXPIRED"


def test_update_campaign_reschedule_and_cancel(client, mock_clerk_user):
    headers = register_hr(client, mock_clerk_user, "clerk_camp_6", "Eta Inc", "hr@eta.com")
    now = datetime.now(timezone.utc)
    created = client.post(
        "/api/v1/hr/campaigns",
        json={
            "name": "Original",
            "start_at": _iso(now + timedelta(days=1)),
            "end_at": _iso(now + timedelta(days=8)),
            "employee_ids": [],
        },
        headers=headers,
    ).json()

    renamed = client.put(
        f"/api/v1/hr/campaigns/{created['id']}", json={"name": "Renamed Campaign"}, headers=headers
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Renamed Campaign"

    cancelled = client.put(
        f"/api/v1/hr/campaigns/{created['id']}", json={"status": "CANCELLED"}, headers=headers
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"

    # Cannot modify a cancelled campaign further.
    blocked = client.put(f"/api/v1/hr/campaigns/{created['id']}", json={"name": "Nope"}, headers=headers)
    assert blocked.status_code == 409


def test_delete_draft_campaign_hard_deletes_scheduled_cancels(client, mock_clerk_user):
    headers = register_hr(client, mock_clerk_user, "clerk_camp_7", "Theta Inc", "hr@theta.com")
    now = datetime.now(timezone.utc)

    draft = client.post(
        "/api/v1/hr/campaigns",
        json={"name": "Draft", "start_at": _iso(now + timedelta(days=1)), "end_at": _iso(now + timedelta(days=8)), "employee_ids": []},
        headers=headers,
    ).json()
    deleted = client.delete(f"/api/v1/hr/campaigns/{draft['id']}", headers=headers)
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/hr/campaigns/{draft['id']}", headers=headers).status_code == 404

    emp = create_employee(client, headers, employee_id="T1", email="t1@theta.com")
    scheduled = client.post(
        "/api/v1/hr/campaigns",
        json={
            "name": "Scheduled",
            "start_at": _iso(now + timedelta(days=1)),
            "end_at": _iso(now + timedelta(days=8)),
            "employee_ids": [emp["id"]],
        },
        headers=headers,
    ).json()
    deleted_scheduled = client.delete(f"/api/v1/hr/campaigns/{scheduled['id']}", headers=headers)
    assert deleted_scheduled.status_code == 204
    still_there = client.get(f"/api/v1/hr/campaigns/{scheduled['id']}", headers=headers)
    assert still_there.status_code == 200
    assert still_there.json()["status"] == "CANCELLED"


def test_company_a_cannot_access_company_b_campaign(client, mock_clerk_user):
    headers_a = register_hr(client, mock_clerk_user, "clerk_camp_8a", "Iota Inc", "hr@iota.com")
    now = datetime.now(timezone.utc)
    created_a = client.post(
        "/api/v1/hr/campaigns",
        json={"name": "A's campaign", "start_at": _iso(now + timedelta(days=1)), "end_at": _iso(now + timedelta(days=8)), "employee_ids": []},
        headers=headers_a,
    ).json()

    headers_b = register_hr(client, mock_clerk_user, "clerk_camp_8b", "Kappa Inc", "hr@kappa.com")
    response = client.get(f"/api/v1/hr/campaigns/{created_a['id']}", headers=headers_b)
    assert response.status_code == 404


def test_list_campaigns_filter_by_status(client, mock_clerk_user):
    headers = register_hr(client, mock_clerk_user, "clerk_camp_9", "Lambda Inc", "hr@lambda.com")
    now = datetime.now(timezone.utc)
    client.post(
        "/api/v1/hr/campaigns",
        json={"name": "Draft One", "start_at": _iso(now + timedelta(days=1)), "end_at": _iso(now + timedelta(days=8)), "employee_ids": []},
        headers=headers,
    )
    emp = create_employee(client, headers, employee_id="L1", email="l1@lambda.com")
    client.post(
        "/api/v1/hr/campaigns",
        json={"name": "Scheduled One", "start_at": _iso(now + timedelta(days=1)), "end_at": _iso(now + timedelta(days=8)), "employee_ids": [emp["id"]]},
        headers=headers,
    )

    drafts = client.get("/api/v1/hr/campaigns?status=DRAFT", headers=headers)
    assert drafts.json()["total"] == 1
    scheduled = client.get("/api/v1/hr/campaigns?status=SCHEDULED", headers=headers)
    assert scheduled.json()["total"] == 1
