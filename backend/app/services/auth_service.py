"""
Business logic for account provisioning.

Clerk owns "who is this person" (identity + login). This service owns the
one-time bridge from a verified Clerk identity into our own `companies` /
`users` tables, which is where role and tenant membership actually live.
"""
from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError
from app.models.company import Company
from app.models.user import User, UserRole
from app.schemas.company import CompanyRegisterRequest
from app.services import audit_service
from app.services.audit_service import AuditAction


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "company"


def _unique_slug(db: Session, base_slug: str) -> str:
    slug = base_slug
    suffix = 1
    while db.execute(select(Company.id).where(Company.slug == slug)).first() is not None:
        suffix += 1
        slug = f"{base_slug}-{suffix}"
    return slug


def register_company_and_admin(db: Session, clerk_user_id: str, payload: CompanyRegisterRequest) -> User:
    """
    Create a brand-new Company plus its first HR_ADMIN user, linked to the
    given (already Clerk-authenticated) clerk_user_id.

    Raises ConflictError if this Clerk identity is already provisioned.
    """
    existing = db.execute(select(User).where(User.clerk_user_id == clerk_user_id)).scalar_one_or_none()
    if existing is not None:
        raise ConflictError("An account already exists for this identity.")

    slug = _unique_slug(db, _slugify(payload.company_name))

    company = Company(id=uuid.uuid4(), name=payload.company_name, slug=slug)
    db.add(company)
    db.flush()  # populate company.id without committing yet

    user = User(
        id=uuid.uuid4(),
        clerk_user_id=clerk_user_id,
        company_id=company.id,
        role=UserRole.HR_ADMIN,
        name=payload.name,
        email=payload.email,
    )
    db.add(user)
    db.flush()

    audit_service.log(
        db,
        company_id=company.id,
        user_id=user.id,
        action=AuditAction.COMPANY_REGISTERED,
        resource_type="company",
        resource_id=company.id,
        extra_data={"company_name": company.name},
    )
    return user
