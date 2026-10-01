"""
Per-employee state within a campaign.

Two independent status tracks are kept deliberately separate:

  - `invitation_status`: did we successfully SEND the invitation email?
    (Phase 5 concern)
  - `interview_status`: where is the employee in the actual interview
    lifecycle? (Phase 6+ concern, mirrors `InterviewSession.status`)

Conflating these would make it impossible to represent "invited, but
hasn't started" vs "email failed to send" vs "in progress" cleanly.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.mixins import UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.campaign import Campaign


class InvitationStatus(str, enum.Enum):
    NOT_SENT = "NOT_SENT"
    SENT = "SENT"
    FAILED = "FAILED"


class CampaignInterviewStatus(str, enum.Enum):
    """
    Mirrors `InterviewSession.status` (introduced in Phase 6) so this column
    can be read cheaply from a campaign listing without a join, and kept in
    sync whenever the underlying session's status changes.
    """

    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class CampaignEmployee(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "campaign_employees"
    __table_args__ = (UniqueConstraint("campaign_id", "employee_id", name="uq_campaign_employee"),)

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )

    invitation_status: Mapped[InvitationStatus] = mapped_column(
        SAEnum(InvitationStatus, name="invitation_status"), nullable=False, default=InvitationStatus.NOT_SENT
    )
    interview_status: Mapped[CampaignInterviewStatus] = mapped_column(
        SAEnum(CampaignInterviewStatus, name="campaign_interview_status"),
        nullable=False,
        default=CampaignInterviewStatus.NOT_STARTED,
    )

    invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    campaign: Mapped["Campaign"] = relationship(back_populates="assignments")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CampaignEmployee campaign_id={self.campaign_id} employee_id={self.employee_id}>"
