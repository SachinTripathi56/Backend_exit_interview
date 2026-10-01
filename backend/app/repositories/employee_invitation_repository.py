"""Data-access layer for employee_invitations."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.employee_invitation import EmployeeInvitation, InvitationTokenStatus


def get_pending_by_token_hash(db: Session, token_hash: str) -> EmployeeInvitation | None:
    stmt = select(EmployeeInvitation).where(
        EmployeeInvitation.token_hash == token_hash,
        EmployeeInvitation.status == InvitationTokenStatus.PENDING,
    )
    return db.execute(stmt).scalar_one_or_none()


def revoke_pending_for_employee_campaign(db: Session, employee_id: uuid.UUID, campaign_id: uuid.UUID) -> None:
    stmt = select(EmployeeInvitation).where(
        EmployeeInvitation.employee_id == employee_id,
        EmployeeInvitation.campaign_id == campaign_id,
        EmployeeInvitation.status == InvitationTokenStatus.PENDING,
    )
    for invitation in db.execute(stmt).scalars().all():
        invitation.status = InvitationTokenStatus.REVOKED
        db.add(invitation)
