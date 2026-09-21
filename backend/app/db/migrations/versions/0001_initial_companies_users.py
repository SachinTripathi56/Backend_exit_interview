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

user_role_enum = postgresql.ENUM("HR_ADMIN", "HR_USER", "EMPLOYEE", name="user_role")


def upgrade() -> None:
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

    user_role_enum.create(op.get_bind(), checkfirst=True)

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
    user_role_enum.drop(op.get_bind(), checkfirst=True)

    op.drop_index("ix_companies_slug", table_name="companies")
    op.drop_table("companies")
