"""add employee_imports + employee_import_errors tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-07

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Pass create_type=False so SQLAlchemy doesn't trigger duplicate ENUM creation
import_status_enum = postgresql.ENUM(
    "VALIDATED",
    "CONFIRMED",
    "FAILED",
    name="import_status",
    create_type=False,
)


def upgrade() -> None:
    # Drop leftover enum if present, then recreate safely
    op.execute("DROP TYPE IF EXISTS import_status CASCADE;")
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE import_status AS ENUM ('VALIDATED', 'CONFIRMED', 'FAILED');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    op.create_table(
        "employee_imports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "uploaded_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("file_name", sa.String(length=500), nullable=False),
        sa.Column("file_extension", sa.String(length=10), nullable=False),
        sa.Column("cloudinary_public_id", sa.String(length=500), nullable=True),
        sa.Column("status", import_status_enum, nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("valid_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("invalid_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("parsed_valid_rows", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_employee_imports_company_id", "employee_imports", ["company_id"])

    op.create_table(
        "employee_import_errors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "import_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employee_imports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("field", sa.String(length=100), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=False),
    )
    op.create_index("ix_employee_import_errors_import_id", "employee_import_errors", ["import_id"])


def downgrade() -> None:
    op.drop_index("ix_employee_import_errors_import_id", table_name="employee_import_errors")
    op.drop_table("employee_import_errors")

    op.drop_index("ix_employee_imports_company_id", table_name="employee_imports")
    op.drop_table("employee_imports")

    op.execute("DROP TYPE IF EXISTS import_status CASCADE;")