"""Pydantic schemas for employee bulk import."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.employee_import import ImportStatus


class ImportErrorItem(BaseModel):
    row: int
    field: str
    message: str


class ImportValidationResponse(BaseModel):
    """Response for POST /api/v1/hr/employees/import."""

    import_id: uuid.UUID
    total_rows: int
    valid_rows: int
    invalid_rows: int
    errors: list[ImportErrorItem]


class ImportDetailResponse(BaseModel):
    """Response for GET /api/v1/hr/employees/imports/{import_id}."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    file_name: str
    file_extension: str
    status: ImportStatus
    total_rows: int
    valid_rows: int
    invalid_rows: int
    created_at: datetime
    confirmed_at: datetime | None
    errors: list[ImportErrorItem]


class ImportConfirmResponse(BaseModel):
    """Response for POST /api/v1/hr/employees/imports/{import_id}/confirm."""

    import_id: uuid.UUID
    created_count: int
    skipped_count: int
    errors: list[ImportErrorItem]
