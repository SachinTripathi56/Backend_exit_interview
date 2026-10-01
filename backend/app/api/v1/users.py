"""Current-user endpoint. The frontend calls this once per session to
determine the authenticated user's application role and company."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user
from app.models.user import User
from app.schemas.user import CurrentUserResponse

router = APIRouter(tags=["users"])


@router.get(
    "/me",
    response_model=CurrentUserResponse,
    summary="Get the authenticated user's profile, role, and company",
    description=(
        "The frontend uses this endpoint (and ONLY this endpoint) to determine "
        "the application role after Clerk authentication. Never trust a "
        "client-side role claim instead of calling this."
    ),
)
def get_me(current_user: User = Depends(get_current_user)) -> CurrentUserResponse:
    return CurrentUserResponse.model_validate(current_user)
