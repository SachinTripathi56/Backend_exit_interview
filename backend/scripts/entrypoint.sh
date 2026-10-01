#!/bin/sh
# Production container entrypoint: apply pending Alembic migrations, then
# start the server.
#
# If arguments are passed (e.g. docker-compose overriding `command:` for
# local dev with --reload), those are what gets exec'd after migrations.
# With no arguments, falls back to the production gunicorn command below.
# This keeps one entrypoint usable for both `docker compose up` (dev) and
# the production image (ECS/App Runner) without maintaining two scripts.
set -e

echo "Running database migrations..."
alembic upgrade head

if [ "$#" -gt 0 ]; then
    echo "Starting: $*"
    exec "$@"
fi

echo "Starting server with ${GUNICORN_WORKERS:-2} worker(s)..."
exec gunicorn app.main:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-2}" \
    --timeout 60 \
    --graceful-timeout 30 \
    --access-logfile - \
    --error-logfile -
