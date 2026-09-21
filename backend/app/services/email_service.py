"""
Email sending abstraction.

Business logic (invitation_service, and later the completion webhook) calls
only the conceptual methods below and never touches a provider SDK
directly, so swapping EMAIL_PROVIDER later requires no changes outside this
file.

The default provider, "console", just logs the email — this is what lets
local development and the test suite exercise the full invitation/reminder
flow without needing a real Resend/SendGrid/SES account.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class EmailSendResult:
    success: bool
    provider_response: str


def _send_raw(to_email: str, subject: str, body: str) -> EmailSendResult:
    provider = settings.EMAIL_PROVIDER

    if provider == "console":
        logger.info("[console email] to=%s subject=%s\n%s", to_email, subject, body)
        return EmailSendResult(success=True, provider_response="console:logged")

    if provider == "resend":
        return _send_via_resend(to_email, subject, body)
    if provider == "sendgrid":
        return _send_via_sendgrid(to_email, subject, body)
    if provider == "ses":
        return _send_via_ses(to_email, subject, body)

    logger.warning("Unknown EMAIL_PROVIDER=%s; falling back to console logging.", provider)
    logger.info("[console email] to=%s subject=%s\n%s", to_email, subject, body)
    return EmailSendResult(success=True, provider_response="console:fallback")


def _send_via_resend(to_email: str, subject: str, body: str) -> EmailSendResult:
    import httpx

    try:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.EMAIL_API_KEY}"},
            json={
                "from": f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM_ADDRESS}>",
                "to": [to_email],
                "subject": subject,
                "html": body,
            },
            timeout=10.0,
        )
        response.raise_for_status()
        return EmailSendResult(success=True, provider_response=response.text)
    except Exception as exc:  # pragma: no cover - network dependent
        logger.exception("Resend send failed for %s", to_email)
        return EmailSendResult(success=False, provider_response=str(exc))


def _send_via_sendgrid(to_email: str, subject: str, body: str) -> EmailSendResult:
    import httpx

    try:
        response = httpx.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={"Authorization": f"Bearer {settings.EMAIL_API_KEY}"},
            json={
                "personalizations": [{"to": [{"email": to_email}]}],
                "from": {"email": settings.EMAIL_FROM_ADDRESS, "name": settings.EMAIL_FROM_NAME},
                "subject": subject,
                "content": [{"type": "text/html", "value": body}],
            },
            timeout=10.0,
        )
        response.raise_for_status()
        return EmailSendResult(success=True, provider_response=f"status={response.status_code}")
    except Exception as exc:  # pragma: no cover - network dependent
        logger.exception("SendGrid send failed for %s", to_email)
        return EmailSendResult(success=False, provider_response=str(exc))


def _send_via_ses(to_email: str, subject: str, body: str) -> EmailSendResult:
    try:
        import boto3

        client = boto3.client(
            "ses",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
        )
        response = client.send_email(
            Source=f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM_ADDRESS}>",
            Destination={"ToAddresses": [to_email]},
            Message={"Subject": {"Data": subject}, "Body": {"Html": {"Data": body}}},
        )
        return EmailSendResult(success=True, provider_response=str(response.get("MessageId", "")))
    except Exception as exc:  # pragma: no cover - network dependent
        logger.exception("SES send failed for %s", to_email)
        return EmailSendResult(success=False, provider_response=str(exc))


# ---------------------------------------------------------------------
# Conceptual methods used by business logic
# ---------------------------------------------------------------------
def send_invitation(to_email: str, employee_name: str, campaign_name: str, access_url: str) -> EmailSendResult:
    subject = f"You're invited: {campaign_name} exit interview"
    body = (
        f"<p>Hi {employee_name},</p>"
        f"<p>You've been invited to complete your exit interview for <b>{campaign_name}</b>.</p>"
        f'<p><a href="{access_url}">Click here to begin</a>.</p>'
        f"<p>This link is unique to you — please don't share it.</p>"
    )
    return _send_raw(to_email, subject, body)


def send_reminder(to_email: str, employee_name: str, campaign_name: str, access_url: str, end_at: str) -> EmailSendResult:
    subject = f"Reminder: complete your {campaign_name} exit interview"
    body = (
        f"<p>Hi {employee_name},</p>"
        f"<p>This is a reminder that your exit interview for <b>{campaign_name}</b> "
        f"is still pending, and closes on {end_at}.</p>"
        f'<p><a href="{access_url}">Click here to complete it</a>.</p>'
    )
    return _send_raw(to_email, subject, body)


def send_completion_confirmation(to_email: str, employee_name: str, campaign_name: str) -> EmailSendResult:
    subject = f"Thank you for completing your {campaign_name} exit interview"
    body = f"<p>Hi {employee_name},</p><p>Thanks for completing your exit interview. We appreciate your feedback.</p>"
    return _send_raw(to_email, subject, body)


def send_hr_notification(to_email: str, subject: str, message: str) -> EmailSendResult:
    return _send_raw(to_email, subject, f"<p>{message}</p>")
