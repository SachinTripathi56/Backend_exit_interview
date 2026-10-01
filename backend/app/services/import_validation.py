"""
Row-level validation for employee import.

Runs after `import_parsers` has turned the file into raw string rows.
Each row is checked independently, but duplicate detection is necessarily
stateful across the whole file (and against the existing `employees`
table for the company).
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.repositories import employee_repository as repo
from app.schemas.employee_import import ImportErrorItem

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d")


def _parse_date(value: str) -> date | None:
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def validate_rows(
    db: Session, company_id: uuid.UUID, raw_rows: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[ImportErrorItem]]:
    """
    Returns (valid_rows, errors). `valid_rows` are plain dicts ready to be
    staged on the EmployeeImport record — NOT yet Employee ORM objects and
    NOT yet committed anywhere.
    """
    errors: list[ImportErrorItem] = []
    valid_rows: list[dict[str, Any]] = []

    seen_employee_ids: dict[str, int] = {}  # lowercased value -> first row number seen
    seen_emails: dict[str, int] = {}

    for index, raw_row in enumerate(raw_rows, start=1):
        row_errors: list[ImportErrorItem] = []

        name = (raw_row.get("name") or "").strip()
        email = (raw_row.get("email") or "").strip()
        employee_id = (raw_row.get("employee_id") or "").strip()
        department = (raw_row.get("department") or "").strip() or None
        designation = (raw_row.get("designation") or "").strip() or None
        last_working_date_raw = (raw_row.get("last_working_date") or "").strip() or None

        if not name:
            row_errors.append(ImportErrorItem(row=index, field="name", message="Name is required."))
        if not employee_id:
            row_errors.append(
                ImportErrorItem(row=index, field="employee_id", message="Employee ID is required.")
            )
        if not email:
            row_errors.append(ImportErrorItem(row=index, field="email", message="Email is required."))
        elif not _EMAIL_RE.match(email):
            row_errors.append(ImportErrorItem(row=index, field="email", message="Invalid email format."))

        parsed_last_working_date: date | None = None
        if last_working_date_raw:
            parsed_last_working_date = _parse_date(last_working_date_raw)
            if parsed_last_working_date is None:
                row_errors.append(
                    ImportErrorItem(
                        row=index,
                        field="last_working_date",
                        message="Invalid date format. Use YYYY-MM-DD.",
                    )
                )

        # Duplicate-within-file detection (case-insensitive). Only checked
        # when the field itself is present and otherwise well-formed.
        if employee_id:
            key = employee_id.lower()
            if key in seen_employee_ids:
                row_errors.append(
                    ImportErrorItem(
                        row=index,
                        field="employee_id",
                        message=f"Duplicate employee ID in file (first seen at row {seen_employee_ids[key]}).",
                    )
                )
            else:
                seen_employee_ids[key] = index

        if email:
            key = email.lower()
            if key in seen_emails:
                row_errors.append(
                    ImportErrorItem(
                        row=index,
                        field="email",
                        message=f"Duplicate email in file (first seen at row {seen_emails[key]}).",
                    )
                )
            else:
                seen_emails[key] = index

        # Duplicate-against-existing-employees detection.
        if employee_id and repo.get_by_employee_code(db, company_id, employee_id) is not None:
            row_errors.append(
                ImportErrorItem(
                    row=index, field="employee_id", message="An employee with this ID already exists."
                )
            )
        if email and _EMAIL_RE.match(email) and repo.get_by_email(db, company_id, email) is not None:
            row_errors.append(
                ImportErrorItem(row=index, field="email", message="An employee with this email already exists.")
            )

        if row_errors:
            errors.extend(row_errors)
            continue

        valid_rows.append(
            {
                "name": name,
                "email": email,
                "employee_id": employee_id,
                "department": department,
                "designation": designation,
                "last_working_date": parsed_last_working_date.isoformat() if parsed_last_working_date else None,
            }
        )

    return valid_rows, errors
