"""
Employee bulk import.

Per the spec: "Do NOT insert invalid records during the validation stage."
So an import goes through two distinct steps:

  1. POST /hr/employees/import — parse + validate the uploaded file
     synchronously, store the *validated* candidate rows on this record
     (`parsed_valid_rows`), and report per-row errors. Nothing is written
     to the `employees` table yet.
  2. POST /hr/employees/imports/{id}/confirm — re-checks the staged rows
     against the current state of `employees` (another import may have
     landed in between) and actually creates the employee records.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    pass


class ImportStatus(str, enum.Enum):
    VALIDATED = "VALIDATED"       # parsed + validated, awaiting confirmation
    CONFIRMED = "CONFIRMED"       # employees created (fully or partially)
    FAILED = "FAILED"             # file could not be parsed at all


class EmployeeImport(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "employee_imports"

    company_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    file_extension: Mapped[str] = mapped_column(String(10), nullable=False)

    # Original file kept in Cloudinary (private resource) purely for audit
    # trail / re-download by HR — never used to re-derive validation state.
    cloudinary_public_id: Mapped[str | None] = mapped_column(String(500), nullable=True)

    status: Mapped[ImportStatus] = mapped_column(SAEnum(ImportStatus, name="import_status"), nullable=False)

    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valid_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    invalid_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Staged, already-validated candidate rows (list[dict]) — the only
    # thing `confirm` reads from. Never written to `employees` until
    # confirm succeeds for that row.
    parsed_valid_rows: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)

    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    errors: Mapped[list["EmployeeImportError"]] = relationship(
        back_populates="import_", cascade="all, delete-orphan", order_by="EmployeeImportError.row_number"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<EmployeeImport id={self.id} status={self.status} company_id={self.company_id}>"


class EmployeeImportError(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "employee_import_errors"

    import_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("employee_imports.id", ondelete="CASCADE"), nullable=False, index=True
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    field: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)

    import_: Mapped["EmployeeImport"] = relationship(back_populates="errors")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<EmployeeImportError row={self.row_number} field={self.field!r}>"
