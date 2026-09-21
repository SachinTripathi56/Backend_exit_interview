"""
Data-access layer for analytics.

Every query here is scoped by company_id and returns only aggregates or
lists of `InterviewResult` rows for in-process aggregation — no query here
ever returns a single row joined back to an identifiable employee outside
this module (the caller, `analytics_service.py`, never re-exposes
`InterviewResult.employee_id`).

`campaign_id` is optional on every function: omitted means "company-wide"
(used by `GET /hr/analytics`), provided means "just this campaign" (used by
Phase 9's per-campaign reports). Same queries, same privacy guarantees,
just a narrower scope.
"""
from __future__ import annotations

import uuid

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.campaign_employee import CampaignEmployee, CampaignInterviewStatus
from app.models.employee import Employee
from app.models.interview_result import InterviewResult

_completed_flag = case((CampaignEmployee.interview_status == CampaignInterviewStatus.COMPLETED, 1), else_=0)


def get_assignment_counts_by_department(
    db: Session, company_id: uuid.UUID, campaign_id: uuid.UUID | None = None
) -> list[tuple[str, int, int]]:
    """Returns (department, assigned_count, completed_count) for every department with at least one assignment."""
    dept_label = func.coalesce(Employee.department, "Unspecified")
    stmt = (
        select(dept_label, func.count(CampaignEmployee.id), func.sum(_completed_flag))
        .select_from(CampaignEmployee)
        .join(Campaign, Campaign.id == CampaignEmployee.campaign_id)
        .join(Employee, Employee.id == CampaignEmployee.employee_id)
        .where(Campaign.company_id == company_id)
        .group_by(dept_label)
    )
    if campaign_id is not None:
        stmt = stmt.where(Campaign.id == campaign_id)
    rows = db.execute(stmt).all()
    return [(dept, int(assigned), int(completed or 0)) for dept, assigned, completed in rows]


def get_total_assignment_counts(
    db: Session, company_id: uuid.UUID, campaign_id: uuid.UUID | None = None
) -> tuple[int, int]:
    stmt = (
        select(func.count(CampaignEmployee.id), func.sum(_completed_flag))
        .select_from(CampaignEmployee)
        .join(Campaign, Campaign.id == CampaignEmployee.campaign_id)
        .where(Campaign.company_id == company_id)
    )
    if campaign_id is not None:
        stmt = stmt.where(Campaign.id == campaign_id)
    total, completed = db.execute(stmt).one()
    return int(total or 0), int(completed or 0)


def get_results_with_department(
    db: Session, company_id: uuid.UUID, campaign_id: uuid.UUID | None = None
) -> list[tuple[InterviewResult, str | None]]:
    stmt = (
        select(InterviewResult, Employee.department)
        .join(Employee, Employee.id == InterviewResult.employee_id)
        .where(InterviewResult.company_id == company_id)
    )
    if campaign_id is not None:
        stmt = stmt.where(InterviewResult.campaign_id == campaign_id)
    return [(r, dept) for r, dept in db.execute(stmt).all()]
