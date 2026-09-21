"""Report generation, listing, and download endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.dependencies import TenantContext, get_tenant_context, require_hr
from app.db.database import get_db
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.report import ReportGenerateRequest, ReportResponse
from app.services import report_service

router = APIRouter(prefix="/hr/reports", tags=["reports"], dependencies=[Depends(require_hr)])


@router.get("", response_model=PaginatedResponse[ReportResponse], summary="List previously generated reports")
def list_reports(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
) -> PaginatedResponse[ReportResponse]:
    items, total = report_service.list_reports(db, tenant.company_id, page=page, limit=limit)
    return PaginatedResponse(items=[ReportResponse.model_validate(r) for r in items], page=page, limit=limit, total=total)


@router.post(
    "/generate",
    response_model=ReportResponse,
    summary="Generate a new report (PDF or Excel)",
    description=(
        "Synchronous: the report is generated and (best-effort) archived before this "
        "call returns. Omit campaign_id for a company-wide report; provide it to scope "
        "the report to a single campaign. status=FAILED with error_message if generation "
        "failed — this is a 200 response, not an HTTP error, since the request itself "
        "was valid."
    ),
)
def generate_report(
    payload: ReportGenerateRequest,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
    current_user: User = Depends(require_hr),
) -> ReportResponse:
    report = report_service.generate_report(db, tenant.company_id, current_user.id, payload)
    return ReportResponse.model_validate(report)


@router.get("/{report_id}", response_model=ReportResponse, summary="Get report metadata")
def get_report(
    report_id: uuid.UUID,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
) -> ReportResponse:
    report = report_service.get_report_or_404(db, tenant.company_id, report_id)
    return ReportResponse.model_validate(report)


@router.get(
    "/{report_id}/download",
    summary="Download the generated report file",
    response_class=Response,
)
def download_report(
    report_id: uuid.UUID,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
) -> Response:
    file_bytes, content_type, file_name = report_service.get_download_content(db, tenant.company_id, report_id)
    return Response(
        content=file_bytes,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )
