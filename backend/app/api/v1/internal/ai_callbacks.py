"""
Internal, service-to-service endpoint.

This router is deliberately NOT under /hr or /employee and does NOT depend
on Clerk authentication — the AI Interview service has no Clerk identity.
It is authenticated by a shared secret (AI_INTERNAL_WEBHOOK_SECRET) via the
X-Webhook-Secret header instead. Never expose this path to the frontend or
document it in a way that suggests browser-callable access.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import verify_ai_webhook
from app.db.database import get_db
from app.schemas.interview_completion import (
    InterviewCompletedWebhookRequest,
    InterviewCompletedWebhookResponse,
)
from app.services import interview_completion_service

router = APIRouter(prefix="/internal/ai", tags=["internal"], dependencies=[Depends(verify_ai_webhook)])


@router.post(
    "/interview-completed",
    response_model=InterviewCompletedWebhookResponse,
    summary="[Internal] AI interview service reports interview completion",
    description=(
        "Called by the separate AI Interview FastAPI service when an interview "
        "finishes (or errors). Authenticated via the X-Webhook-Secret header, "
        "never a Clerk token. Idempotent: redelivering the same ai_session_id "
        "after it was already processed as COMPLETED is a safe no-op."
    ),
)
def interview_completed(
    payload: InterviewCompletedWebhookRequest,
    db: Session = Depends(get_db),
) -> InterviewCompletedWebhookResponse:
    session = interview_completion_service.handle_interview_completed(db, payload)
    return InterviewCompletedWebhookResponse(
        received=True, interview_session_id=str(session.id), status=session.status.value
    )
