"""
InterviewSession = the platform's record of one employee's attempt at their
exit interview. `ai_session_id` is an opaque identifier handed back by the
separate, already-existing AI Interview FastAPI service — this platform
never re-implements interview conversation logic, only tracks access
control and lifecycle around it (see app/services/ai_interview_service.py).
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    pass


class InterviewSessionStatus(str, enum.Enum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"


class InterviewSession(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "interview_sessions"
    __table_args__ = (
        # One session per employee per campaign — "start" is idempotent and
        # resumes this row rather than ever creating a second one.
        UniqueConstraint("employee_id", "campaign_id", name="uq_interview_session_employee_campaign"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )

    ai_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    status: Mapped[InterviewSessionStatus] = mapped_column(
        SAEnum(InterviewSessionStatus, name="interview_session_status"),
        nullable=False,
        default=InterviewSessionStatus.NOT_STARTED,
    )

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<InterviewSession id={self.id} status={self.status} employee_id={self.employee_id}>"
