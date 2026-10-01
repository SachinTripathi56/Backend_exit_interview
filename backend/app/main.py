"""
Exit Interview Platform — FastAPI application entrypoint.

Run locally with:
    uvicorn app.main:app --reload

See /docs for interactive OpenAPI documentation once running.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.core.config import settings, validate_production_config
from app.core.exceptions import AppError, ErrorCode
from app.core.middleware import RateLimitMiddleware, SecurityHeadersMiddleware

logging.basicConfig(level=logging.INFO if not settings.DEBUG else logging.DEBUG)
logger = logging.getLogger("exit_interview_platform")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail fast rather than serve traffic with insecure/incomplete config —
    # only enforced when APP_ENV=="production"; see config.py.
    validate_production_config(settings)
    logger.info("Starting %s (env=%s)", settings.APP_NAME, settings.APP_ENV)
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description=(
        "Backend platform API for the Exit Interview Platform. Consumed by a "
        "separately-built frontend. All endpoints are namespaced under "
        f"{settings.API_V1_PREFIX}."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# ----------------------------------------------------------------------
# CORS — only the configured frontend origin(s), never a wildcard in prod.
# ----------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security headers on every response, and a lightweight rate limit on the
# few identity-bootstrapping endpoints that don't yet have a real session
# to scope against. See app/core/middleware.py.
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)


# ----------------------------------------------------------------------
# Standardized error responses: {"error": {"code": ..., "message": ...}}
# ----------------------------------------------------------------------
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code.value, "message": exc.message}},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": ErrorCode.VALIDATION_ERROR.value,
                "message": "The request failed validation.",
                "details": exc.errors(),
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Never leak stack traces / internals to the client.
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": ErrorCode.INTERNAL_ERROR.value,
                "message": "An unexpected error occurred. Please try again.",
            }
        },
    )


@app.get("/health", tags=["meta"], summary="Liveness/readiness probe")
def health_check() -> dict:
    return {"status": "ok", "env": settings.APP_ENV}


# ----------------------------------------------------------------------
# Mount versioned API
# ----------------------------------------------------------------------
from app.api.v1.router import api_router  # noqa: E402  (import after app/middleware setup)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)
