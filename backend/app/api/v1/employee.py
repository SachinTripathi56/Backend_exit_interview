"""
Employee-facing endpoints.

Every endpoint here depends on `require_employee` AND scopes every query by
the CALLER's own `current_user.employee_id` + `company_id` — an employee
can only ever see or act on their own record. There is deliberately no
"employee_id" path parameter anywhere in this router.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import require_employee
from app.core.exceptions import NotFoundError
from app.db.database import get_db
from app.models.user import User
from app.schemas.employee_me import EmployeeMeResponse
from app.schemas.interview import (
    CampaignSummary,
    EmployeeInterviewResponse,
    InterviewSessionSummary,
    InterviewStartResponse,
    InterviewStatusResponse,
)
from app.services import interview_service

router = APIRouter(prefix="/employee", tags=["employee"], dependencies=[Depends(require_employee)])


def _require_linked_employee_id(current_user: User) -> None:
    if current_user.employee_id is None:
        raise NotFoundError("No employee record is linked to your account.")


@router.get("/me", response_model=EmployeeMeResponse, summary="Get the authenticated employee's own profile")
def get_employee_me(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_employee),
) -> EmployeeMeResponse:
    from app.models.employee import Employee

    _require_linked_employee_id(current_user)
    employee = db.get(Employee, current_user.employee_id)
    if employee is None or employee.company_id != current_user.company_id:
        raise NotFoundError("No employee record is linked to your account.")
    return EmployeeMeResponse.model_validate(employee)


@router.get(
    "/interview",
    response_model=EmployeeInterviewResponse,
    summary="Get the employee's assigned interview, if any",
)
def get_interview(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_employee),
) -> EmployeeInterviewResponse:
    _require_linked_employee_id(current_user)
    view = interview_service.get_employee_interview_view(db, current_user.company_id, current_user.employee_id)

    campaign = view["campaign"]
    session = view["session"]
    return EmployeeInterviewResponse(
        available=view["available"],
        status=view["status"],
        reason=view["reason"],
        campaign=CampaignSummary.model_validate(campaign, from_attributes=True) if campaign else None,
        interview_session=InterviewSessionSummary.model_validate(session, from_attributes=True) if session else None,
    )


@router.get(
    "/interview/status",
    response_model=InterviewStatusResponse,
    summary="Lightweight poll target for the current interview session status",
)
def get_interview_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_employee),
) -> InterviewStatusResponse:
    _require_linked_employee_id(current_user)
    result = interview_service.get_interview_status(db, current_user.company_id, current_user.employee_id)
    return InterviewStatusResponse(
        status=result["status"], interview_session_id=result["session_id"], completed_at=result["completed_at"]
    )


@router.post(
    "/interview/start",
    response_model=InterviewStartResponse,
    summary="Start (or resume) the authenticated employee's interview",
    description=(
        "Re-validates every access condition server-side (campaign assignment, active "
        "window, not already completed, not disabled) before ever contacting the AI "
        "interview service. See INTERVIEW START LOGIC in the API contract."
    ),
)
def start_interview(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_employee),
) -> InterviewStartResponse:
    _require_linked_employee_id(current_user)
    session, interview_url = interview_service.start_interview(db, current_user.company_id, current_user.employee_id)
    return InterviewStartResponse(
        interview_id=session.id,
        session_id=session.ai_session_id,
        status=session.status,
        interview_url=interview_url,
    )
