"""Campaign management endpoints. Invitations/reminders are in this same
router since they're campaign sub-resources — see the bottom of this file."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import TenantContext, get_tenant_context, require_hr
from app.db.database import get_db
from app.models.campaign import CampaignStatus
from app.models.user import User
from app.schemas.campaign import (
    CampaignCreateRequest,
    CampaignDetailResponse,
    CampaignResponse,
    CampaignUpdateRequest,
)
from app.schemas.common import PaginatedResponse
from app.schemas.invitation import BulkEmailResponse, InvitationSendRequest, ReminderSendRequest
from app.services import campaign_service, invitation_service

router = APIRouter(prefix="/hr/campaigns", tags=["campaigns"], dependencies=[Depends(require_hr)])


def _to_response(campaign) -> CampaignResponse:
    invited = sum(1 for a in campaign.assignments if a.invitation_status.value == "SENT")
    completed = sum(1 for a in campaign.assignments if a.interview_status.value == "COMPLETED")
    return CampaignResponse(
        id=campaign.id,
        company_id=campaign.company_id,
        name=campaign.name,
        description=campaign.description,
        instructions=campaign.instructions,
        start_at=campaign.start_at,
        end_at=campaign.end_at,
        status=campaign.status,
        created_by=campaign.created_by,
        created_at=campaign.created_at,
        updated_at=campaign.updated_at,
        employee_count=len(campaign.assignments),
        invited_count=invited,
        completed_count=completed,
    )


def _to_detail_response(campaign) -> CampaignDetailResponse:
    base = _to_response(campaign)
    return CampaignDetailResponse(**base.model_dump(), assignments=list(campaign.assignments))


@router.get("", response_model=PaginatedResponse[CampaignResponse], summary="List campaigns")
def list_campaigns(
    status_filter: CampaignStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
) -> PaginatedResponse[CampaignResponse]:
    items, total = campaign_service.list_campaigns(
        db, tenant.company_id, status=status_filter, page=page, limit=limit
    )
    return PaginatedResponse(items=[_to_response(c) for c in items], page=page, limit=limit, total=total)


@router.post("", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED, summary="Create a campaign")
def create_campaign(
    payload: CampaignCreateRequest,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
    current_user: User = Depends(require_hr),
) -> CampaignResponse:
    campaign = campaign_service.create_campaign(db, tenant.company_id, current_user.id, payload)
    return _to_response(campaign)


@router.get("/{campaign_id}", response_model=CampaignDetailResponse, summary="Get campaign detail")
def get_campaign(
    campaign_id: uuid.UUID,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
) -> CampaignDetailResponse:
    campaign = campaign_service.get_campaign_or_404(db, tenant.company_id, campaign_id)
    return _to_detail_response(campaign)


@router.put("/{campaign_id}", response_model=CampaignDetailResponse, summary="Update a campaign")
def update_campaign(
    campaign_id: uuid.UUID,
    payload: CampaignUpdateRequest,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
) -> CampaignDetailResponse:
    campaign = campaign_service.update_campaign(db, tenant.company_id, campaign_id, payload, tenant.user.id)
    return _to_detail_response(campaign)


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete or cancel a campaign")
def delete_campaign(
    campaign_id: uuid.UUID,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
) -> None:
    campaign_service.delete_campaign(db, tenant.company_id, campaign_id, tenant.user.id)


@router.post(
    "/{campaign_id}/invitations",
    response_model=BulkEmailResponse,
    summary="Send interview invitations to campaign employees",
    description=(
        "Generates a secure, single-use invitation token per employee, emails it, and "
        "logs the email. No plaintext credentials are ever sent."
    ),
)
def send_invitations(
    campaign_id: uuid.UUID,
    payload: InvitationSendRequest,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
) -> BulkEmailResponse:
    return invitation_service.send_invitations(
        db, tenant.company_id, campaign_id, payload.employee_ids, tenant.user.id
    )


@router.post(
    "/{campaign_id}/reminders",
    response_model=BulkEmailResponse,
    summary="Send reminders to eligible pending employees",
)
def send_reminders(
    campaign_id: uuid.UUID,
    payload: ReminderSendRequest,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
) -> BulkEmailResponse:
    return invitation_service.send_reminders(
        db, tenant.company_id, campaign_id, payload.employee_ids, tenant.user.id
    )
