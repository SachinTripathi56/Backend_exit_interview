"""
Report generation orchestration.

Design choice, documented once here: the Report row is metadata (who
requested it, when, in what format, success/failure) — the file bytes
themselves are regenerated deterministically from current aggregate data
at download time rather than persisted as a DB blob. Generation also
best-effort archives a copy to Cloudinary (private/authenticated) purely
as an audit trail, exactly like the Phase 3 import-file archival pattern;
a Cloudinary outage never blocks generating or downloading a report.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationAppError
from app.models.report import Report, ReportFormat, ReportStatus
from app.repositories import report_repository as repo
from app.schemas.report import ReportGenerateRequest
from app.services import analytics_service, campaign_service, cloudinary_service, report_builder
from app.services import audit_service
from app.services.audit_service import AuditAction

logger = logging.getLogger(__name__)

_CONTENT_TYPES = {
    ReportFormat.PDF: "application/pdf",
    ReportFormat.EXCEL: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
_EXTENSIONS = {ReportFormat.PDF: "pdf", ReportFormat.EXCEL: "xlsx"}


def _build_report_bytes(db: Session, company_id: uuid.UUID, campaign_id: uuid.UUID | None, fmt: ReportFormat) -> bytes:
    analytics = analytics_service.get_hr_analytics(db, company_id, campaign_id)

    campaign_meta = None
    scope_label = "Company-wide"
    if campaign_id is not None:
        campaign = campaign_service.get_campaign_or_404(db, company_id, campaign_id)
        campaign_meta = {
            "name": campaign.name,
            "status": campaign.status.value,
            "start_at": campaign.start_at.strftime("%Y-%m-%d"),
            "end_at": campaign.end_at.strftime("%Y-%m-%d"),
        }
        scope_label = campaign.name

    generated_at = datetime.now(timezone.utc)
    builder = report_builder.build_pdf_report if fmt == ReportFormat.PDF else report_builder.build_excel_report
    return builder(scope_label=scope_label, generated_at=generated_at, analytics=analytics, campaign_meta=campaign_meta)


def generate_report(
    db: Session, company_id: uuid.UUID, requested_by: uuid.UUID, payload: ReportGenerateRequest
) -> Report:
    if payload.campaign_id is not None:
        # Raises NotFoundError (404) if it doesn't belong to this company —
        # exactly the tenant-isolation behavior every other resource has.
        campaign_service.get_campaign_or_404(db, company_id, payload.campaign_id)

    now = datetime.now(timezone.utc)
    ext = _EXTENSIONS[payload.format]
    scope_slug = str(payload.campaign_id) if payload.campaign_id else "company-wide"
    file_name = f"exit-interview-report-{scope_slug}-{now.strftime('%Y%m%d%H%M%S')}.{ext}"

    report = Report(
        id=uuid.uuid4(),
        company_id=company_id,
        campaign_id=payload.campaign_id,
        requested_by=requested_by,
        format=payload.format,
        status=ReportStatus.FAILED,  # optimistic default flipped to COMPLETED below on success
        file_name=file_name,
    )

    try:
        file_bytes = _build_report_bytes(db, company_id, payload.campaign_id, payload.format)
    except Exception as exc:  # pragma: no cover - defensive; builder failures shouldn't normally happen
        logger.exception("Report generation failed for company_id=%s", company_id)
        report.error_message = str(exc)
        db.add(report)
        db.flush()
        return report

    report.status = ReportStatus.COMPLETED
    report.generated_at = now
    db.add(report)
    db.flush()

    try:
        public_id = cloudinary_service.upload_file(
            file_bytes, folder=f"reports/{company_id}", public_id=str(report.id)
        )
        if public_id:
            report.cloudinary_public_id = public_id
            db.add(report)
            db.flush()
    except Exception:  # pragma: no cover - network/service dependent
        logger.exception("Failed to archive report %s to Cloudinary", report.id)

    audit_service.log(
        db,
        company_id=company_id,
        user_id=requested_by,
        action=AuditAction.REPORT_GENERATED,
        resource_type="report",
        resource_id=report.id,
        extra_data={"format": report.format.value, "campaign_id": str(payload.campaign_id) if payload.campaign_id else None},
    )
    return report


def get_report_or_404(db: Session, company_id: uuid.UUID, report_id: uuid.UUID) -> Report:
    report = repo.get_by_id(db, company_id, report_id)
    if report is None:
        raise NotFoundError("Report not found.")
    return report


def list_reports(db: Session, company_id: uuid.UUID, *, page: int, limit: int) -> tuple[list[Report], int]:
    return repo.list_paginated(db, company_id, page=page, limit=limit)


def get_download_content(db: Session, company_id: uuid.UUID, report_id: uuid.UUID) -> tuple[bytes, str, str]:
    """Returns (file_bytes, content_type, file_name). Re-derives bytes deterministically — see module docstring."""
    report = get_report_or_404(db, company_id, report_id)
    if report.status != ReportStatus.COMPLETED:
        raise ValidationAppError(f"This report failed to generate: {report.error_message or 'unknown error'}")

    file_bytes = _build_report_bytes(db, company_id, report.campaign_id, report.format)
    return file_bytes, _CONTENT_TYPES[report.format], report.file_name
