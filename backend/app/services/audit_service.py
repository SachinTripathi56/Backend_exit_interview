"""
Audit logging.

Call `log()` directly after a significant state change succeeds — never
before, and never for a request that failed validation/authorization
(a rejected attempt isn't "what happened", it's noise, and logging it
pre-authorization would itself leak information about resources the
caller couldn't access).

`extra_data` must never contain interview transcripts, full employee PII
beyond an id, or anything from `InterviewResult` — see the data-privacy
notes on that model. A resource id plus a short human-readable summary is
the right amount of detail for "what happened", not "here is the data".
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


class AuditAction:
    """Central registry of action strings so call sites can't typo a new one silently."""

    EMPLOYEE_CREATED = "employee.created"
    EMPLOYEE_UPDATED = "employee.updated"
    EMPLOYEE_DELETED = "employee.deleted"
    EMPLOYEE_IMPORT_CONFIRMED = "employee_import.confirmed"

    CAMPAIGN_CREATED = "campaign.created"
    CAMPAIGN_UPDATED = "campaign.updated"
    CAMPAIGN_DELETED = "campaign.deleted"
    CAMPAIGN_INVITATIONS_SENT = "campaign.invitations_sent"
    CAMPAIGN_REMINDERS_SENT = "campaign.reminders_sent"

    INTERVIEW_STARTED = "interview.started"
    INTERVIEW_COMPLETED = "interview.completed"

    REPORT_GENERATED = "report.generated"

    COMPANY_REGISTERED = "company.registered"
    EMPLOYEE_ACCESS_REDEEMED = "employee_access.redeemed"


def log(
    db: Session,
    *,
    company_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
    action: str,
    resource_type: str,
    resource_id: uuid.UUID | None,
    extra_data: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            id=uuid.uuid4(),
            company_id=company_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            extra_data=extra_data or {},
        )
    )
    # Deliberately no db.flush() here: audit logging piggybacks on the
    # caller's existing transaction (the request's get_db session, which
    # commits on success) rather than forcing an extra round-trip. If the
    # surrounding transaction rolls back, the audit entry rolls back with
    # it — which is correct, since the action it describes didn't happen.
