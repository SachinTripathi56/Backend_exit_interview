"""Pydantic schemas for company creation / registration."""
from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr, Field, ConfigDict


class CompanyRegisterRequest(BaseModel):
    """
    Body for POST /api/v1/auth/register-company.

    This corresponds to the frontend's public `/register` route: a brand
    new HR user, who has already created a Clerk account client-side,
    registers their company and becomes its first HR_ADMIN.
    """

    company_name: str = Field(min_length=2, max_length=255)
    name: str = Field(min_length=1, max_length=255, description="The registering user's display name.")
    email: EmailStr


class CompanyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
