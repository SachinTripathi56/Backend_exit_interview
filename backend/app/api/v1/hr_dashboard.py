"""HR dashboard metrics endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import TenantContext, get_tenant_context, require_hr
from app.db.database import get_db
from app.schemas.dashboard import HRDashboardResponse
from app.services import dashboard_service

router = APIRouter(prefix="/hr", tags=["hr-dashboard"], dependencies=[Depends(require_hr)])


@router.get(
    "/dashboard",
    response_model=HRDashboardResponse,
    summary="Get HR dashboard metrics for the authenticated user's company",
)
def get_dashboard(
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
) -> HRDashboardResponse:
    return dashboard_service.get_hr_dashboard(db, tenant.company_id)
