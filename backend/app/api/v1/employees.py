"""
Employee management endpoints.

Every endpoint depends on `require_hr`, and every service/repository call
is scoped by `tenant.company_id` — resolved server-side from the
authenticated user, never accepted from the client. This is what prevents
a user from Company A ever reading or mutating Company B's employees, even
if they guess/enumerate a valid employee UUID.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import TenantContext, get_tenant_context, require_hr
from app.db.database import get_db
from app.models.employee import EmployeeStatus
from app.schemas.common import PaginatedResponse
from app.schemas.employee import EmployeeCreateRequest, EmployeeResponse, EmployeeUpdateRequest
from app.services import employee_service

router = APIRouter(prefix="/hr/employees", tags=["employees"], dependencies=[Depends(require_hr)])


@router.get(
    "",
    response_model=PaginatedResponse[EmployeeResponse],
    summary="List employees for the authenticated user's company",
)
def list_employees(
    search: str | None = Query(default=None, description="Matches name, email, or employee ID."),
    department: str | None = Query(default=None),
    status_filter: EmployeeStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
) -> PaginatedResponse[EmployeeResponse]:
    items, total = employee_service.list_employees(
        db,
        tenant.company_id,
        search=search,
        department=department,
        status=status_filter,
        page=page,
        limit=limit,
    )
    return PaginatedResponse(
        items=[EmployeeResponse.model_validate(e) for e in items], page=page, limit=limit, total=total
    )


@router.post(
    "",
    response_model=EmployeeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a single employee",
)
def create_employee(
    payload: EmployeeCreateRequest,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
) -> EmployeeResponse:
    employee = employee_service.create_employee(db, tenant.company_id, payload, tenant.user.id)
    return EmployeeResponse.model_validate(employee)


@router.get(
    "/{employee_pk}",
    response_model=EmployeeResponse,
    summary="Get a single employee by system ID",
)
def get_employee(
    employee_pk: uuid.UUID,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
) -> EmployeeResponse:
    employee = employee_service.get_employee_or_404(db, tenant.company_id, employee_pk)
    return EmployeeResponse.model_validate(employee)


@router.put(
    "/{employee_pk}",
    response_model=EmployeeResponse,
    summary="Update an employee",
)
def update_employee(
    employee_pk: uuid.UUID,
    payload: EmployeeUpdateRequest,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
) -> EmployeeResponse:
    employee = employee_service.update_employee(db, tenant.company_id, employee_pk, payload, tenant.user.id)
    return EmployeeResponse.model_validate(employee)


@router.delete(
    "/{employee_pk}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an employee",
)
def delete_employee(
    employee_pk: uuid.UUID,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
) -> None:
    employee_service.delete_employee(db, tenant.company_id, employee_pk, tenant.user.id)
