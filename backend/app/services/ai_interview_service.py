"""
Adapter to the EXISTING AI Interview FastAPI service.

This platform never reimplements interview conversation logic — it only
needs to create a session, know its status, and later fetch a result. The
exact request/response shape of the real AI service's API will be
configured separately; this module intentionally does NOT invent
assumptions about it beyond a plausible REST shape, so that shape can be
adjusted here (and only here) once the real contract is known. No caller
outside this module should know or care about the AI service's URL paths.

Dev/stub mode: if AI_INTERVIEW_SERVICE_URL is not configured, every method
returns a synthetic-but-realistic result instead of making a network call.
This is what lets Phase 6 (session creation, access control, status
tracking) be built and tested end-to-end before the real AI service
endpoint is wired up — exactly the same graceful-degradation pattern used
for Cloudinary and the console email provider.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.core.exceptions import AIServiceError

logger = logging.getLogger(__name__)


@dataclass
class AISessionHandle:
    ai_session_id: str
    interview_url: str | None


@dataclass
class AISessionStatus:
    ai_session_id: str
    status: str  # raw status string as reported by the AI service
    is_completed: bool


def _is_configured() -> bool:
    return bool(settings.AI_INTERVIEW_SERVICE_URL)


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=settings.AI_INTERVIEW_SERVICE_URL,
        headers={"Authorization": f"Bearer {settings.AI_INTERVIEW_SERVICE_API_KEY}"},
        timeout=settings.AI_INTERVIEW_SERVICE_TIMEOUT_SECONDS,
    )


def create_session(*, employee_id: uuid.UUID, campaign_id: uuid.UUID, interview_session_id: uuid.UUID) -> AISessionHandle:
    """
    Create (or resume) a session with the AI interview service for this
    platform interview_session. Called at most once per InterviewSession
    (see interview_service.start_interview) — subsequent starts resume the
    existing ai_session_id instead of calling this again.
    """
    if not _is_configured():
        stub_id = f"stub-{uuid.uuid4()}"
        logger.warning(
            "AI_INTERVIEW_SERVICE_URL is not configured; returning a stub AI session (%s). "
            "Configure it to integrate with the real AI interview service.",
            stub_id,
        )
        return AISessionHandle(ai_session_id=stub_id, interview_url=f"about:blank#stub-session-{stub_id}")

    try:
        with _client() as client:
            response = client.post(
                "/sessions",
                json={
                    "external_reference_id": str(interview_session_id),
                    "employee_id": str(employee_id),
                    "campaign_id": str(campaign_id),
                },
            )
            response.raise_for_status()
            data = response.json()
            return AISessionHandle(ai_session_id=data["session_id"], interview_url=data.get("interview_url"))
    except Exception as exc:  # pragma: no cover - network dependent
        logger.exception("Failed to create AI interview session")
        raise AIServiceError("Could not start the interview service. Please try again shortly.") from exc


def get_session_status(ai_session_id: str) -> AISessionStatus:
    if not _is_configured() or ai_session_id.startswith("stub-"):
        # Stub sessions never self-report completion — completion in dev
        # comes only through the (Phase 7) completion webhook being called
        # manually/by a test, matching how the real webhook will behave.
        return AISessionStatus(ai_session_id=ai_session_id, status="IN_PROGRESS", is_completed=False)

    try:
        with _client() as client:
            response = client.get(f"/sessions/{ai_session_id}")
            response.raise_for_status()
            data = response.json()
            return AISessionStatus(
                ai_session_id=ai_session_id,
                status=data.get("status", "UNKNOWN"),
                is_completed=data.get("status") == "COMPLETED",
            )
    except Exception as exc:  # pragma: no cover - network dependent
        logger.exception("Failed to fetch AI interview session status")
        raise AIServiceError("Could not check interview status. Please try again shortly.") from exc


def get_result(ai_session_id: str) -> dict:
    """Fetch the final interview result payload. Used by the Phase 7 completion flow."""
    if not _is_configured() or ai_session_id.startswith("stub-"):
        return {"transcript": None, "summary": None, "note": "stub result — AI service not configured"}

    try:
        with _client() as client:
            response = client.get(f"/sessions/{ai_session_id}/result")
            response.raise_for_status()
            return response.json()
    except Exception as exc:  # pragma: no cover - network dependent
        logger.exception("Failed to fetch AI interview result")
        raise AIServiceError("Could not retrieve the interview result. Please try again shortly.") from exc
