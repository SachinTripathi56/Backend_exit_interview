"""add reports table

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-09

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

report_format_enum = postgresql.ENUM("PDF", "EXCEL", name="report_format")
report_status_enum = postgresql.ENUM("COMPLETED", "FAILED", name="report_status")


def upgrade() -> None:
    bind = op.get_bind()
    report_format_enum.create(bind, checkfirst=True)
    report_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("format", report_format_enum, nullable=False),
        sa.Column("status", report_status_enum, nullable=False),
        sa.Column("file_name", sa.String(length=500), nullable=False),
        sa.Column("cloudinary_public_id", sa.String(length=500), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_reports_company_id", "reports", ["company_id"])
    op.create_index("ix_reports_campaign_id", "reports", ["campaign_id"])


def downgrade() -> None:
    op.drop_index("ix_reports_campaign_id", table_name="reports")
    op.drop_index("ix_reports_company_id", table_name="reports")
    op.drop_table("reports")

    bind = op.get_bind()
    report_status_enum.drop(bind, checkfirst=True)
    report_format_enum.drop(bind, checkfirst=True)
