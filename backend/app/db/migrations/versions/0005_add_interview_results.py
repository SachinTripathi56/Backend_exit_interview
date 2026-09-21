"""add interview_results table

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-08

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "interview_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "interview_session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("interview_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("satisfaction_score", sa.Float(), nullable=True),
        sa.Column("exit_reasons", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("themes", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("recommendations", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("raw_ai_payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("interview_session_id", name="uq_interview_results_session"),
    )
    op.create_index("ix_interview_results_company_id", "interview_results", ["company_id"])
    op.create_index("ix_interview_results_employee_id", "interview_results", ["employee_id"])
    op.create_index("ix_interview_results_campaign_id", "interview_results", ["campaign_id"])
    op.create_index("ix_interview_results_interview_session_id", "interview_results", ["interview_session_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_interview_results_interview_session_id", table_name="interview_results")
    op.drop_index("ix_interview_results_campaign_id", table_name="interview_results")
    op.drop_index("ix_interview_results_employee_id", table_name="interview_results")
    op.drop_index("ix_interview_results_company_id", table_name="interview_results")
    op.drop_table("interview_results")
