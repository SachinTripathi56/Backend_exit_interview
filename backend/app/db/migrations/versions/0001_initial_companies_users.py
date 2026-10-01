"""initial: companies + users

Revision ID: 0001
Revises:
Create Date: 2026-09-06

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

user_role_enum = postgresql.ENUM("HR_ADMIN", "HR_USER", "EMPLOYEE", name="user_role",create_type=False)

def upgrade() -> None:
    # 1. Drop existing type if leftover from a bad run
    op.execute("DROP TYPE IF EXISTS user_role CASCADE;")
    
    # 2. Create the enum explicitly before tables
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE user_role AS ENUM ('HR_ADMIN', 'HR_USER', 'EMPLOYEE');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    op.create_table(
        "companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("industry", sa.String(length=255), nullable=True),
        sa.Column("company_size", sa.String(length=50), nullable=True),
        sa.Column("logo_url", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_companies_slug", "companies", ["slug"], unique=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("clerk_user_id", sa.String(length=255), nullable=False),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", user_role_enum, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_clerk_user_id", "users", ["clerk_user_id"], unique=True)
    op.create_index("ix_users_company_id", "users", ["company_id"])
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_employee_id", "users", ["employee_id"])


def downgrade() -> None:
    op.drop_index("ix_users_employee_id", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_company_id", table_name="users")
    op.drop_index("ix_users_clerk_user_id", table_name="users")
    op.drop_table("users")
    
    op.execute("DROP TYPE IF EXISTS user_role CASCADE;")

    op.drop_index("ix_companies_slug", table_name="companies")
    op.drop_table("companies")