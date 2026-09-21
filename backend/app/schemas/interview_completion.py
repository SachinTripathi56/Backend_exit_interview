"""
Pydantic schemas for POST /api/v1/internal/ai/interview-completed.

This is OUR side of the contract with the existing AI Interview service —
the exact real payload shape will be finalized once that service's API is
configured, but this defines a reasonable, self-contained shape in the
meantime so Phase 7 can be built and tested end-to-end. Only this file (and
the service function that consumes it) needs to change if the real
contract differs.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class InterviewResultPayload(BaseModel):
    transcript: str | None = None
    summary: str | None = None
    satisfaction_score: float | None = Field(default=None, ge=0, le=10)
    exit_reasons: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class InterviewCompletedWebhookRequest(BaseModel):
    ai_session_id: str
    status: Literal["COMPLETED", "ERROR"]
    completed_at: datetime | None = None
    result: InterviewResultPayload | None = None
    raw: dict[str, Any] = Field(default_factory=dict, description="Full raw payload, stored as-is for audit.")


class InterviewCompletedWebhookResponse(BaseModel):
    received: bool
    interview_session_id: str
    status: str
