"""Data-access layer for interview_sessions."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.interview_session import InterviewSession


def get_by_employee_and_campaign(
    db: Session, employee_id: uuid.UUID, campaign_id: uuid.UUID
) -> InterviewSession | None:
    stmt = select(InterviewSession).where(
        InterviewSession.employee_id == employee_id, InterviewSession.campaign_id == campaign_id
    )
    return db.execute(stmt).scalar_one_or_none()


def get_by_id(db: Session, company_id: uuid.UUID, session_id: uuid.UUID) -> InterviewSession | None:
    stmt = select(InterviewSession).where(
        InterviewSession.company_id == company_id, InterviewSession.id == session_id
    )
    return db.execute(stmt).scalar_one_or_none()


def get_by_ai_session_id(db: Session, ai_session_id: str) -> InterviewSession | None:
    """
    Deliberately NOT company-scoped: the AI service's completion webhook
    has no notion of "company" — it only knows the ai_session_id it was
    given at creation. The company is derived FROM the session found here,
    not supplied by the caller.
    """
    stmt = select(InterviewSession).where(InterviewSession.ai_session_id == ai_session_id)
    return db.execute(stmt).scalar_one_or_none()
