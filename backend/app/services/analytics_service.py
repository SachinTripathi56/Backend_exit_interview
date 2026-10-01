"""
HR analytics aggregation.

Data minimization rule (spec section 26): `key_comments` only ever contains
a small number of short summary snippets, and ONLY once there are enough
completed interviews in the company that no single comment could be
attributed to one departing employee. Below that threshold the list is
empty rather than showing "the one comment we have" — which would be
trivially attributable in a small company/department.
"""
from __future__ import annotations

import uuid
from collections import Counter

from sqlalchemy.orm import Session

from app.repositories import analytics_repository as repo
from app.schemas.analytics import (
    AnalyticsResponse,
    DepartmentParticipation,
    DepartmentSatisfaction,
    FrequencyItem,
)

_MIN_RESULTS_FOR_KEY_COMMENTS = 3
_MAX_KEY_COMMENTS = 5
_MAX_FREQUENCY_ITEMS = 10


def _top_frequencies(items: list[str], limit: int = _MAX_FREQUENCY_ITEMS) -> list[FrequencyItem]:
    counter = Counter(i.strip() for i in items if i and i.strip())
    return [FrequencyItem(label=label, count=count) for label, count in counter.most_common(limit)]


def get_hr_analytics(db: Session, company_id: uuid.UUID, campaign_id: uuid.UUID | None = None) -> AnalyticsResponse:
    total_assigned, total_completed = repo.get_total_assignment_counts(db, company_id, campaign_id)
    completion_rate = round((total_completed / total_assigned) * 100, 1) if total_assigned > 0 else 0.0

    dept_rows = repo.get_assignment_counts_by_department(db, company_id, campaign_id)
    department_participation = [
        DepartmentParticipation(
            department=dept,
            assigned_count=assigned,
            completed_count=completed,
            participation_rate=round((completed / assigned) * 100, 1) if assigned > 0 else 0.0,
        )
        for dept, assigned, completed in dept_rows
    ]

    results_with_dept = repo.get_results_with_department(db, company_id, campaign_id)

    all_scores = [r.satisfaction_score for r, _ in results_with_dept if r.satisfaction_score is not None]
    overall_satisfaction = round(sum(all_scores) / len(all_scores), 2) if all_scores else None

    scores_by_dept: dict[str, list[float]] = {}
    for result, dept in results_with_dept:
        if result.satisfaction_score is None:
            continue
        key = dept or "Unspecified"
        scores_by_dept.setdefault(key, []).append(result.satisfaction_score)

    department_satisfaction = [
        DepartmentSatisfaction(
            department=dept,
            average_satisfaction=round(sum(scores) / len(scores), 2),
            response_count=len(scores),
        )
        for dept, scores in scores_by_dept.items()
    ]

    all_exit_reasons = [reason for r, _ in results_with_dept for reason in (r.exit_reasons or [])]
    all_themes = [theme for r, _ in results_with_dept for theme in (r.themes or [])]
    all_recommendations = [rec for r, _ in results_with_dept for rec in (r.recommendations or [])]

    key_comments: list[str] = []
    if len(results_with_dept) >= _MIN_RESULTS_FOR_KEY_COMMENTS:
        summaries = [r.summary for r, _ in results_with_dept if r.summary]
        key_comments = summaries[:_MAX_KEY_COMMENTS]

    return AnalyticsResponse(
        overall_satisfaction=overall_satisfaction,
        completion_rate=completion_rate,
        total_assigned=total_assigned,
        total_completed=total_completed,
        department_participation=department_participation,
        department_satisfaction=department_satisfaction,
        common_exit_reasons=_top_frequencies(all_exit_reasons),
        common_themes=_top_frequencies(all_themes),
        recommendations=_top_frequencies(all_recommendations),
        key_comments=key_comments,
    )
