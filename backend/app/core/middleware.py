"""
Cross-cutting HTTP middleware: security headers and a lightweight rate
limiter for the handful of unauthenticated/identity-bootstrapping
endpoints that are realistic brute-force targets.

Rate limiting note: this is an in-process, in-memory sliding window. It
protects a single instance correctly but does NOT share state across
multiple instances/replicas — a production deployment running more than
one instance behind a load balancer needs a shared store (Redis) instead.
Documented here rather than silently pretending this is production-grade
distributed rate limiting.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        for header, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        if settings.APP_ENV == "production":
            response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
        if request.url.path.startswith(settings.API_V1_PREFIX):
            # API responses carry tenant data — never cache them client-side
            # or at an intermediate proxy.
            response.headers.setdefault("Cache-Control", "no-store")
        return response


# Path -> (max_requests, window_seconds). Only the identity-bootstrapping
# endpoints that don't already require a valid Clerk session are listed:
# once a caller has a real session, ordinary auth (and, for HR endpoints,
# tenant scoping) is the meaningful control.
_RATE_LIMITED_PATHS: dict[str, tuple[int, int]] = {
    f"{settings.API_V1_PREFIX}/auth/register-company": (10, 60),
    f"{settings.API_V1_PREFIX}/auth/employee-access": (10, 60),
    f"{settings.API_V1_PREFIX}/internal/ai/interview-completed": (60, 60),
}

# Module-level (not instance-level) so tests can reset it directly without
# needing to reach into Starlette's internal, lazily-built middleware
# stack. See reset_rate_limits() below.
_hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def reset_rate_limits() -> None:
    """Test-only helper: clears all rate-limit counters between tests."""
    _hits.clear()


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)

        limit = _RATE_LIMITED_PATHS.get(request.url.path)
        if limit is not None:
            max_requests, window_seconds = limit
            client_ip = request.client.host if request.client else "unknown"
            key = (client_ip, request.url.path)
            now = time.monotonic()
            hits = _hits[key]

            while hits and now - hits[0] > window_seconds:
                hits.popleft()

            if len(hits) >= max_requests:
                return JSONResponse(
                    status_code=429,
                    content={"error": {"code": "RATE_LIMITED", "message": "Too many requests. Please try again shortly."}},
                    headers={"Retry-After": str(window_seconds)},
                )
            hits.append(now)

        return await call_next(request)
