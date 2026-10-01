"""
HR dashboard metrics.

NOTE (Phase 2 → later phases): `interview_sessions` doesn't exist yet
(that lands in Phase 6). Until then, interview-related counts are derived
from `Employee.status`, which already models interview lifecycle states
(INTERVIEW_PENDING / INTERVIEW_IN_PROGRESS / INTERVIEW_COMPLETED). This
keeps the response contract in API_CONTRACT.md stable for the frontend
from day one — the *values* get more accurate in Phase 6/7 when they're
recomputed from real interview_sessions + campaign windows instead, but
the shape of `GET /api/v1/hr/dashboard` will not change.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.employee import EmployeeStatus
from app.repositories import employee_repository as repo
from app.schemas.dashboard import HRDashboardResponse

_INTERVIEW_ENTERED_STATUSES = [
    EmployeeStatus.INTERVIEW_PENDING,
    EmployeeStatus.INTERVIEW_IN_PROGRESS,
    EmployeeStatus.INTERVIEW_COMPLETED,
]


def get_hr_dashboard(db: Session, company_id: uuid.UUID) -> HRDashboardResponse:
    total_employees = repo.count_by_company(db, company_id)
    total_interviews = repo.count_by_status(db, company_id, _INTERVIEW_ENTERED_STATUSES)
    completed_interviews = repo.count_by_status(db, company_id, [EmployeeStatus.INTERVIEW_COMPLETED])
    pending_interviews = repo.count_by_status(db, company_id, [EmployeeStatus.INTERVIEW_PENDING])
    # Expiry is a function of campaign end-date, which doesn't exist until
    # Phase 4 — reported as 0 until then rather than guessed.
    expired_interviews = 0

    completion_rate = (
        round((completed_interviews / total_interviews) * 100, 1) if total_interviews > 0 else 0.0
    )

    return HRDashboardResponse(
        total_employees=total_employees,
        total_interviews=total_interviews,
        completed_interviews=completed_interviews,
        pending_interviews=pending_interviews,
        expired_interviews=expired_interviews,
        completion_rate=completion_rate,
        active_campaigns=0,
    )
