"""HR analytics endpoint. Every value returned is an aggregate — see
app/services/analytics_service.py for the data-minimization rules applied."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import TenantContext, get_tenant_context, require_hr
from app.db.database import get_db
from app.schemas.analytics import AnalyticsResponse
from app.services import analytics_service

router = APIRouter(prefix="/hr", tags=["analytics"], dependencies=[Depends(require_hr)])


@router.get(
    "/analytics",
    response_model=AnalyticsResponse,
    summary="Get aggregated exit interview analytics for the authenticated user's company",
)
def get_analytics(
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
) -> AnalyticsResponse:
    return analytics_service.get_hr_analytics(db, tenant.company_id)
