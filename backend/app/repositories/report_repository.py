"""Data-access layer for reports."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.report import Report


def get_by_id(db: Session, company_id: uuid.UUID, report_id: uuid.UUID) -> Report | None:
    stmt = select(Report).where(Report.company_id == company_id, Report.id == report_id)
    return db.execute(stmt).scalar_one_or_none()


def list_paginated(db: Session, company_id: uuid.UUID, *, page: int, limit: int) -> tuple[list[Report], int]:
    stmt = select(Report).where(Report.company_id == company_id)
    count_stmt = select(func.count()).select_from(Report).where(Report.company_id == company_id)

    total = db.execute(count_stmt).scalar_one()
    stmt = stmt.order_by(Report.created_at.desc()).offset((page - 1) * limit).limit(limit)
    items = list(db.execute(stmt).scalars().all())
    return items, total
