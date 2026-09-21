"""
Company = tenant.

Every company-scoped resource (employees, campaigns, interviews, reports,
audit logs, ...) carries a company_id foreign key back to this table.
Tenant isolation is enforced at the query layer using this column — see
app/api/dependencies.py and the repositories.
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class Company(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)

    # Reserved for future use — kept nullable so they can be added without
    # a breaking migration for existing tenants.
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_size: Mapped[str | None] = mapped_column(String(50), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    users: Mapped[list["User"]] = relationship(back_populates="company")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Company id={self.id} slug={self.slug!r}>"
