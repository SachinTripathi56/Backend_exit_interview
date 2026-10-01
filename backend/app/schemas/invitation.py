"""Pydantic schemas for the invitation/reminder/employee-access flow."""
from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class InvitationSendRequest(BaseModel):
    employee_ids: list[uuid.UUID] | None = Field(
        default=None,
        description=(
            "If omitted, invites all eligible (not-yet-invited) employees in the campaign. "
            "If provided, (re)sends to exactly these employees regardless of current invitation_status."
        ),
    )


class ReminderSendRequest(BaseModel):
    employee_ids: list[uuid.UUID] | None = Field(
        default=None,
        description="If omitted, reminds all eligible pending employees in the campaign.",
    )


class BulkEmailResultItem(BaseModel):
    employee_id: uuid.UUID
    status: str  # "SENT" | "FAILED" | "SKIPPED"
    message: str | None = None


class BulkEmailResponse(BaseModel):
    sent_count: int
    failed_count: int
    skipped_count: int
    results: list[BulkEmailResultItem]


class EmployeeAccessRequest(BaseModel):
    """Body for POST /api/v1/auth/employee-access — redeems an invitation token."""

    token: str = Field(min_length=1)
