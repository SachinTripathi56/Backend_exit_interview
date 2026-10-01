"""Data-access layer for campaigns and campaign_employees."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.campaign import Campaign, CampaignStatus
from app.models.campaign_employee import CampaignEmployee


def get_by_id(db: Session, company_id: uuid.UUID, campaign_id: uuid.UUID) -> Campaign | None:
    stmt = (
        select(Campaign)
        .options(selectinload(Campaign.assignments))
        .where(Campaign.company_id == company_id, Campaign.id == campaign_id)
    )
    return db.execute(stmt).scalar_one_or_none()


def list_paginated(
    db: Session,
    company_id: uuid.UUID,
    *,
    status: CampaignStatus | None,
    page: int,
    limit: int,
) -> tuple[list[Campaign], int]:
    stmt = select(Campaign).where(Campaign.company_id == company_id)
    count_stmt = select(func.count()).select_from(Campaign).where(Campaign.company_id == company_id)

    if status:
        stmt = stmt.where(Campaign.status == status)
        count_stmt = count_stmt.where(Campaign.status == status)

    total = db.execute(count_stmt).scalar_one()

    stmt = (
        stmt.options(selectinload(Campaign.assignments))
        .order_by(Campaign.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    items = list(db.execute(stmt).scalars().all())
    return items, total


def get_assignment(db: Session, campaign_id: uuid.UUID, employee_id: uuid.UUID) -> CampaignEmployee | None:
    stmt = select(CampaignEmployee).where(
        CampaignEmployee.campaign_id == campaign_id, CampaignEmployee.employee_id == employee_id
    )
    return db.execute(stmt).scalar_one_or_none()


def get_active_assignment_for_employee(db: Session, company_id: uuid.UUID, employee_id: uuid.UUID):
    """
    Returns the (CampaignEmployee, Campaign) pair most relevant to show the
    employee right now: prefer an ACTIVE campaign, then fall back to the
    most recently created assignment (e.g. a SCHEDULED one, so the employee
    portal can say "starts on <date>" rather than showing nothing).
    """
    stmt = (
        select(CampaignEmployee, Campaign)
        .join(Campaign, Campaign.id == CampaignEmployee.campaign_id)
        .where(Campaign.company_id == company_id, CampaignEmployee.employee_id == employee_id)
        .where(Campaign.status.notin_([CampaignStatus.CANCELLED, CampaignStatus.DRAFT]))
        .order_by(
            (Campaign.status == CampaignStatus.ACTIVE).desc(),
            Campaign.created_at.desc(),
        )
    )
    return db.execute(stmt).first()
