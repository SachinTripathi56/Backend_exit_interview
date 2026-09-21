"""Pydantic schema for GET /api/v1/hr/dashboard."""
from __future__ import annotations

from pydantic import BaseModel, Field


class HRDashboardResponse(BaseModel):
    total_employees: int
    total_interviews: int
    completed_interviews: int
    pending_interviews: int
    expired_interviews: int
    completion_rate: float = Field(description="Percentage 0-100.")

    # Extra fields beyond the spec's example are allowed by the contract
    # ("Allow additional fields for charts/analytics."). active_campaigns
    # is wired up for real once campaigns land in Phase 4; until then it's
    # always 0 rather than omitted, so the frontend card doesn't need a
    # conditional.
    active_campaigns: int = 0
