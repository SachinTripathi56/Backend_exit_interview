"""
Report = a generated exit-interview report (PDF or Excel), scoped either to
one campaign or to the whole company.

The generated file bytes themselves are NOT persisted in Postgres — this
row is metadata (who requested it, when, in what format, and whether it
succeeded). The actual content is deterministically rebuilt from current
aggregate data at download time (see `app/services/report_service.py`),
and best-effort archived to Cloudinary as a private/authenticated resource
for audit purposes, matching the same pattern used for import file
archival in Phase 3.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    pass


class ReportFormat(str, enum.Enum):
    PDF = "PDF"
    EXCEL = "EXCEL"


class ReportStatus(str, enum.Enum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Report(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "reports"

    company_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True, index=True
    )
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    format: Mapped[ReportFormat] = mapped_column(SAEnum(ReportFormat, name="report_format"), nullable=False)
    status: Mapped[ReportStatus] = mapped_column(SAEnum(ReportStatus, name="report_status"), nullable=False)

    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    cloudinary_public_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Report id={self.id} format={self.format} status={self.status}>"
