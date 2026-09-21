"""Reusable SQLAlchemy mixins used across all models."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UUIDPrimaryKeyMixin:
    """
    Public-facing UUID primary key.

    We use UUIDs (not sequential integers) as public identifiers so that
    resource IDs never leak information (row counts, creation order) and
    can't be trivially enumerated by a malicious tenant.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    """created_at / updated_at columns, always stored in UTC."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
