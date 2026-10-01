"""
Employee = an application entity representing a departing employee, created
by HR (manually or via bulk import) ahead of that person ever logging in.

A Clerk-authenticated employee identity is linked back to a row here via
`users.employee_id` (see models/user.py) once they access their portal —
but the employee record itself exists independently of any login.
"""
from __future__ import annotations

import enum
import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, Enum as SAEnum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.company import Company


class EmployeeStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INVITED = "INVITED"
    INTERVIEW_PENDING = "INTERVIEW_PENDING"
    INTERVIEW_IN_PROGRESS = "INTERVIEW_IN_PROGRESS"
    INTERVIEW_COMPLETED = "INTERVIEW_COMPLETED"
    DISABLED = "DISABLED"


class Employee(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "employees"
    __table_args__ = (
        # A company cannot have two employees with the same business
        # employee code or the same email — but two DIFFERENT companies
        # can (multi-tenant), so uniqueness is scoped by company_id.
        UniqueConstraint("company_id", "employee_id", name="uq_employees_company_employee_code"),
        UniqueConstraint("company_id", "email", name="uq_employees_company_email"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Business-facing employee code (what HR calls "Employee ID" in the UI
    # and in imports) — distinct from this row's system `id` (UUID PK).
    employee_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    department: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    designation: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_working_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    status: Mapped[EmployeeStatus] = mapped_column(
        SAEnum(EmployeeStatus, name="employee_status"),
        nullable=False,
        default=EmployeeStatus.ACTIVE,
    )

    company: Mapped["Company"] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Employee id={self.id} employee_id={self.employee_id!r} company_id={self.company_id}>"
