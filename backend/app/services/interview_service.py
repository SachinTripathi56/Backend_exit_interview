"""
Employee interview session management.

`start_interview` is the security-critical function in this whole backend:
it is the ONLY path that may put an employee in front of the AI interview,
and it re-derives every fact it needs (campaign membership, campaign
window, completion state, disabled state) from the database using the
authenticated employee's own identity — never from anything the client
claims. This directly implements the spec's 10-step "Interview start
logic" checklist; each check below is numbered to match it.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import (
    ForbiddenError,
    InterviewAlreadyCompletedError,
    InterviewNotAvailableError,
    NotFoundError,
)
from app.models.campaign import CampaignStatus
from app.models.campaign_employee import CampaignInterviewStatus
from app.models.employee import Employee, EmployeeStatus
from app.models.interview_session import InterviewSession, InterviewSessionStatus
from app.repositories import campaign_repository as campaign_repo
from app.repositories import interview_repository as interview_repo
from app.services import ai_interview_service
from app.services import audit_service
from app.services.audit_service import AuditAction
from app.services.campaign_service import compute_status as compute_campaign_status


def _get_employee_or_404(db: Session, company_id: uuid.UUID, employee_id: uuid.UUID) -> Employee:
    employee = db.get(Employee, employee_id)
    if employee is None or employee.company_id != company_id:
        raise NotFoundError("Employee record not found.")
    return employee


def get_employee_interview_view(db: Session, company_id: uuid.UUID, employee_id: uuid.UUID):
    """Backing logic for GET /api/v1/employee/interview — never raises for 'nothing assigned yet'."""
    result = campaign_repo.get_active_assignment_for_employee(db, company_id, employee_id)
    if result is None:
        return {"available": False, "status": None, "reason": "No interview has been assigned to you yet.", "campaign": None, "session": None}

    assignment, campaign = result
    live_status = compute_campaign_status(campaign)

    session = interview_repo.get_by_employee_and_campaign(db, employee_id, campaign.id)

    if live_status == CampaignStatus.SCHEDULED:
        return {
            "available": False,
            "status": assignment.interview_status,
            "reason": f"Your interview opens on {campaign.start_at.isoformat()}.",
            "campaign": campaign,
            "session": session,
        }
    if live_status in (CampaignStatus.EXPIRED, CampaignStatus.CANCELLED):
        return {
            "available": False,
            "status": assignment.interview_status,
            "reason": "This interview window has closed.",
            "campaign": campaign,
            "session": session,
        }
    if assignment.interview_status == CampaignInterviewStatus.COMPLETED:
        return {
            "available": False,
            "status": assignment.interview_status,
            "reason": "You have already completed this interview.",
            "campaign": campaign,
            "session": session,
        }

    return {"available": True, "status": assignment.interview_status, "reason": None, "campaign": campaign, "session": session}


def get_interview_status(db: Session, company_id: uuid.UUID, employee_id: uuid.UUID):
    result = campaign_repo.get_active_assignment_for_employee(db, company_id, employee_id)
    if result is None:
        return {"status": None, "session_id": None, "completed_at": None}
    assignment, campaign = result
    session = interview_repo.get_by_employee_and_campaign(db, employee_id, campaign.id)
    return {
        "status": assignment.interview_status,
        "session_id": session.id if session else None,
        "completed_at": session.completed_at if session else None,
    }


def start_interview(db: Session, company_id: uuid.UUID, employee_id: uuid.UUID) -> tuple[InterviewSession, str | None]:
    # 1-2. Caller is already Clerk-authenticated + role=EMPLOYEE (enforced by
    #      `require_employee` before this function is ever called).
    # 3-4. Employee exists and belongs to the authenticated company.
    employee = _get_employee_or_404(db, company_id, employee_id)

    # 11. Employee is not disabled.
    if employee.status == EmployeeStatus.DISABLED:
        raise ForbiddenError("Your account has been disabled.")

    # 5-6. Employee has an assigned campaign; campaign exists.
    result = campaign_repo.get_active_assignment_for_employee(db, company_id, employee_id)
    if result is None:
        raise InterviewNotAvailableError("You do not have an assigned interview.")
    assignment, campaign = result

    # 7-8. Campaign is active, and current server time is within its window
    #      (compute_status derives this from server time, never the client's).
    live_status = compute_campaign_status(campaign)
    if live_status == CampaignStatus.SCHEDULED:
        raise InterviewNotAvailableError("Your interview has not started yet.")
    if live_status in (CampaignStatus.EXPIRED, CampaignStatus.CANCELLED, CampaignStatus.COMPLETED):
        raise InterviewNotAvailableError("Your interview window has closed.")
    if live_status != CampaignStatus.ACTIVE:
        raise InterviewNotAvailableError("Your interview is not currently available.")

    # 9. Employee has not already completed the interview.
    if assignment.interview_status == CampaignInterviewStatus.COMPLETED:
        raise InterviewAlreadyCompletedError()

    # All checks passed — create the session if needed, or resume it.
    session = interview_repo.get_by_employee_and_campaign(db, employee_id, campaign.id)
    if session is None:
        session = InterviewSession(
            id=uuid.uuid4(),
            company_id=company_id,
            employee_id=employee_id,
            campaign_id=campaign.id,
            status=InterviewSessionStatus.NOT_STARTED,
        )
        db.add(session)
        db.flush()

    if session.status == InterviewSessionStatus.COMPLETED:
        # Defensive: campaign_employees said not-completed but the session
        # itself disagrees. Trust the session and stop rather than
        # re-issuing a completed interview.
        raise InterviewAlreadyCompletedError()

    if session.status == InterviewSessionStatus.IN_PROGRESS and session.ai_session_id:
        # Idempotent resume: don't call the AI service again. We don't have
        # a fresh interview_url from the AI service on resume, which is
        # fine — the frontend should already be holding onto it from the
        # original /start response for an in-progress interview.
        return session, None

    handle = ai_interview_service.create_session(
        employee_id=employee_id, campaign_id=campaign.id, interview_session_id=session.id
    )
    session.ai_session_id = handle.ai_session_id
    session.status = InterviewSessionStatus.IN_PROGRESS
    if session.started_at is None:
        session.started_at = datetime.now(timezone.utc)
    db.add(session)

    assignment.interview_status = CampaignInterviewStatus.IN_PROGRESS
    db.add(assignment)

    if employee.status in (EmployeeStatus.ACTIVE, EmployeeStatus.INVITED):
        employee.status = EmployeeStatus.INTERVIEW_IN_PROGRESS
        db.add(employee)

    db.flush()

    audit_service.log(
        db,
        company_id=company_id,
        user_id=None,  # actor is the employee, identified by employee_id in extra_data below;
        # this function only receives Employee.id, not the linked User.id
        action=AuditAction.INTERVIEW_STARTED,
        resource_type="interview_session",
        resource_id=session.id,
        extra_data={"employee_id": str(employee_id), "campaign_id": str(campaign.id)},
    )
    return session, handle.interview_url
