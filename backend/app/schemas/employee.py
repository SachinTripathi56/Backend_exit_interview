"""Pydantic schemas for employee management."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.employee import EmployeeStatus


class EmployeeBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    employee_id: str = Field(min_length=1, max_length=100, description="HR-assigned employee code, e.g. 'EMP1023'.")
    department: str | None = Field(default=None, max_length=255)
    designation: str | None = Field(default=None, max_length=255)
    last_working_date: date | None = None


class EmployeeCreateRequest(EmployeeBase):
    status: EmployeeStatus = EmployeeStatus.ACTIVE


class EmployeeUpdateRequest(BaseModel):
    """All fields optional — only supplied fields are updated (PATCH-like semantics via PUT)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None
    employee_id: str | None = Field(default=None, min_length=1, max_length=100)
    department: str | None = Field(default=None, max_length=255)
    designation: str | None = Field(default=None, max_length=255)
    last_working_date: date | None = None
    status: EmployeeStatus | None = None


class EmployeeResponse(EmployeeBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    status: EmployeeStatus
    created_at: datetime
    updated_at: datetime
