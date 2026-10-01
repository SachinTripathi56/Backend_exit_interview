"""Pydantic schemas for campaign management."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.campaign import CampaignStatus
from app.models.campaign_employee import CampaignInterviewStatus, InvitationStatus


class CampaignCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    instructions: str | None = None
    start_at: datetime
    end_at: datetime
    employee_ids: list[uuid.UUID] = Field(default_factory=list)


class CampaignUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    instructions: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    status: CampaignStatus | None = Field(
        default=None, description="Only CANCELLED may be set explicitly; other values are server-computed."
    )
    employee_ids: list[uuid.UUID] | None = Field(
        default=None,
        description="If provided, REPLACES the full assigned employee list. Omit to leave assignments untouched.",
    )


class CampaignAssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    employee_id: uuid.UUID
    invitation_status: InvitationStatus
    interview_status: CampaignInterviewStatus
    invited_at: datetime | None
    last_reminded_at: datetime | None
    completed_at: datetime | None


class CampaignResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    description: str | None
    instructions: str | None
    start_at: datetime
    end_at: datetime
    status: CampaignStatus
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    employee_count: int = 0
    invited_count: int = 0
    completed_count: int = 0


class CampaignDetailResponse(CampaignResponse):
    assignments: list[CampaignAssignmentResponse] = Field(default_factory=list)
