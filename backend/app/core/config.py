"""
Centralized application configuration.

All configuration is loaded from environment variables so the same codebase
can run locally, in Docker, or on AWS without code changes. Nothing sensitive
is ever hardcoded here.
"""
from functools import lru_cache
from typing import List

from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ------------------------------------------------------------------
    # App
    # ------------------------------------------------------------------
    APP_NAME: str = "Exit Interview Platform API"
    APP_ENV: str = "development"  # development | staging | production
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    # ------------------------------------------------------------------
    # Database (Neon PostgreSQL)
    # ------------------------------------------------------------------
    DATABASE_URL: str = "postgresql+psycopg://user:password@localhost:5432/exit_interview"
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 10
    DATABASE_ECHO: bool = False

    # ------------------------------------------------------------------
    # Clerk Authentication
    # ------------------------------------------------------------------
    CLERK_SECRET_KEY: str = ""
    CLERK_JWT_KEY: str = ""  # PEM public key, or JWKS is fetched via CLERK_JWKS_URL
    CLERK_JWKS_URL: str = ""  # e.g. https://<your-domain>.clerk.accounts.dev/.well-known/jwks.json
    CLERK_ISSUER: str = ""  # e.g. https://<your-domain>.clerk.accounts.dev
    CLERK_AUDIENCE: str = ""

    # ------------------------------------------------------------------
    # Cloudinary
    # ------------------------------------------------------------------
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""

    # ------------------------------------------------------------------
    # Existing AI Interview Bot (separate FastAPI service)
    # ------------------------------------------------------------------
    AI_INTERVIEW_SERVICE_URL: str = ""
    AI_INTERVIEW_SERVICE_API_KEY: str = ""
    AI_INTERVIEW_SERVICE_TIMEOUT_SECONDS: int = 15

    # Shared secret used to authenticate inbound webhook calls FROM the AI
    # service back to this platform (e.g. interview-completed callback).
    AI_INTERNAL_WEBHOOK_SECRET: str = ""

    # ------------------------------------------------------------------
    # Email provider abstraction
    # ------------------------------------------------------------------
    EMAIL_PROVIDER: str = "console"  # console | resend | sendgrid | ses
    EMAIL_API_KEY: str = ""
    EMAIL_FROM_ADDRESS: str = "no-reply@example.com"
    EMAIL_FROM_NAME: str = "Exit Interview Platform"

    # AWS SES specific (only used when EMAIL_PROVIDER=ses)
    AWS_REGION: str = "us-east-1"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""

    # ------------------------------------------------------------------
    # Frontend / CORS
    # ------------------------------------------------------------------
    FRONTEND_URL: str = "http://localhost:5173"
    ADDITIONAL_CORS_ORIGINS: str = ""  # comma-separated extra origins

    # --- File upload limits ---
    MAX_IMPORT_FILE_SIZE_MB: int = 10
    ALLOWED_IMPORT_EXTENSIONS: str = ".xlsx,.xls,.csv,.pdf"

    # --- Invitations ---
    INVITATION_TOKEN_EXPIRY_DAYS: int = 14
    EMPLOYEE_ACCESS_URL_PATH: str = "/employee/access"

    # --- Rate limiting ---
    # Disabled by default in the test suite (see tests/conftest.py) since a
    # single shared TestClient "IP" would otherwise trip the limiter across
    # unrelated tests that each legitimately call register-company once.
    RATE_LIMIT_ENABLED: bool = True

    # ------------------------------------------------------------------
    # Security
    # ------------------------------------------------------------------
    SECRET_KEY: str = "change-me-in-production"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origins(self) -> List[str]:
        origins = [self.FRONTEND_URL]
        if self.ADDITIONAL_CORS_ORIGINS:
            origins.extend(
                o.strip() for o in self.ADDITIONAL_CORS_ORIGINS.split(",") if o.strip()
            )
        if self.APP_ENV == "development":
            origins.extend(["http://localhost:5173", "http://localhost:3000"])
        # de-duplicate while preserving order
        seen = set()
        result = []
        for o in origins:
            if o not in seen:
                seen.add(o)
                result.append(o)
        return result

    @property
    def allowed_import_extensions_list(self) -> List[str]:
        return [e.strip().lower() for e in self.ALLOWED_IMPORT_EXTENSIONS.split(",") if e.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance. Import this everywhere instead of Settings()."""
    return Settings()


settings = get_settings()


def validate_production_config(s: Settings) -> None:
    """
    Fail fast on startup rather than serving traffic with insecure defaults.

    Only enforced when APP_ENV=="production" — local/dev/staging are free
    to run with placeholder values (that's what .env.example's defaults
    are for).
    """
    if s.APP_ENV != "production":
        return

    problems: list[str] = []
    if s.SECRET_KEY == "change-me-in-production":
        problems.append("SECRET_KEY is still the default placeholder value.")
    if not s.CLERK_JWKS_URL and not s.CLERK_JWT_KEY:
        problems.append("Neither CLERK_JWKS_URL nor CLERK_JWT_KEY is configured — auth would accept no one.")
    if "user:password@localhost" in s.DATABASE_URL:
        problems.append("DATABASE_URL is still the default placeholder value.")
    if not s.AI_INTERNAL_WEBHOOK_SECRET:
        problems.append("AI_INTERNAL_WEBHOOK_SECRET is not set — the interview-completed webhook is unusable.")
    if s.FRONTEND_URL.startswith("http://localhost"):
        problems.append("FRONTEND_URL still points at localhost — CORS would reject the real frontend.")

    if problems:
        raise RuntimeError(
            "Refusing to start in production with insecure/incomplete configuration:\n- "
            + "\n- ".join(problems)
        )
