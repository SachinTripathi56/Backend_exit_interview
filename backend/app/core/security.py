"""
Clerk authentication verification.

Clerk answers "who is this user?". This module is ONLY responsible for
cryptographically verifying the bearer token issued by Clerk and extracting
the Clerk user id + claims from it. It does NOT know about roles or
companies — that mapping lives in our own `users` table and is resolved in
`api/dependencies.py`.

We verify using Clerk's JWKS endpoint (recommended, works with key rotation).
As a fallback for local/dev setups, a single static PEM public key
(CLERK_JWT_KEY) can be used instead.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient

from app.core.config import settings
from app.core.exceptions import UnauthorizedError

_jwk_client: PyJWKClient | None = None


def _get_jwk_client() -> PyJWKClient:
    global _jwk_client
    if _jwk_client is None:
        if not settings.CLERK_JWKS_URL:
            raise UnauthorizedError("Authentication is not configured (missing CLERK_JWKS_URL).")
        _jwk_client = PyJWKClient(settings.CLERK_JWKS_URL)
    return _jwk_client


@dataclass
class ClerkClaims:
    """Decoded, verified claims from a Clerk session token."""

    clerk_user_id: str
    email: str | None
    raw: dict[str, Any]


def verify_clerk_token(token: str) -> ClerkClaims:
    """
    Verify a Clerk-issued JWT (session token) and return its claims.

    Raises UnauthorizedError if the token is missing, malformed, expired,
    or fails signature/issuer/audience verification.
    """
    if not token:
        raise UnauthorizedError("Missing authentication token.")

    decode_kwargs: dict[str, Any] = {
        "algorithms": ["RS256"],
        "options": {"require": ["exp", "iat", "sub"]},
    }
    if settings.CLERK_ISSUER:
        decode_kwargs["issuer"] = settings.CLERK_ISSUER
    if settings.CLERK_AUDIENCE:
        decode_kwargs["audience"] = settings.CLERK_AUDIENCE

    try:
        if settings.CLERK_JWKS_URL:
            signing_key = _get_jwk_client().get_signing_key_from_jwt(token).key
        elif settings.CLERK_JWT_KEY:
            signing_key = settings.CLERK_JWT_KEY
        else:
            raise UnauthorizedError(
                "Authentication is not configured (missing CLERK_JWKS_URL or CLERK_JWT_KEY)."
            )

        payload = jwt.decode(token, signing_key, **decode_kwargs)
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Authentication token has expired.") from exc
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid authentication token.") from exc

    clerk_user_id = payload.get("sub")
    if not clerk_user_id:
        raise UnauthorizedError("Authentication token is missing a subject claim.")

    email = payload.get("email") or _extract_email_from_claims(payload)

    return ClerkClaims(clerk_user_id=clerk_user_id, email=email, raw=payload)


def _extract_email_from_claims(payload: dict[str, Any]) -> str | None:
    # Clerk session tokens don't always embed email directly depending on
    # template configuration; custom JWT templates may nest it differently.
    for key in ("email_address", "primary_email_address"):
        if key in payload:
            return payload[key]
    return None


def verify_internal_webhook_secret(provided_secret: str | None) -> None:
    """
    Used to authenticate inbound calls from the existing AI Interview
    service (e.g. the interview-completed webhook). This is a simple shared
    secret check — never expose AI_INTERNAL_WEBHOOK_SECRET to the frontend.
    """
    if not settings.AI_INTERNAL_WEBHOOK_SECRET:
        raise UnauthorizedError("Internal webhook is not configured.")
    if not provided_secret or provided_secret != settings.AI_INTERNAL_WEBHOOK_SECRET:
        raise UnauthorizedError("Invalid internal webhook credentials.")
