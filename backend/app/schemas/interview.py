"""Pydantic schemas for the employee interview flow (Phase 6)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.campaign_employee import CampaignInterviewStatus
from app.models.interview_session import InterviewSessionStatus


class CampaignSummary(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    instructions: str | None
    start_at: datetime
    end_at: datetime


class InterviewSessionSummary(BaseModel):
    id: uuid.UUID
    status: InterviewSessionStatus
    started_at: datetime | None
    completed_at: datetime | None


class EmployeeInterviewResponse(BaseModel):
    """
    GET /api/v1/employee/interview

    Deliberately never raises a 4xx just because nothing is assigned yet —
    that's a normal, expected state for an employee browsing their portal
    before any campaign targets them, not an error condition. `available`
    and `status` let the frontend render the right empty/blocked state.
    """

    available: bool
    status: CampaignInterviewStatus | None
    reason: str | None
    campaign: CampaignSummary | None
    interview_session: InterviewSessionSummary | None


class InterviewStatusResponse(BaseModel):
    """GET /api/v1/employee/interview/status — lightweight poll target."""

    status: CampaignInterviewStatus | None
    interview_session_id: uuid.UUID | None
    completed_at: datetime | None


class InterviewStartResponse(BaseModel):
    """POST /api/v1/employee/interview/start"""

    interview_id: uuid.UUID
    session_id: str | None
    status: InterviewSessionStatus
    interview_url: str | None
