"""
Audit trail for significant actions across the platform.

Deliberately schema-light: `action` is a short dotted string
("employee.created", "campaign.cancelled", "interview.completed", ...),
`resource_type`/`resource_id` identify what it happened to, and `metadata`
carries whatever extra context that specific action needs — this avoids a
new migration every time a new event type is added, at the cost of the
caller needing to be disciplined about what it puts in `metadata` (never
raw transcripts or full PII dumps — see app/services/audit_service.py).
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class AuditLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "audit_logs"

    company_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)

    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    extra_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AuditLog action={self.action!r} resource_type={self.resource_type!r}>"
