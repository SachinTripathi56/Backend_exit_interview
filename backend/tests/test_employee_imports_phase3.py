import io

from tests.conftest import register_hr

CSV_HEADER = "Name,Email,Employee ID,Department,Designation,Last Working Date\n"


def _csv_file(rows: str, filename: str = "employees.csv"):
    content = (CSV_HEADER + rows).encode("utf-8")
    return {"file": (filename, io.BytesIO(content), "text/csv")}


def test_upload_valid_csv_stages_rows_without_creating_employees(client, mock_clerk_user):
    headers = register_hr(client, mock_clerk_user, "clerk_imp_1", "Nova Inc", "hr@nova.com")

    rows = (
        "Alice Example,alice@nova.com,EMP001,Engineering,SWE,2026-09-30\n"
        "Bob Test,bob@nova.com,EMP002,Sales,Rep,2026-10-15\n"
    )
    response = client.post("/api/v1/hr/employees/import", files=_csv_file(rows), headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total_rows"] == 2
    assert body["valid_rows"] == 2
    assert body["invalid_rows"] == 0
    assert body["errors"] == []

    # Nothing was created yet.
    listing = client.get("/api/v1/hr/employees", headers=headers)
    assert listing.json()["total"] == 0


def test_upload_csv_with_bad_rows_reports_errors_and_still_stages_good_rows(client, mock_clerk_user):
    headers = register_hr(client, mock_clerk_user, "clerk_imp_2", "Orbit LLC", "hr@orbit.com")

    rows = (
        "Alice Example,alice@orbit.com,EMP001,Engineering,SWE,2026-09-30\n"
        ",bademail,EMP001,Engineering,,\n"  # missing name, bad email, duplicate employee_id
        "Carl Good,carl@orbit.com,EMP003,Sales,Rep,not-a-date\n"
    )
    response = client.post("/api/v1/hr/employees/import", files=_csv_file(rows), headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total_rows"] == 3
    assert body["valid_rows"] == 1
    assert body["invalid_rows"] == 2
    fields_with_errors = {e["field"] for e in body["errors"]}
    assert "name" in fields_with_errors
    assert "email" in fields_with_errors
    assert "last_working_date" in fields_with_errors


def test_confirm_import_creates_only_valid_rows(client, mock_clerk_user):
    headers = register_hr(client, mock_clerk_user, "clerk_imp_3", "Pulse Co", "hr@pulse.com")

    rows = (
        "Dana Lee,dana@pulse.com,EMP010,Engineering,SWE,2026-09-30\n"
        "Evan Ray,evan@pulse.com,EMP011,Sales,Rep,2026-10-01\n"
    )
    upload = client.post("/api/v1/hr/employees/import", files=_csv_file(rows), headers=headers)
    import_id = upload.json()["import_id"]

    confirm = client.post(f"/api/v1/hr/employees/imports/{import_id}/confirm", headers=headers)
    assert confirm.status_code == 200
    body = confirm.json()
    assert body["created_count"] == 2
    assert body["skipped_count"] == 0

    listing = client.get("/api/v1/hr/employees", headers=headers)
    assert listing.json()["total"] == 2


def test_confirm_import_twice_conflicts(client, mock_clerk_user):
    headers = register_hr(client, mock_clerk_user, "clerk_imp_4", "Quartz Inc", "hr@quartz.com")

    rows = "Fay Lin,fay@quartz.com,EMP020,Engineering,SWE,2026-09-30\n"
    upload = client.post("/api/v1/hr/employees/import", files=_csv_file(rows), headers=headers)
    import_id = upload.json()["import_id"]

    first = client.post(f"/api/v1/hr/employees/imports/{import_id}/confirm", headers=headers)
    assert first.status_code == 200

    second = client.post(f"/api/v1/hr/employees/imports/{import_id}/confirm", headers=headers)
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "CONFLICT"


def test_confirm_skips_rows_that_conflict_with_employees_created_after_validation(client, mock_clerk_user):
    headers = register_hr(client, mock_clerk_user, "clerk_imp_5", "Rune Corp", "hr@rune.com")

    rows = "Gina Park,gina@rune.com,EMP030,Engineering,SWE,2026-09-30\n"
    upload = client.post("/api/v1/hr/employees/import", files=_csv_file(rows), headers=headers)
    import_id = upload.json()["import_id"]

    # Someone else creates a conflicting employee AFTER validation but
    # BEFORE confirm — the row must be skipped, not silently overwritten,
    # and confirm must not fail outright for the whole batch.
    manual = client.post(
        "/api/v1/hr/employees",
        json={"name": "Manual Duplicate", "email": "gina@rune.com", "employee_id": "EMP099"},
        headers=headers,
    )
    assert manual.status_code == 201

    confirm = client.post(f"/api/v1/hr/employees/imports/{import_id}/confirm", headers=headers)
    assert confirm.status_code == 200
    body = confirm.json()
    assert body["created_count"] == 0
    assert body["skipped_count"] == 1
    assert body["errors"][0]["field"] == "email"


def test_get_import_returns_detail(client, mock_clerk_user):
    headers = register_hr(client, mock_clerk_user, "clerk_imp_6", "Solace Inc", "hr@solace.com")

    rows = "Henry Cole,henry@solace.com,EMP040,Engineering,SWE,2026-09-30\n"
    upload = client.post("/api/v1/hr/employees/import", files=_csv_file(rows), headers=headers)
    import_id = upload.json()["import_id"]

    detail = client.get(f"/api/v1/hr/employees/imports/{import_id}", headers=headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == "VALIDATED"
    assert body["valid_rows"] == 1


def test_unsupported_file_type_rejected(client, mock_clerk_user):
    headers = register_hr(client, mock_clerk_user, "clerk_imp_7", "Tundra LLC", "hr@tundra.com")

    files = {"file": ("employees.txt", io.BytesIO(b"not a real import file"), "text/plain")}
    response = client.post("/api/v1/hr/employees/import", files=files, headers=headers)
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_company_a_cannot_view_company_b_import(client, mock_clerk_user):
    headers_a = register_hr(client, mock_clerk_user, "clerk_imp_8a", "Umbra Co", "hr@umbra.com")
    rows = "Ivy Stone,ivy@umbra.com,EMP050,Engineering,SWE,2026-09-30\n"
    upload = client.post("/api/v1/hr/employees/import", files=_csv_file(rows), headers=headers_a)
    import_id = upload.json()["import_id"]

    headers_b = register_hr(client, mock_clerk_user, "clerk_imp_8b", "Vertex Co", "hr@vertex.com")
    response = client.get(f"/api/v1/hr/employees/imports/{import_id}", headers=headers_b)
    assert response.status_code == 404
