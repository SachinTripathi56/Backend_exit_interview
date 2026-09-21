"""Pydantic schema for the employee's own profile view."""
from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict

from app.models.employee import EmployeeStatus


class EmployeeMeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    email: str
    employee_id: str
    department: str | None
    designation: str | None
    last_working_date: date | None
    status: EmployeeStatus
