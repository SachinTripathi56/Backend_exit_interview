"""
Interview completion.

Triggered exclusively by the internal webhook (`app/api/v1/internal/ai_callbacks.py`),
authenticated by shared secret rather than a Clerk token — the AI service
has no Clerk identity. This function derives the company/employee/campaign
entirely from the InterviewSession the ai_session_id points to; nothing
here trusts a company_id/employee_id if the webhook payload ever included
one (it doesn't, by design).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.campaign_employee import CampaignInterviewStatus
from app.models.email_log import EmailLog, EmailStatus, EmailType
from app.models.employee import Employee, EmployeeStatus
from app.models.interview_result import InterviewResult
from app.models.interview_session import InterviewSession, InterviewSessionStatus
from app.models.user import User, UserRole
from app.repositories import campaign_repository as campaign_repo
from app.repositories import interview_repository as interview_repo
from app.schemas.interview_completion import InterviewCompletedWebhookRequest
from app.services import email_service
from app.services import audit_service
from app.services.audit_service import AuditAction

logger = logging.getLogger(__name__)


def _notify_hr_admins(db: Session, company_id: uuid.UUID, employee_name: str, campaign_name: str) -> None:
    admins = db.query(User).filter(User.company_id == company_id, User.role == UserRole.HR_ADMIN).all()
    for admin in admins:
        result = email_service.send_hr_notification(
            admin.email,
            f"Exit interview completed: {campaign_name}",
            f"{employee_name} has completed their exit interview for {campaign_name}.",
        )
        db.add(
            EmailLog(
                id=uuid.uuid4(),
                company_id=company_id,
                campaign_id=None,
                employee_id=None,
                email_type=EmailType.HR_NOTIFICATION,
                recipient_email=admin.email,
                subject=f"Exit interview completed: {campaign_name}",
                status=EmailStatus.SENT if result.success else EmailStatus.FAILED,
                provider_response=result.provider_response,
            )
        )


def handle_interview_completed(db: Session, payload: InterviewCompletedWebhookRequest) -> InterviewSession:
    session = interview_repo.get_by_ai_session_id(db, payload.ai_session_id)
    if session is None:
        raise NotFoundError(f"No interview session found for ai_session_id={payload.ai_session_id!r}.")

    if payload.status == "ERROR":
        if session.status != InterviewSessionStatus.COMPLETED:
            session.status = InterviewSessionStatus.ERROR
            db.add(session)
            db.flush()
        return session

    # Idempotency: the AI service may retry a webhook delivery. If we've
    # already processed this session's completion, do nothing further
    # (no duplicate InterviewResult row, no duplicate confirmation email).
    if session.status == InterviewSessionStatus.COMPLETED:
        return session

    completed_at = payload.completed_at or datetime.now(timezone.utc)

    session.status = InterviewSessionStatus.COMPLETED
    session.completed_at = completed_at
    db.add(session)

    result_payload = payload.result
    db.add(
        InterviewResult(
            id=uuid.uuid4(),
            company_id=session.company_id,
            employee_id=session.employee_id,
            campaign_id=session.campaign_id,
            interview_session_id=session.id,
            transcript=result_payload.transcript if result_payload else None,
            summary=result_payload.summary if result_payload else None,
            satisfaction_score=result_payload.satisfaction_score if result_payload else None,
            exit_reasons=result_payload.exit_reasons if result_payload else [],
            themes=result_payload.themes if result_payload else [],
            recommendations=result_payload.recommendations if result_payload else [],
            raw_ai_payload=payload.raw,
        )
    )

    assignment = campaign_repo.get_assignment(db, session.campaign_id, session.employee_id)
    if assignment is not None:
        assignment.interview_status = CampaignInterviewStatus.COMPLETED
        assignment.completed_at = completed_at
        db.add(assignment)

    employee = db.get(Employee, session.employee_id)
    campaign_name = "your exit interview"
    if employee is not None:
        employee.status = EmployeeStatus.INTERVIEW_COMPLETED
        db.add(employee)

        campaign = campaign_repo.get_by_id(db, session.company_id, session.campaign_id)
        if campaign is not None:
            campaign_name = campaign.name

        confirmation = email_service.send_completion_confirmation(employee.email, employee.name, campaign_name)
        db.add(
            EmailLog(
                id=uuid.uuid4(),
                company_id=session.company_id,
                campaign_id=session.campaign_id,
                employee_id=employee.id,
                email_type=EmailType.COMPLETION_CONFIRMATION,
                recipient_email=employee.email,
                subject=f"Thank you for completing your {campaign_name} exit interview",
                status=EmailStatus.SENT if confirmation.success else EmailStatus.FAILED,
                provider_response=confirmation.provider_response,
            )
        )

        _notify_hr_admins(db, session.company_id, employee.name, campaign_name)

    db.flush()

    audit_service.log(
        db,
        company_id=session.company_id,
        user_id=None,  # actor is the AI service (webhook), not a platform user
        action=AuditAction.INTERVIEW_COMPLETED,
        resource_type="interview_session",
        resource_id=session.id,
        extra_data={"employee_id": str(session.employee_id), "campaign_id": str(session.campaign_id)},
    )
    return session
