# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------
# Builder stage: install dependencies into a venv, nothing else.
# ---------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# ---------------------------------------------------------------------
# Runtime stage: copy only the venv + app code, run as non-root.
# ---------------------------------------------------------------------
FROM python:3.12-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 app && useradd --uid 1000 --gid app --shell /bin/bash --create-home app

WORKDIR /app
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app . .

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# gunicorn manages uvicorn workers: process supervision, graceful worker
# restarts, and a sane number of workers for a typical small ECS/App
# Runner task. entrypoint.sh runs pending migrations, then execs gunicorn
# with $GUNICORN_WORKERS (default 2) so the worker count can be sized per
# task without rebuilding the image.
ENV GUNICORN_WORKERS=2
ENTRYPOINT ["./scripts/entrypoint.sh"]
