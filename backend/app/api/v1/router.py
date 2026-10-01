"""
Aggregates all /api/v1 routers into one.

As each phase is implemented, its router is included here. This is the only
file that needs to change when a new resource module is added.
"""
from fastapi import APIRouter

from app.api.v1 import (
    analytics,
    auth,
    campaigns,
    employee,
    employee_imports,
    employees,
    hr_dashboard,
    reports,
    users,
)
from app.api.v1.internal import ai_callbacks

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(hr_dashboard.router)
api_router.include_router(employees.router)
api_router.include_router(employee_imports.router)
api_router.include_router(campaigns.router)
api_router.include_router(employee.router)
api_router.include_router(analytics.router)
api_router.include_router(reports.router)
api_router.include_router(ai_callbacks.router)

# Phase 10 adds audit logging and security hardening across existing
# routers rather than new endpoints — see app/services/audit_service.py.
