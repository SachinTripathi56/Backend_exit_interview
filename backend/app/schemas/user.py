"""Pydantic schemas for user-related API responses."""
from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict

from app.models.user import UserRole


class CurrentUserResponse(BaseModel):
    """Response shape for GET /api/v1/me — matches the frontend contract exactly."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    clerk_user_id: str
    role: UserRole
    company_id: uuid.UUID
    name: str
    email: str
