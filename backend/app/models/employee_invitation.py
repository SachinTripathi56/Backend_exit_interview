"""
Employee invitation tokens.

An employee doesn't self-register: HR creates their `Employee` row (or
imports it), then an invitation email carries a single-use, expiring token
that — once redeemed via POST /api/v1/auth/employee-access alongside a
freshly-authenticated Clerk identity — creates the `User` row (role=
EMPLOYEE) linking that Clerk identity to this specific employee. This is
the "secure invitation token" approach the spec asks for instead of
plaintext passwords.

Only the SHA-256 hash of the token is stored, exactly like a password-reset
token: a database leak alone can never be used to redeem an invitation.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    pass


class InvitationTokenStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class EmployeeInvitation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "employee_invitations"

    company_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )

    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    status: Mapped[InvitationTokenStatus] = mapped_column(
        SAEnum(InvitationTokenStatus, name="invitation_token_status"),
        nullable=False,
        default=InvitationTokenStatus.PENDING,
    )

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<EmployeeInvitation employee_id={self.employee_id} status={self.status}>"
