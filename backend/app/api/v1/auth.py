"""
Auth / provisioning endpoints.

Clerk itself handles login, signup UI, and session issuance on the frontend.
This router only covers the one thing the platform backend must do: bridge
a verified Clerk identity into our own tenant/role model.

Employee provisioning (an employee's first login) is handled separately in
Phase 5 via the invitation flow — employees are created by HR (or bulk
import) ahead of time, so there is no public employee self-registration
endpoint.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.core.security import verify_clerk_token
from app.db.database import get_db
from app.schemas.company import CompanyRegisterRequest
from app.schemas.invitation import EmployeeAccessRequest
from app.schemas.user import CurrentUserResponse
from app.services.auth_service import register_company_and_admin
from app.services.invitation_service import redeem_employee_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register-company",
    response_model=CurrentUserResponse,
    summary="Register a new company and its first HR admin",
    description=(
        "Called once, immediately after a user creates a Clerk account via the "
        "frontend's /register flow for a brand-new organization. Verifies the "
        "supplied Clerk token, then creates a Company and an HR_ADMIN user "
        "linked to that Clerk identity. Returns 409 if this identity is "
        "already provisioned."
    ),
)
def register_company(
    payload: CompanyRegisterRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> CurrentUserResponse:
    from app.api.dependencies import _extract_bearer_token  # local import avoids circularity at module load

    token = _extract_bearer_token(authorization)
    claims = verify_clerk_token(token)

    user = register_company_and_admin(db, claims.clerk_user_id, payload)
    return CurrentUserResponse.model_validate(user)


@router.post(
    "/employee-access",
    response_model=CurrentUserResponse,
    summary="Redeem an invitation token to link a Clerk identity to an employee record",
    description=(
        "Called after an employee authenticates with Clerk client-side, using the "
        "token from their invitation/reminder email. Creates the EMPLOYEE-role user "
        "and marks the invitation ACCEPTED. 404 if the token is invalid/expired; "
        "409 if this Clerk identity is already provisioned."
    ),
)
def employee_access(
    payload: EmployeeAccessRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> CurrentUserResponse:
    from app.api.dependencies import _extract_bearer_token

    token = _extract_bearer_token(authorization)
    claims = verify_clerk_token(token)

    user = redeem_employee_access_token(db, claims.clerk_user_id, payload.token)
    return CurrentUserResponse.model_validate(user)
