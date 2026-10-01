"""Pydantic schemas for report generation/listing/download."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.report import ReportFormat, ReportStatus


class ReportGenerateRequest(BaseModel):
    campaign_id: uuid.UUID | None = None
    format: ReportFormat = ReportFormat.PDF


class ReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    campaign_id: uuid.UUID | None
    format: ReportFormat
    status: ReportStatus
    file_name: str
    error_message: str | None
    generated_at: datetime | None
    created_at: datetime
