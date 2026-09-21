"""
Every email the platform sends (via any provider) gets a row here — this is
what the spec's "Create email logs" requirement for invitations/reminders
maps to, and doubles as the audit trail for "was this employee actually
emailed?" support questions.
"""
from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    pass


class EmailType(str, enum.Enum):
    INVITATION = "INVITATION"
    REMINDER = "REMINDER"
    COMPLETION_CONFIRMATION = "COMPLETION_CONFIRMATION"
    HR_NOTIFICATION = "HR_NOTIFICATION"


class EmailStatus(str, enum.Enum):
    SENT = "SENT"
    FAILED = "FAILED"


class EmailLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "email_logs"

    company_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True, index=True
    )
    employee_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True
    )

    email_type: Mapped[EmailType] = mapped_column(SAEnum(EmailType, name="email_type"), nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[EmailStatus] = mapped_column(SAEnum(EmailStatus, name="email_status"), nullable=False)
    provider_response: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<EmailLog type={self.email_type} status={self.status} recipient={self.recipient_email!r}>"
