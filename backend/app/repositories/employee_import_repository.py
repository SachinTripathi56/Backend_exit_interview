"""Data-access layer for employee_imports / employee_import_errors."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.employee_import import EmployeeImport, EmployeeImportError


def get_by_id(db: Session, company_id: uuid.UUID, import_id: uuid.UUID) -> EmployeeImport | None:
    stmt = (
        select(EmployeeImport)
        .options(selectinload(EmployeeImport.errors))
        .where(EmployeeImport.company_id == company_id, EmployeeImport.id == import_id)
    )
    return db.execute(stmt).scalar_one_or_none()


def create(db: Session, employee_import: EmployeeImport, error_rows: list[EmployeeImportError]) -> EmployeeImport:
    db.add(employee_import)
    db.flush()  # populate employee_import.id
    for err in error_rows:
        err.import_id = employee_import.id
        db.add(err)
    db.flush()
    return employee_import
