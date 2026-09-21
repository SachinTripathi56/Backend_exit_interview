"""
Employee bulk import endpoints.

Two-step flow per the spec ("Do NOT insert invalid records during the
validation stage"):

    1. POST   /hr/employees/import                    -> parse + validate, stage candidate rows
    2. GET    /hr/employees/imports/{import_id}        -> inspect a previous validation result
    3. POST   /hr/employees/imports/{import_id}/confirm -> actually create the employees
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies import TenantContext, get_current_user, get_tenant_context, require_hr
from app.db.database import get_db
from app.models.user import User
from app.schemas.employee_import import (
    ImportConfirmResponse,
    ImportDetailResponse,
    ImportErrorItem,
    ImportValidationResponse,
)
from app.services import import_service

router = APIRouter(prefix="/hr/employees", tags=["employee-import"], dependencies=[Depends(require_hr)])


@router.post(
    "/import",
    response_model=ImportValidationResponse,
    summary="Upload and validate an employee file (.xlsx, .xls, .csv, .pdf)",
    description=(
        "Parses and validates the file synchronously. No employee records are "
        "created at this step — call the /confirm endpoint with the returned "
        "import_id to actually create the valid rows."
    ),
)
async def upload_import(
    file: UploadFile,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
    current_user: User = Depends(get_current_user),
) -> ImportValidationResponse:
    file_bytes = await file.read()
    employee_import = import_service.validate_and_stage_import(
        db, tenant.company_id, current_user.id, file.filename or "upload", file_bytes
    )
    return ImportValidationResponse(
        import_id=employee_import.id,
        total_rows=employee_import.total_rows,
        valid_rows=employee_import.valid_rows,
        invalid_rows=employee_import.invalid_rows,
        errors=[
            ImportErrorItem(row=e.row_number, field=e.field, message=e.message)
            for e in employee_import.errors
        ],
    )


@router.get(
    "/imports/{import_id}",
    response_model=ImportDetailResponse,
    summary="Get the validation result of a previous import",
)
def get_import(
    import_id: uuid.UUID,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
) -> ImportDetailResponse:
    employee_import = import_service.get_import_or_404(db, tenant.company_id, import_id)
    return ImportDetailResponse(
        id=employee_import.id,
        file_name=employee_import.file_name,
        file_extension=employee_import.file_extension,
        status=employee_import.status,
        total_rows=employee_import.total_rows,
        valid_rows=employee_import.valid_rows,
        invalid_rows=employee_import.invalid_rows,
        created_at=employee_import.created_at,
        confirmed_at=employee_import.confirmed_at,
        errors=[
            ImportErrorItem(row=e.row_number, field=e.field, message=e.message)
            for e in employee_import.errors
        ],
    )


@router.post(
    "/imports/{import_id}/confirm",
    response_model=ImportConfirmResponse,
    status_code=status.HTTP_200_OK,
    summary="Confirm a validated import, creating the employee records",
)
def confirm_import(
    import_id: uuid.UUID,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
) -> ImportConfirmResponse:
    created_count, skipped_count, errors = import_service.confirm_import(
        db, tenant.company_id, import_id, tenant.user.id
    )
    return ImportConfirmResponse(
        import_id=import_id, created_count=created_count, skipped_count=skipped_count, errors=errors
    )
