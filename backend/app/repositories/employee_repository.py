"""
Data-access layer for employees.

Every method here takes `company_id` as a required argument and applies it
as a WHERE filter. This is the enforcement point for tenant isolation:
services must never query the `Employee` model directly, and no method here
accepts an unscoped query. This makes an IDOR bug (accidentally returning
another tenant's row) require someone to actively remove the filter, rather
than simply forget to add one.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.employee import Employee, EmployeeStatus


def get_by_id(db: Session, company_id: uuid.UUID, employee_id: uuid.UUID) -> Employee | None:
    stmt = select(Employee).where(Employee.company_id == company_id, Employee.id == employee_id)
    return db.execute(stmt).scalar_one_or_none()


def get_by_employee_code(db: Session, company_id: uuid.UUID, employee_code: str) -> Employee | None:
    stmt = select(Employee).where(
        Employee.company_id == company_id, Employee.employee_id == employee_code
    )
    return db.execute(stmt).scalar_one_or_none()


def get_by_email(db: Session, company_id: uuid.UUID, email: str) -> Employee | None:
    stmt = select(Employee).where(Employee.company_id == company_id, Employee.email == email)
    return db.execute(stmt).scalar_one_or_none()


def list_paginated(
    db: Session,
    company_id: uuid.UUID,
    *,
    search: str | None,
    department: str | None,
    status: EmployeeStatus | None,
    page: int,
    limit: int,
) -> tuple[list[Employee], int]:
    stmt = select(Employee).where(Employee.company_id == company_id)
    count_stmt = select(func.count()).select_from(Employee).where(Employee.company_id == company_id)

    if search:
        pattern = f"%{search.lower()}%"
        search_filter = func.lower(Employee.name).like(pattern) | func.lower(Employee.email).like(
            pattern
        ) | func.lower(Employee.employee_id).like(pattern)
        stmt = stmt.where(search_filter)
        count_stmt = count_stmt.where(search_filter)

    if department:
        stmt = stmt.where(Employee.department == department)
        count_stmt = count_stmt.where(Employee.department == department)

    if status:
        stmt = stmt.where(Employee.status == status)
        count_stmt = count_stmt.where(Employee.status == status)

    total = db.execute(count_stmt).scalar_one()

    stmt = stmt.order_by(Employee.created_at.desc()).offset((page - 1) * limit).limit(limit)
    items = list(db.execute(stmt).scalars().all())

    return items, total


def count_by_company(db: Session, company_id: uuid.UUID) -> int:
    stmt = select(func.count()).select_from(Employee).where(Employee.company_id == company_id)
    return db.execute(stmt).scalar_one()


def count_by_status(db: Session, company_id: uuid.UUID, statuses: list[EmployeeStatus]) -> int:
    stmt = (
        select(func.count())
        .select_from(Employee)
        .where(Employee.company_id == company_id, Employee.status.in_(statuses))
    )
    return db.execute(stmt).scalar_one()
