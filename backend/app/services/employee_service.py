"""
Employee business logic.

Every function here takes a `company_id` (resolved server-side from the
authenticated user — never trust one from the request body) and delegates
data access to `app.repositories.employee_repository`, which enforces the
company_id filter at the query level.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models.employee import Employee, EmployeeStatus
from app.repositories import employee_repository as repo
from app.schemas.employee import EmployeeCreateRequest, EmployeeUpdateRequest
from app.services import audit_service
from app.services.audit_service import AuditAction


def create_employee(
    db: Session, company_id: uuid.UUID, payload: EmployeeCreateRequest, actor_user_id: uuid.UUID | None = None
) -> Employee:
    if repo.get_by_employee_code(db, company_id, payload.employee_id) is not None:
        raise ConflictError(f"An employee with employee ID '{payload.employee_id}' already exists.")
    if repo.get_by_email(db, company_id, payload.email) is not None:
        raise ConflictError(f"An employee with email '{payload.email}' already exists.")

    employee = Employee(
        id=uuid.uuid4(),
        company_id=company_id,
        name=payload.name,
        email=payload.email,
        employee_id=payload.employee_id,
        department=payload.department,
        designation=payload.designation,
        last_working_date=payload.last_working_date,
        status=payload.status,
    )
    db.add(employee)
    db.flush()

    audit_service.log(
        db,
        company_id=company_id,
        user_id=actor_user_id,
        action=AuditAction.EMPLOYEE_CREATED,
        resource_type="employee",
        resource_id=employee.id,
        extra_data={"employee_code": employee.employee_id},
    )
    return employee


def get_employee_or_404(db: Session, company_id: uuid.UUID, employee_pk: uuid.UUID) -> Employee:
    employee = repo.get_by_id(db, company_id, employee_pk)
    if employee is None:
        # Deliberately 404 rather than 403 here: acknowledging that an
        # employee ID exists (just "not yours") would leak cross-tenant
        # information. From the caller's perspective a resource in another
        # company simply does not exist.
        raise NotFoundError("Employee not found.")
    return employee


def list_employees(
    db: Session,
    company_id: uuid.UUID,
    *,
    search: str | None,
    department: str | None,
    status: EmployeeStatus | None,
    page: int,
    limit: int,
) -> tuple[list[Employee], int]:
    return repo.list_paginated(
        db, company_id, search=search, department=department, status=status, page=page, limit=limit
    )


def update_employee(
    db: Session,
    company_id: uuid.UUID,
    employee_pk: uuid.UUID,
    payload: EmployeeUpdateRequest,
    actor_user_id: uuid.UUID | None = None,
) -> Employee:
    employee = get_employee_or_404(db, company_id, employee_pk)

    if payload.employee_id and payload.employee_id != employee.employee_id:
        existing = repo.get_by_employee_code(db, company_id, payload.employee_id)
        if existing is not None and existing.id != employee.id:
            raise ConflictError(f"An employee with employee ID '{payload.employee_id}' already exists.")

    if payload.email and payload.email != employee.email:
        existing = repo.get_by_email(db, company_id, payload.email)
        if existing is not None and existing.id != employee.id:
            raise ConflictError(f"An employee with email '{payload.email}' already exists.")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(employee, field, value)

    db.add(employee)
    db.flush()

    audit_service.log(
        db,
        company_id=company_id,
        user_id=actor_user_id,
        action=AuditAction.EMPLOYEE_UPDATED,
        resource_type="employee",
        resource_id=employee.id,
        extra_data={"updated_fields": list(update_data.keys())},
    )
    return employee


def delete_employee(
    db: Session, company_id: uuid.UUID, employee_pk: uuid.UUID, actor_user_id: uuid.UUID | None = None
) -> None:
    employee = get_employee_or_404(db, company_id, employee_pk)
    employee_code = employee.employee_id
    db.delete(employee)
    db.flush()

    audit_service.log(
        db,
        company_id=company_id,
        user_id=actor_user_id,
        action=AuditAction.EMPLOYEE_DELETED,
        resource_type="employee",
        resource_id=employee_pk,
        extra_data={"employee_code": employee_code},
    )
