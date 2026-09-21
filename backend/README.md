# Exit Interview Platform — Backend

FastAPI backend for the Exit Interview Platform. Consumed by a separately
built frontend (Lovable / React + TypeScript). See `API_CONTRACT.md` for the
full REST contract shared with the frontend team.

This backend is being delivered in phases (matching the original spec's
phase breakdown). Each phase is a working increment on top of the last.

## Phase status

- [x] **Phase 1 — Project setup**: FastAPI app, config, Neon Postgres
      connection, Alembic, Clerk token verification, `companies`/`users`
      models, `GET /api/v1/me`, company registration/provisioning.
- [x] **Phase 2 — Employee management, RBAC, tenant isolation, HR dashboard**:
      `employees` table + model, full CRUD with search/filter/pagination,
      role-guarded (`require_hr`) endpoints, tenant-scoped repository layer
      that makes cross-company access structurally hard to introduce by
      accident, and `GET /api/v1/hr/dashboard`.
- [x] **Phase 3 — Employee imports + Cloudinary**: parses `.xlsx`/`.xls`/
      `.csv`/`.pdf` uploads, validates every row (required fields, email
      format, date format, in-file duplicates, duplicates against existing
      employees), stages valid rows without writing to `employees` until
      `/confirm` is called, and archives the original file to Cloudinary
      as a private/authenticated resource (best-effort — never blocks the
      import if Cloudinary isn't configured).
- [x] **Phase 4 — Campaigns**: `campaigns` + `campaign_employees` tables,
      full CRUD, server-computed status (`SCHEDULED`/`ACTIVE`/`COMPLETED`/
      `EXPIRED` derived from server time — never trusts the client's
      clock), schedule validation (`start_at < end_at`), employee
      assignment scoped/validated against the caller's own company.
- [x] **Phase 5 — Email invitations, reminders, employee access**: provider-
      agnostic `email_service.py` (console/Resend/SendGrid/SES), secure
      single-use invitation tokens (SHA-256 hashed, never stored/sent in
      plaintext) bridging a Clerk identity to a specific `Employee` via
      `POST /auth/employee-access`, bulk invitation/reminder sending with
      a full `email_logs` audit trail, and `GET /employee/me`.
- [x] **Phase 6 — Interview sessions + AI bot integration**: `interview_sessions`
      table, a clean adapter (`ai_interview_service.py`) to the *separate,
      already-existing* AI Interview FastAPI service — never reimplements
      interview logic, and runs in a graceful stub mode when
      `AI_INTERVIEW_SERVICE_URL` isn't configured — plus the full 10-step
      `/employee/interview/start` gate (assignment, window, completion,
      disabled-check) re-derived server-side on every call.
- [x] **Phase 7 — Interview completion webhook**: `interview_results` table
      (never exposed to HR individually — see Phase 8), an idempotent
      internal webhook (`POST /internal/ai/interview-completed`)
      authenticated by shared secret (never a Clerk token), which marks the
      session/assignment/employee complete, sends the employee a
      confirmation email, and notifies HR admins — all in one transaction,
      safe to redeliver.
- [x] **Phase 8 — Analytics**: `GET /hr/analytics` returns only aggregates —
      completion rate, department participation/satisfaction, frequency-
      ranked exit reasons/themes/recommendations. `key_comments` is
      withheld entirely below a minimum sample size so a single response
      is never individually attributable in a small company/department.
- [x] **Phase 9 — Reports**: `GET/POST /hr/reports`, `/generate`, `/{id}`,
      `/{id}/download`. Generates real PDF (reportlab) and Excel
      (xlsxwriter) files — verified by actually generating and re-reading
      both formats back with `pdfplumber`/`openpyxl` during development,
      not just compiling. Reports are metadata rows; file bytes are
      deterministically regenerated at download time from current
      aggregate data, with best-effort Cloudinary archival for audit.
      Scoped either company-wide or to a single campaign.
- [x] **Phase 10 — Audit logs, security hardening, Docker/AWS polish**:
      `audit_logs` table + `audit_service.py`, wired into every significant
      write path (employee/campaign CRUD, import confirm, invitations/
      reminders, interview start/completion, report generation, company
      registration, invitation redemption). Security: response headers
      middleware (`X-Frame-Options`, `X-Content-Type-Options`, HSTS in
      prod), an in-process rate limiter on the identity-bootstrapping
      endpoints, and fail-fast production config validation (refuses to
      start with placeholder secrets/URLs when `APP_ENV=production`) — all
      individually verified with real requests, not just written. Docker:
      multi-stage non-root image, gunicorn+uvicorn workers, healthcheck,
      migration-on-start entrypoint; see `DEPLOYMENT.md` for the AWS path.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# fill in DATABASE_URL (Neon), CLERK_JWKS_URL, CLERK_ISSUER, etc.

# Run migrations
alembic upgrade head

# Run the API
uvicorn app.main:app --reload
```

Visit `http://localhost:8000/docs` for interactive OpenAPI documentation.

## Running with Docker

```bash
docker compose up --build
```

This starts the API plus a local throwaway Postgres container for
development. **Production/staging always use Neon** — just point
`DATABASE_URL` at your Neon connection string; nothing else changes.

## Running tests

Tests run against a real Postgres database (schema uses Postgres-native
UUID/enum types). Point `TEST_DATABASE_URL` at a throwaway database:

```bash
export TEST_DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/exit_interview_test
pytest
```

## Architecture notes

- **Clerk** answers "who is this user?" — verified in `app/core/security.py`.
- **Our DB** answers "what company/role do they have?" — resolved in
  `app/api/dependencies.py::get_current_user`, which every protected
  endpoint depends on. This is the ONLY place that bridges Clerk identity
  to our authorization model.
- **Tenant isolation**: every company-scoped query must be filtered by
  `company_id` taken from the authenticated user's server-side identity —
  never from a client-supplied field. See `TenantContext` in
  `app/api/dependencies.py`.
- **Errors**: raise `AppError` subclasses from `app/core/exceptions.py`
  anywhere in business logic; the global handler in `app/main.py` converts
  them to the standardized `{"error": {"code", "message"}}` shape.
- **AI Interview Bot**: a separate, already-existing FastAPI service. This
  platform never reimplements interview logic — see
  `app/services/ai_interview_service.py` (added in Phase 6) for the
  adapter boundary.

## Migrations

New tables are added incrementally, phase by phase, via Alembic:

```bash
alembic revision --autogenerate -m "add employees table"
alembic upgrade head
```
