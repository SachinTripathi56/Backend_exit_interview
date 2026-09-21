"""
Campaign business logic.

Status computation (`refresh_status`) is the key piece: `ACTIVE`/`EXPIRED`
are never set directly by an API call — they're derived from server time
compared against `start_at`/`end_at`, exactly as section 25 of the spec
requires ("Never rely on frontend clock"). The only status a caller can set
directly is `CANCELLED` (and `DRAFT`, only at creation with no employees
assigned yet).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import CampaignInvalidScheduleError, ConflictError, NotFoundError, ValidationAppError
from app.models.campaign import Campaign, CampaignStatus
from app.models.campaign_employee import CampaignEmployee, CampaignInterviewStatus
from app.models.employee import Employee
from app.repositories import campaign_repository as repo
from app.schemas.campaign import CampaignCreateRequest, CampaignUpdateRequest
from app.services import audit_service
from app.services.audit_service import AuditAction


def _validate_schedule(start_at: datetime, end_at: datetime) -> None:
    if start_at >= end_at:
        raise CampaignInvalidScheduleError("start_at must be strictly before end_at.")


def _validate_employee_ids(db: Session, company_id: uuid.UUID, employee_ids: list[uuid.UUID]) -> list[Employee]:
    if not employee_ids:
        return []
    stmt = select(Employee).where(Employee.company_id == company_id, Employee.id.in_(employee_ids))
    found = list(db.execute(stmt).scalars().all())
    found_ids = {e.id for e in found}
    missing = [str(eid) for eid in employee_ids if eid not in found_ids]
    if missing:
        # Deliberately a generic validation error, not 404: this is a
        # request-shape problem ("some of the IDs you sent don't belong to
        # your company"), not "the campaign resource wasn't found".
        raise ValidationAppError(
            "One or more employee_ids are invalid or do not belong to your company: " + ", ".join(missing)
        )
    return found


def compute_status(campaign: Campaign, now: datetime | None = None) -> CampaignStatus:
    """Pure function: derive the *display* status without mutating anything."""
    now = now or datetime.now(timezone.utc)

    if campaign.status in (CampaignStatus.CANCELLED, CampaignStatus.DRAFT):
        return campaign.status

    if now < campaign.start_at:
        return CampaignStatus.SCHEDULED
    if now <= campaign.end_at:
        return CampaignStatus.ACTIVE

    # Past end_at: distinguish COMPLETED (everyone finished) from EXPIRED
    # (window closed but at least one employee never finished).
    assignments = campaign.assignments
    if assignments and all(a.interview_status == CampaignInterviewStatus.COMPLETED for a in assignments):
        return CampaignStatus.COMPLETED
    return CampaignStatus.EXPIRED


def refresh_status(db: Session, campaign: Campaign) -> Campaign:
    """Recompute and persist status if it has changed. Call before returning any campaign to a client."""
    new_status = compute_status(campaign)
    if new_status != campaign.status:
        campaign.status = new_status
        db.add(campaign)
        db.flush()
    return campaign


def create_campaign(
    db: Session, company_id: uuid.UUID, created_by: uuid.UUID, payload: CampaignCreateRequest
) -> Campaign:
    _validate_schedule(payload.start_at, payload.end_at)
    employees = _validate_employee_ids(db, company_id, payload.employee_ids)

    initial_status = CampaignStatus.DRAFT if not employees else CampaignStatus.SCHEDULED

    campaign = Campaign(
        id=uuid.uuid4(),
        company_id=company_id,
        name=payload.name,
        description=payload.description,
        instructions=payload.instructions,
        start_at=payload.start_at,
        end_at=payload.end_at,
        status=initial_status,
        created_by=created_by,
    )
    db.add(campaign)
    db.flush()

    for employee in employees:
        db.add(CampaignEmployee(id=uuid.uuid4(), campaign_id=campaign.id, employee_id=employee.id))
    db.flush()
    db.refresh(campaign)

    campaign = refresh_status(db, campaign)
    audit_service.log(
        db,
        company_id=company_id,
        user_id=created_by,
        action=AuditAction.CAMPAIGN_CREATED,
        resource_type="campaign",
        resource_id=campaign.id,
        extra_data={"name": campaign.name, "employee_count": len(employees)},
    )
    return campaign


def get_campaign_or_404(db: Session, company_id: uuid.UUID, campaign_id: uuid.UUID) -> Campaign:
    campaign = repo.get_by_id(db, company_id, campaign_id)
    if campaign is None:
        raise NotFoundError("Campaign not found.")
    return refresh_status(db, campaign)


def list_campaigns(
    db: Session, company_id: uuid.UUID, *, status: CampaignStatus | None, page: int, limit: int
) -> tuple[list[Campaign], int]:
    items, total = repo.list_paginated(db, company_id, status=status, page=page, limit=limit)
    items = [refresh_status(db, c) for c in items]
    return items, total


def update_campaign(
    db: Session,
    company_id: uuid.UUID,
    campaign_id: uuid.UUID,
    payload: CampaignUpdateRequest,
    actor_user_id: uuid.UUID | None = None,
) -> Campaign:
    campaign = get_campaign_or_404(db, company_id, campaign_id)

    if campaign.status in (CampaignStatus.COMPLETED, CampaignStatus.CANCELLED):
        raise ConflictError(f"Cannot modify a campaign that is {campaign.status.value}.")

    new_start = payload.start_at or campaign.start_at
    new_end = payload.end_at or campaign.end_at
    if payload.start_at or payload.end_at:
        _validate_schedule(new_start, new_end)
        campaign.start_at = new_start
        campaign.end_at = new_end

    if payload.name is not None:
        campaign.name = payload.name
    if payload.description is not None:
        campaign.description = payload.description
    if payload.instructions is not None:
        campaign.instructions = payload.instructions

    if payload.status is not None:
        if payload.status != CampaignStatus.CANCELLED:
            raise ValidationAppError("Only CANCELLED may be set explicitly; other statuses are server-computed.")
        campaign.status = CampaignStatus.CANCELLED

    if payload.employee_ids is not None:
        if campaign.status == CampaignStatus.ACTIVE:
            raise ConflictError("Cannot change the assigned employee list once a campaign is active.")
        employees = _validate_employee_ids(db, company_id, payload.employee_ids)
        existing_by_employee = {a.employee_id: a for a in campaign.assignments}
        keep_ids = {e.id for e in employees}

        for employee_id, assignment in list(existing_by_employee.items()):
            if employee_id not in keep_ids:
                db.delete(assignment)

        for employee in employees:
            if employee.id not in existing_by_employee:
                db.add(CampaignEmployee(id=uuid.uuid4(), campaign_id=campaign.id, employee_id=employee.id))

        db.flush()
        db.refresh(campaign)
        if campaign.status == CampaignStatus.DRAFT and employees:
            campaign.status = CampaignStatus.SCHEDULED

    db.add(campaign)
    db.flush()
    db.refresh(campaign)
    campaign = refresh_status(db, campaign)

    audit_service.log(
        db,
        company_id=company_id,
        user_id=actor_user_id,
        action=AuditAction.CAMPAIGN_UPDATED,
        resource_type="campaign",
        resource_id=campaign.id,
        extra_data={"new_status": campaign.status.value},
    )
    return campaign


def delete_campaign(
    db: Session, company_id: uuid.UUID, campaign_id: uuid.UUID, actor_user_id: uuid.UUID | None = None
) -> None:
    campaign = get_campaign_or_404(db, company_id, campaign_id)

    if campaign.status == CampaignStatus.DRAFT:
        db.delete(campaign)
    else:
        campaign.status = CampaignStatus.CANCELLED
        db.add(campaign)
    db.flush()

    audit_service.log(
        db,
        company_id=company_id,
        user_id=actor_user_id,
        action=AuditAction.CAMPAIGN_DELETED,
        resource_type="campaign",
        resource_id=campaign_id,
        extra_data={},
    )
