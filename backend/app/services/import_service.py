"""
Employee import orchestration.

    validate_and_stage_import()  ->  POST /hr/employees/import
    confirm_import()             ->  POST /hr/employees/imports/{id}/confirm
    get_import_or_404()          ->  GET  /hr/employees/imports/{id}
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ConflictError, FileTooLargeError, NotFoundError, UnsupportedFileTypeError
from app.models.employee import Employee, EmployeeStatus
from app.models.employee_import import EmployeeImport, EmployeeImportError, ImportStatus
from app.repositories import employee_import_repository as import_repo
from app.repositories import employee_repository as employee_repo
from app.schemas.employee_import import ImportErrorItem
from app.services import cloudinary_service
from app.services import audit_service
from app.services.audit_service import AuditAction
from app.services.import_parsers import parse_employee_file
from app.services.import_validation import validate_rows

logger = logging.getLogger(__name__)


def _validate_upload_constraints(filename: str, size_bytes: int) -> str:
    extension = os.path.splitext(filename)[1].lower()
    if extension not in settings.allowed_import_extensions_list:
        raise UnsupportedFileTypeError(
            f"'{extension or 'unknown'}' files are not supported. "
            f"Allowed types: {', '.join(settings.allowed_import_extensions_list)}."
        )

    max_bytes = settings.MAX_IMPORT_FILE_SIZE_MB * 1024 * 1024
    if size_bytes > max_bytes:
        raise FileTooLargeError(
            f"File exceeds the {settings.MAX_IMPORT_FILE_SIZE_MB}MB limit."
        )
    return extension


def validate_and_stage_import(
    db: Session,
    company_id: uuid.UUID,
    uploaded_by_user_id: uuid.UUID,
    filename: str,
    file_bytes: bytes,
) -> EmployeeImport:
    extension = _validate_upload_constraints(filename, len(file_bytes))

    # Parsing errors (corrupt file, missing required columns, empty file)
    # propagate as ImportValidationFailedError — no import record is
    # created for a file we couldn't even read.
    raw_rows = parse_employee_file(file_bytes, extension)

    valid_rows, errors = validate_rows(db, company_id, raw_rows)

    status_value = ImportStatus.VALIDATED if raw_rows else ImportStatus.FAILED

    employee_import = EmployeeImport(
        id=uuid.uuid4(),
        company_id=company_id,
        uploaded_by=uploaded_by_user_id,
        file_name=filename,
        file_extension=extension,
        status=status_value,
        total_rows=len(raw_rows),
        valid_rows=len(valid_rows),
        invalid_rows=len(raw_rows) - len(valid_rows),
        parsed_valid_rows=valid_rows,
    )

    error_rows = [
        EmployeeImportError(id=uuid.uuid4(), row_number=e.row, field=e.field, message=e.message)
        for e in errors
    ]

    import_repo.create(db, employee_import, error_rows)

    # Best-effort archival of the original file. Never let a Cloudinary
    # hiccup fail the import itself — the validation result already exists.
    try:
        public_id = cloudinary_service.upload_file(
            file_bytes,
            folder=f"employee-imports/{company_id}",
            public_id=str(employee_import.id),
        )
        if public_id:
            employee_import.cloudinary_public_id = public_id
            db.add(employee_import)
            db.flush()
    except Exception:  # pragma: no cover - defensive, network/service dependent
        logger.exception("Failed to archive import file %s to Cloudinary", employee_import.id)

    return employee_import


def get_import_or_404(db: Session, company_id: uuid.UUID, import_id: uuid.UUID) -> EmployeeImport:
    employee_import = import_repo.get_by_id(db, company_id, import_id)
    if employee_import is None:
        raise NotFoundError("Import not found.")
    return employee_import


def confirm_import(
    db: Session, company_id: uuid.UUID, import_id: uuid.UUID, actor_user_id: uuid.UUID | None = None
) -> tuple[int, int, list[ImportErrorItem]]:
    """
    Creates Employee rows from the staged `parsed_valid_rows`.

    Rows are re-checked against the CURRENT `employees` table (not just
    the state at validation time), since another import or manual creation
    could have landed a conflicting employee_id/email in between. Any such
    row is skipped (not the whole confirm) and reported back.
    """
    employee_import = get_import_or_404(db, company_id, import_id)

    if employee_import.status == ImportStatus.CONFIRMED:
        raise ConflictError("This import has already been confirmed.")
    if employee_import.status != ImportStatus.VALIDATED:
        raise ConflictError("Only a validated import can be confirmed.")

    created_count = 0
    skip_errors: list[ImportErrorItem] = []

    for index, row in enumerate(employee_import.parsed_valid_rows, start=1):
        if employee_repo.get_by_employee_code(db, company_id, row["employee_id"]) is not None:
            skip_errors.append(
                ImportErrorItem(
                    row=index, field="employee_id", message="Skipped: employee ID was created since validation."
                )
            )
            continue
        if employee_repo.get_by_email(db, company_id, row["email"]) is not None:
            skip_errors.append(
                ImportErrorItem(
                    row=index, field="email", message="Skipped: email was used since validation."
                )
            )
            continue

        last_working_date_value = None
        if row["last_working_date"]:
            last_working_date_value = date.fromisoformat(row["last_working_date"])

        employee = Employee(
            id=uuid.uuid4(),
            company_id=company_id,
            name=row["name"],
            email=row["email"],
            employee_id=row["employee_id"],
            department=row["department"],
            designation=row["designation"],
            last_working_date=last_working_date_value,
            status=EmployeeStatus.ACTIVE,
        )
        db.add(employee)
        created_count += 1

    employee_import.status = ImportStatus.CONFIRMED
    employee_import.confirmed_at = datetime.now(timezone.utc)
    db.add(employee_import)
    db.flush()

    audit_service.log(
        db,
        company_id=company_id,
        user_id=actor_user_id,
        action=AuditAction.EMPLOYEE_IMPORT_CONFIRMED,
        resource_type="employee_import",
        resource_id=import_id,
        extra_data={"created_count": created_count, "skipped_count": len(skip_errors)},
    )

    return created_count, len(skip_errors), skip_errors
