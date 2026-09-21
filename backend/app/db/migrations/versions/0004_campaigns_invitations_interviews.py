"""add campaigns, campaign_employees, employee_invitations, email_logs, interview_sessions

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-08

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

campaign_status_enum = postgresql.ENUM(
    "DRAFT", "SCHEDULED", "ACTIVE", "COMPLETED", "EXPIRED", "CANCELLED", name="campaign_status"
)
invitation_status_enum = postgresql.ENUM("NOT_SENT", "SENT", "FAILED", name="invitation_status")
campaign_interview_status_enum = postgresql.ENUM(
    "NOT_STARTED", "IN_PROGRESS", "COMPLETED", "EXPIRED", "CANCELLED", name="campaign_interview_status"
)
invitation_token_status_enum = postgresql.ENUM(
    "PENDING", "ACCEPTED", "EXPIRED", "REVOKED", name="invitation_token_status"
)
email_type_enum = postgresql.ENUM(
    "INVITATION", "REMINDER", "COMPLETION_CONFIRMATION", "HR_NOTIFICATION", name="email_type"
)
email_status_enum = postgresql.ENUM("SENT", "FAILED", name="email_status")
interview_session_status_enum = postgresql.ENUM(
    "NOT_STARTED", "IN_PROGRESS", "COMPLETED", "EXPIRED", "CANCELLED", "ERROR", name="interview_session_status"
)


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in (
        campaign_status_enum,
        invitation_status_enum,
        campaign_interview_status_enum,
        invitation_token_status_enum,
        email_type_enum,
        email_status_enum,
        interview_session_status_enum,
    ):
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "campaigns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", campaign_status_enum, nullable=False, server_default="DRAFT"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_campaigns_company_id", "campaigns", ["company_id"])

    op.create_table(
        "campaign_employees",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invitation_status", invitation_status_enum, nullable=False, server_default="NOT_SENT"),
        sa.Column("interview_status", campaign_interview_status_enum, nullable=False, server_default="NOT_STARTED"),
        sa.Column("invited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_reminded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("campaign_id", "employee_id", name="uq_campaign_employee"),
    )
    op.create_index("ix_campaign_employees_campaign_id", "campaign_employees", ["campaign_id"])
    op.create_index("ix_campaign_employees_employee_id", "campaign_employees", ["employee_id"])

    op.create_table(
        "employee_invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", invitation_token_status_enum, nullable=False, server_default="PENDING"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_employee_invitations_company_id", "employee_invitations", ["company_id"])
    op.create_index("ix_employee_invitations_employee_id", "employee_invitations", ["employee_id"])
    op.create_index("ix_employee_invitations_campaign_id", "employee_invitations", ["campaign_id"])
    op.create_index("ix_employee_invitations_token_hash", "employee_invitations", ["token_hash"], unique=True)

    op.create_table(
        "email_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("email_type", email_type_enum, nullable=False),
        sa.Column("recipient_email", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("status", email_status_enum, nullable=False),
        sa.Column("provider_response", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_email_logs_company_id", "email_logs", ["company_id"])
    op.create_index("ix_email_logs_campaign_id", "email_logs", ["campaign_id"])
    op.create_index("ix_email_logs_employee_id", "email_logs", ["employee_id"])

    op.create_table(
        "interview_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ai_session_id", sa.String(length=255), nullable=True),
        sa.Column("status", interview_session_status_enum, nullable=False, server_default="NOT_STARTED"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("employee_id", "campaign_id", name="uq_interview_session_employee_campaign"),
    )
    op.create_index("ix_interview_sessions_company_id", "interview_sessions", ["company_id"])
    op.create_index("ix_interview_sessions_employee_id", "interview_sessions", ["employee_id"])
    op.create_index("ix_interview_sessions_campaign_id", "interview_sessions", ["campaign_id"])
    op.create_index("ix_interview_sessions_ai_session_id", "interview_sessions", ["ai_session_id"])


def downgrade() -> None:
    op.drop_table("interview_sessions")
    op.drop_table("email_logs")
    op.drop_table("employee_invitations")
    op.drop_table("campaign_employees")
    op.drop_table("campaigns")

    bind = op.get_bind()
    for enum_type in (
        interview_session_status_enum,
        email_status_enum,
        email_type_enum,
        invitation_token_status_enum,
        campaign_interview_status_enum,
        invitation_status_enum,
        campaign_status_enum,
    ):
        enum_type.drop(bind, checkfirst=True)
