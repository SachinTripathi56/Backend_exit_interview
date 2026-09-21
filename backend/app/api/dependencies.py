"""
Shared FastAPI dependencies.

This module is the single place where the request pipeline described in the
spec is implemented:

    1. Verify Clerk token.
    2. Get Clerk user ID.
    3. Get internal user.
    4. Get company.
    5. Check role.
    6. (endpoint) Execute company-scoped query.
    7. (endpoint) Return response.

Every protected endpoint should depend on `get_current_user` (or one of the
role-specific wrappers below) rather than reading headers itself. This keeps
authorization logic in exactly one place instead of scattered across
endpoints.
"""
from __future__ import annotations

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import verify_clerk_token
from app.db.database import get_db
from app.models.user import User, UserRole


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UnauthorizedError("Missing or malformed Authorization header.")
    return authorization.split(" ", 1)[1].strip()


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    """
    Resolve the fully-authenticated + authorized internal user for this
    request. This is the dependency almost every endpoint should use.

    Raises 401 if the token is missing/invalid, or if no internal user
    record exists yet for this Clerk identity (the frontend should call
    an onboarding/provisioning flow in that case — see auth.py).
    """
    token = _extract_bearer_token(authorization)
    claims = verify_clerk_token(token)

    user = db.query(User).filter(User.clerk_user_id == claims.clerk_user_id).first()
    if user is None:
        raise UnauthorizedError(
            "No account is provisioned for this identity yet. Please complete onboarding."
        )
    return user


def require_roles(*allowed_roles: UserRole):
    """
    Dependency factory for endpoint-level role checks.

    Usage:
        @router.get(..., dependencies=[Depends(require_roles(UserRole.HR_ADMIN, UserRole.HR_USER))])
    or
        current_user: User = Depends(require_roles(UserRole.HR_ADMIN))
    """

    def _dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise ForbiddenError("Your role does not permit this action.")
        return current_user

    return _dependency


def require_hr(current_user: User = Depends(get_current_user)) -> User:
    """Any HR role (HR_ADMIN or HR_USER)."""
    if not current_user.role.is_hr:
        raise ForbiddenError("This endpoint is restricted to HR users.")
    return current_user


def require_hr_admin(current_user: User = Depends(get_current_user)) -> User:
    """HR_ADMIN only — for destructive/administrative actions."""
    if current_user.role != UserRole.HR_ADMIN:
        raise ForbiddenError("This endpoint is restricted to HR administrators.")
    return current_user


def require_employee(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.EMPLOYEE:
        raise ForbiddenError("This endpoint is restricted to employee accounts.")
    return current_user


class TenantContext:
    """
    Convenience bundle passed into services/repositories so tenant scoping
    is explicit and impossible to forget: every company-scoped query should
    take a TenantContext (or at minimum a company_id) rather than trusting
    any company_id that arrives in a request body or query string.
    """

    def __init__(self, user: User):
        self.user = user
        self.company_id = user.company_id
        self.role = user.role


def get_tenant_context(current_user: User = Depends(get_current_user)) -> TenantContext:
    return TenantContext(current_user)


def verify_ai_webhook(x_webhook_secret: str | None = Header(default=None, alias="X-Webhook-Secret")) -> None:
    """
    Authenticates inbound calls FROM the AI Interview service (never from
    the frontend) using a shared secret, never a Clerk token — the AI
    service has no Clerk identity of its own. See
    app.core.security.verify_internal_webhook_secret.
    """
    from app.core.security import verify_internal_webhook_secret

    verify_internal_webhook_secret(x_webhook_secret)
