"""
InterviewResult = the stored outcome of a completed interview, as reported
by the (separate, already-existing) AI Interview service via the
completion webhook.

Per spec section 26 (Data Privacy): this table holds the most sensitive
data in the whole platform. No HR-facing endpoint returns rows from this
table directly or individually — Phase 8's `/hr/analytics` only ever reads
AGGREGATED values out of it (averages, counts, frequency-ranked lists),
never a single employee's transcript or an identifiable single response.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Float, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class InterviewResult(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "interview_results"

    company_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    interview_session_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("interview_sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Free-text fields from the AI service. Never surfaced individually to
    # HR — only aggregated/summarized in analytics.
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    satisfaction_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_reasons: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    themes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    recommendations: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    # Full raw payload from the AI service, kept for audit/debugging only.
    raw_ai_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<InterviewResult interview_session_id={self.interview_session_id}>"
