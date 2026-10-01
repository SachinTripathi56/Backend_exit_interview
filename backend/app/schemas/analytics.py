"""
Pydantic schemas for GET /api/v1/hr/analytics.

Per spec section 26 (Data Privacy): every field here is an aggregate
(count, average, or frequency-ranked list) — nothing here is traceable to
a single employee's individual response.
"""
from __future__ import annotations

from pydantic import BaseModel


class DepartmentParticipation(BaseModel):
    department: str
    assigned_count: int
    completed_count: int
    participation_rate: float  # percentage 0-100


class DepartmentSatisfaction(BaseModel):
    department: str
    average_satisfaction: float | None
    response_count: int


class FrequencyItem(BaseModel):
    label: str
    count: int


class AnalyticsResponse(BaseModel):
    overall_satisfaction: float | None
    completion_rate: float  # percentage 0-100
    total_assigned: int
    total_completed: int

    department_participation: list[DepartmentParticipation]
    department_satisfaction: list[DepartmentSatisfaction]

    common_exit_reasons: list[FrequencyItem]
    common_themes: list[FrequencyItem]
    recommendations: list[FrequencyItem]

    # Only ever a handful of short, non-attributable summary snippets, and
    # only surfaced at all once there's enough volume that no single
    # comment is individually identifiable (see analytics_service.py).
    key_comments: list[str]
