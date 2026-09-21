"""
Internal application user.

Clerk answers "who is this user?" (identity). This table answers
"what company do they belong to, and what role do they have?"
(authorization). Every authenticated request resolves to exactly one row
here via clerk_user_id — see app/api/dependencies.py.
"""
from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.company import Company


class UserRole(str, enum.Enum):
    """
    Kept extensible: new roles can be added without changing the shape of
    the authorization system, since checks should be based on role
    capability helpers rather than scattered string comparisons.
    """

    HR_ADMIN = "HR_ADMIN"
    HR_USER = "HR_USER"
    EMPLOYEE = "EMPLOYEE"

    @property
    def is_hr(self) -> bool:
        return self in (UserRole.HR_ADMIN, UserRole.HR_USER)


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    clerk_user_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole, name="user_role"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Set when this user account corresponds to an `employees` row (i.e. the
    # user is logging in as an employee to take their exit interview).
    #
    # NOTE: the FK constraint to employees.id is added via an Alembic
    # migration in Phase 2 once the `employees` table exists (see
    # db/migrations). Declaring it as a bare UUID column here avoids a
    # forward-reference mapper error while the tables are introduced
    # incrementally, phase by phase.
    employee_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True, index=True
    )

    company: Mapped["Company"] = relationship(back_populates="users")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User id={self.id} role={self.role} company_id={self.company_id}>"
