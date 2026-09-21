from tests.conftest import auth_header, create_employee_user, register_hr


def _create_employee(client, headers, **overrides):
    payload = {
        "name": "Alice Example",
        "email": "alice@example.com",
        "employee_id": "EMP001",
        "department": "Engineering",
        "designation": "Senior Engineer",
        "last_working_date": "2026-09-30",
    }
    payload.update(overrides)
    return client.post("/api/v1/hr/employees", json=payload, headers=headers)


def test_hr_can_create_and_get_employee(client, mock_clerk_user):
    headers = register_hr(client, mock_clerk_user, "clerk_hr_1", "Acme Corp", "hr1@acme.com")

    created = _create_employee(client, headers)
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "Alice Example"
    assert body["status"] == "ACTIVE"

    fetched = client.get(f"/api/v1/hr/employees/{body['id']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["email"] == "alice@example.com"


def test_duplicate_employee_code_in_same_company_conflicts(client, mock_clerk_user):
    headers = register_hr(client, mock_clerk_user, "clerk_hr_2", "Beta Inc", "hr2@beta.com")

    first = _create_employee(client, headers, employee_id="EMP100", email="a@beta.com")
    assert first.status_code == 201

    second = _create_employee(client, headers, employee_id="EMP100", email="b@beta.com")
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "CONFLICT"


def test_same_employee_code_allowed_across_different_companies(client, mock_clerk_user):
    headers_a = register_hr(client, mock_clerk_user, "clerk_hr_3a", "Gamma LLC", "hr@gamma.com")
    created_a = _create_employee(client, headers_a, employee_id="EMP001", email="a@gamma.com")
    assert created_a.status_code == 201

    headers_b = register_hr(client, mock_clerk_user, "clerk_hr_3b", "Delta LLC", "hr@delta.com")
    created_b = _create_employee(client, headers_b, employee_id="EMP001", email="a@delta.com")
    assert created_b.status_code == 201


def test_employee_update_and_delete(client, mock_clerk_user):
    headers = register_hr(client, mock_clerk_user, "clerk_hr_4", "Epsilon Co", "hr4@epsilon.com")
    created = _create_employee(client, headers, employee_id="EMP200", email="c@epsilon.com").json()

    updated = client.put(
        f"/api/v1/hr/employees/{created['id']}",
        json={"department": "Marketing", "status": "INTERVIEW_PENDING"},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["department"] == "Marketing"
    assert updated.json()["status"] == "INTERVIEW_PENDING"
    # Untouched fields survive the partial update.
    assert updated.json()["name"] == "Alice Example"

    deleted = client.delete(f"/api/v1/hr/employees/{created['id']}", headers=headers)
    assert deleted.status_code == 204

    gone = client.get(f"/api/v1/hr/employees/{created['id']}", headers=headers)
    assert gone.status_code == 404


def test_list_employees_search_filter_and_pagination(client, mock_clerk_user):
    headers = register_hr(client, mock_clerk_user, "clerk_hr_5", "Zeta Corp", "hr5@zeta.com")

    _create_employee(client, headers, employee_id="E1", email="e1@zeta.com", name="Priya Singh", department="Sales")
    _create_employee(client, headers, employee_id="E2", email="e2@zeta.com", name="Raj Kumar", department="Engineering")
    _create_employee(client, headers, employee_id="E3", email="e3@zeta.com", name="Priya Patel", department="Sales")

    all_items = client.get("/api/v1/hr/employees", headers=headers)
    assert all_items.status_code == 200
    assert all_items.json()["total"] == 3

    by_dept = client.get("/api/v1/hr/employees?department=Sales", headers=headers)
    assert by_dept.json()["total"] == 2

    by_search = client.get("/api/v1/hr/employees?search=priya", headers=headers)
    assert by_search.json()["total"] == 2

    paged = client.get("/api/v1/hr/employees?page=1&limit=2", headers=headers)
    assert len(paged.json()["items"]) == 2
    assert paged.json()["total"] == 3


def test_employee_role_cannot_access_hr_employee_endpoints(client, mock_clerk_user, db_session):
    headers = register_hr(client, mock_clerk_user, "clerk_hr_6", "Theta LLC", "hr6@theta.com")
    me = client.get("/api/v1/me", headers=headers).json()

    create_employee_user(db_session, me["company_id"], "clerk_employee_6", "worker@theta.com")
    db_session.flush()

    mock_clerk_user("clerk_employee_6")
    response = client.get("/api/v1/hr/employees", headers=auth_header("token-clerk_employee_6"))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_company_a_cannot_access_company_b_employee(client, mock_clerk_user):
    headers_a = register_hr(client, mock_clerk_user, "clerk_hr_7a", "Iota Co", "hr@iota.com")
    created_a = _create_employee(client, headers_a, employee_id="A1", email="a1@iota.com").json()

    headers_b = register_hr(client, mock_clerk_user, "clerk_hr_7b", "Kappa Co", "hr@kappa.com")

    # Company B's HR tries to read/update/delete Company A's employee by ID.
    get_resp = client.get(f"/api/v1/hr/employees/{created_a['id']}", headers=headers_b)
    assert get_resp.status_code == 404

    put_resp = client.put(
        f"/api/v1/hr/employees/{created_a['id']}", json={"department": "Hacked"}, headers=headers_b
    )
    assert put_resp.status_code == 404

    delete_resp = client.delete(f"/api/v1/hr/employees/{created_a['id']}", headers=headers_b)
    assert delete_resp.status_code == 404


def test_dashboard_reflects_employee_counts(client, mock_clerk_user):
    headers = register_hr(client, mock_clerk_user, "clerk_hr_8", "Lambda Inc", "hr8@lambda.com")

    _create_employee(client, headers, employee_id="D1", email="d1@lambda.com", status="INTERVIEW_COMPLETED")
    _create_employee(client, headers, employee_id="D2", email="d2@lambda.com", status="INTERVIEW_PENDING")
    _create_employee(client, headers, employee_id="D3", email="d3@lambda.com", status="ACTIVE")

    dashboard = client.get("/api/v1/hr/dashboard", headers=headers)
    assert dashboard.status_code == 200
    body = dashboard.json()
    assert body["total_employees"] == 3
    assert body["total_interviews"] == 2  # PENDING + COMPLETED count as "entered the interview flow"
    assert body["completed_interviews"] == 1
    assert body["pending_interviews"] == 1
    assert body["completion_rate"] == 50.0
