"""add employees table + FK from users.employee_id

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-06

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Pass create_type=False to disable SQLAlchemy automatic creation during create_table
employee_status_enum = postgresql.ENUM(
    "ACTIVE",
    "INVITED",
    "INTERVIEW_PENDING",
    "INTERVIEW_IN_PROGRESS",
    "INTERVIEW_COMPLETED",
    "DISABLED",
    name="employee_status",
    create_type=False,
)


def upgrade() -> None:
    # Safely handle ENUM creation
    op.execute("DROP TYPE IF EXISTS employee_status CASCADE;")
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE employee_status AS ENUM (
                'ACTIVE', 'INVITED', 'INTERVIEW_PENDING', 
                'INTERVIEW_IN_PROGRESS', 'INTERVIEW_COMPLETED', 'DISABLED'
            );
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    op.create_table(
        "employees",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("employee_id", sa.String(length=100), nullable=False),
        sa.Column("department", sa.String(length=255), nullable=True),
        sa.Column("designation", sa.String(length=255), nullable=True),
        sa.Column("last_working_date", sa.Date(), nullable=True),
        sa.Column("status", employee_status_enum, nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "employee_id", name="uq_employees_company_employee_code"),
        sa.UniqueConstraint("company_id", "email", name="uq_employees_company_email"),
    )
    op.create_index("ix_employees_company_id", "employees", ["company_id"])
    op.create_index("ix_employees_email", "employees", ["email"])
    op.create_index("ix_employees_employee_id", "employees", ["employee_id"])
    op.create_index("ix_employees_department", "employees", ["department"])

    # Deferred FK constraint
    op.create_foreign_key(
        "fk_users_employee_id_employees",
        "users",
        "employees",
        ["employee_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_employee_id_employees", "users", type_="foreignkey")

    op.drop_index("ix_employees_department", table_name="employees")
    op.drop_index("ix_employees_employee_id", table_name="employees")
    op.drop_index("ix_employees_email", table_name="employees")
    op.drop_index("ix_employees_company_id", table_name="employees")
    op.drop_table("employees")

    op.execute("DROP TYPE IF EXISTS employee_status CASCADE;")