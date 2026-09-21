"""
Invitation / reminder orchestration, and employee-access token redemption.

Two audiences use this module:
  - HR, via POST /hr/campaigns/{id}/invitations and /reminders
  - The employee's browser, via POST /auth/employee-access (token redemption)
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import CampaignExpiredError, ConflictError, NotFoundError, ValidationAppError
from app.models.campaign import CampaignStatus
from app.models.campaign_employee import CampaignEmployee, CampaignInterviewStatus, InvitationStatus
from app.models.email_log import EmailLog, EmailStatus, EmailType
from app.models.employee import Employee, EmployeeStatus
from app.models.employee_invitation import EmployeeInvitation, InvitationTokenStatus
from app.models.user import User, UserRole
from app.repositories import campaign_repository as campaign_repo
from app.repositories import employee_invitation_repository as invitation_repo
from app.schemas.invitation import BulkEmailResponse, BulkEmailResultItem
from app.services import campaign_service, email_service
from app.services import audit_service
from app.services.audit_service import AuditAction


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _build_access_url(raw_token: str) -> str:
    return f"{settings.FRONTEND_URL}{settings.EMPLOYEE_ACCESS_URL_PATH}?token={raw_token}"


def _issue_invitation_token(db: Session, company_id: uuid.UUID, employee_id: uuid.UUID, campaign_id: uuid.UUID) -> str:
    # Only one valid (PENDING) token per employee+campaign at a time.
    invitation_repo.revoke_pending_for_employee_campaign(db, employee_id, campaign_id)

    raw_token = secrets.token_urlsafe(32)
    invitation = EmployeeInvitation(
        id=uuid.uuid4(),
        company_id=company_id,
        employee_id=employee_id,
        campaign_id=campaign_id,
        token_hash=_hash_token(raw_token),
        status=InvitationTokenStatus.PENDING,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.INVITATION_TOKEN_EXPIRY_DAYS),
    )
    db.add(invitation)
    db.flush()
    return raw_token


def _log_email(
    db: Session,
    company_id: uuid.UUID,
    *,
    campaign_id: uuid.UUID | None,
    employee_id: uuid.UUID | None,
    email_type: EmailType,
    recipient_email: str,
    subject: str,
    result,
) -> None:
    db.add(
        EmailLog(
            id=uuid.uuid4(),
            company_id=company_id,
            campaign_id=campaign_id,
            employee_id=employee_id,
            email_type=email_type,
            recipient_email=recipient_email,
            subject=subject,
            status=EmailStatus.SENT if result.success else EmailStatus.FAILED,
            provider_response=result.provider_response,
        )
    )


def _require_active_or_scheduled_campaign(campaign) -> None:
    if campaign.status in (CampaignStatus.EXPIRED, CampaignStatus.CANCELLED, CampaignStatus.COMPLETED):
        raise CampaignExpiredError(f"Cannot email employees: campaign is {campaign.status.value}.")


def send_invitations(
    db: Session,
    company_id: uuid.UUID,
    campaign_id: uuid.UUID,
    employee_ids: list[uuid.UUID] | None,
    actor_user_id: uuid.UUID | None = None,
) -> BulkEmailResponse:
    campaign = campaign_service.get_campaign_or_404(db, company_id, campaign_id)
    _require_active_or_scheduled_campaign(campaign)

    if employee_ids is not None:
        targets = [a for a in campaign.assignments if a.employee_id in set(employee_ids)]
        missing = set(employee_ids) - {a.employee_id for a in targets}
        if missing:
            raise ValidationAppError(
                "employee_ids not assigned to this campaign: " + ", ".join(str(m) for m in missing)
            )
    else:
        targets = [a for a in campaign.assignments if a.invitation_status != InvitationStatus.SENT]

    results: list[BulkEmailResultItem] = []
    sent_count = failed_count = skipped_count = 0

    for assignment in targets:
        employee = db.get(Employee, assignment.employee_id)
        if employee is None or employee.status == EmployeeStatus.DISABLED:
            results.append(
                BulkEmailResultItem(employee_id=assignment.employee_id, status="SKIPPED", message="Employee is disabled or missing.")
            )
            skipped_count += 1
            continue

        raw_token = _issue_invitation_token(db, company_id, employee.id, campaign.id)
        access_url = _build_access_url(raw_token)
        result = email_service.send_invitation(employee.email, employee.name, campaign.name, access_url)

        _log_email(
            db,
            company_id,
            campaign_id=campaign.id,
            employee_id=employee.id,
            email_type=EmailType.INVITATION,
            recipient_email=employee.email,
            subject=f"You're invited: {campaign.name} exit interview",
            result=result,
        )

        assignment.invitation_status = InvitationStatus.SENT if result.success else InvitationStatus.FAILED
        assignment.invited_at = datetime.now(timezone.utc)
        db.add(assignment)

        if result.success and employee.status == EmployeeStatus.ACTIVE:
            employee.status = EmployeeStatus.INVITED
            db.add(employee)

        if result.success:
            sent_count += 1
            results.append(BulkEmailResultItem(employee_id=employee.id, status="SENT"))
        else:
            failed_count += 1
            results.append(BulkEmailResultItem(employee_id=employee.id, status="FAILED", message=result.provider_response))

    db.flush()
    audit_service.log(
        db,
        company_id=company_id,
        user_id=actor_user_id,
        action=AuditAction.CAMPAIGN_INVITATIONS_SENT,
        resource_type="campaign",
        resource_id=campaign_id,
        extra_data={"sent_count": sent_count, "failed_count": failed_count},
    )
    return BulkEmailResponse(sent_count=sent_count, failed_count=failed_count, skipped_count=skipped_count, results=results)


def send_reminders(
    db: Session,
    company_id: uuid.UUID,
    campaign_id: uuid.UUID,
    employee_ids: list[uuid.UUID] | None,
    actor_user_id: uuid.UUID | None = None,
) -> BulkEmailResponse:
    campaign = campaign_service.get_campaign_or_404(db, company_id, campaign_id)
    _require_active_or_scheduled_campaign(campaign)

    def _eligible(a: CampaignEmployee) -> bool:
        return (
            a.invitation_status == InvitationStatus.SENT
            and a.interview_status in (CampaignInterviewStatus.NOT_STARTED, CampaignInterviewStatus.IN_PROGRESS)
        )

    if employee_ids is not None:
        candidates = [a for a in campaign.assignments if a.employee_id in set(employee_ids)]
    else:
        candidates = list(campaign.assignments)

    results: list[BulkEmailResultItem] = []
    sent_count = failed_count = skipped_count = 0

    for assignment in candidates:
        if not _eligible(assignment):
            results.append(
                BulkEmailResultItem(
                    employee_id=assignment.employee_id, status="SKIPPED", message="Not eligible for a reminder."
                )
            )
            skipped_count += 1
            continue

        employee = db.get(Employee, assignment.employee_id)
        if employee is None:
            skipped_count += 1
            continue

        raw_token = _issue_invitation_token(db, company_id, employee.id, campaign.id)
        access_url = _build_access_url(raw_token)
        result = email_service.send_reminder(
            employee.email, employee.name, campaign.name, access_url, campaign.end_at.isoformat()
        )

        _log_email(
            db,
            company_id,
            campaign_id=campaign.id,
            employee_id=employee.id,
            email_type=EmailType.REMINDER,
            recipient_email=employee.email,
            subject=f"Reminder: complete your {campaign.name} exit interview",
            result=result,
        )

        assignment.last_reminded_at = datetime.now(timezone.utc)
        db.add(assignment)

        if result.success:
            sent_count += 1
            results.append(BulkEmailResultItem(employee_id=employee.id, status="SENT"))
        else:
            failed_count += 1
            results.append(BulkEmailResultItem(employee_id=employee.id, status="FAILED", message=result.provider_response))

    db.flush()
    audit_service.log(
        db,
        company_id=company_id,
        user_id=actor_user_id,
        action=AuditAction.CAMPAIGN_REMINDERS_SENT,
        resource_type="campaign",
        resource_id=campaign_id,
        extra_data={"sent_count": sent_count, "failed_count": failed_count},
    )
    return BulkEmailResponse(sent_count=sent_count, failed_count=failed_count, skipped_count=skipped_count, results=results)


def redeem_employee_access_token(db: Session, clerk_user_id: str, raw_token: str) -> User:
    """
    Called from POST /api/v1/auth/employee-access after the employee has
    already authenticated with Clerk client-side. Links that Clerk identity
    to the specific Employee record the token was issued for.
    """
    existing_user = db.query(User).filter(User.clerk_user_id == clerk_user_id).first()
    if existing_user is not None:
        raise ConflictError("An account already exists for this identity.")

    invitation = invitation_repo.get_pending_by_token_hash(db, _hash_token(raw_token))
    if invitation is None:
        raise NotFoundError("This invitation link is invalid or has already been used.")

    if invitation.expires_at < datetime.now(timezone.utc):
        invitation.status = InvitationTokenStatus.EXPIRED
        db.add(invitation)
        db.flush()
        raise NotFoundError("This invitation link has expired. Please ask HR to resend it.")

    employee = db.get(Employee, invitation.employee_id)
    if employee is None:
        raise NotFoundError("The employee record for this invitation no longer exists.")

    user = User(
        id=uuid.uuid4(),
        clerk_user_id=clerk_user_id,
        company_id=invitation.company_id,
        role=UserRole.EMPLOYEE,
        name=employee.name,
        email=employee.email,
        employee_id=employee.id,
    )
    db.add(user)

    invitation.status = InvitationTokenStatus.ACCEPTED
    invitation.accepted_at = datetime.now(timezone.utc)
    db.add(invitation)

    db.flush()
    audit_service.log(
        db,
        company_id=invitation.company_id,
        user_id=user.id,
        action=AuditAction.EMPLOYEE_ACCESS_REDEEMED,
        resource_type="employee_invitation",
        resource_id=invitation.id,
        extra_data={"employee_id": str(employee.id)},
    )
    return user
