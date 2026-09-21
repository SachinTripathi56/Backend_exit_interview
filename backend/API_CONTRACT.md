# API Contract — Exit Interview Platform

Base URL: `VITE_API_BASE_URL` (e.g. `https://api.example.com`)
All endpoints are prefixed with `/api/v1`.
Every authenticated request must send `Authorization: Bearer <Clerk token>`.

Full interactive docs are always available at `/docs` once the backend is
running — this file is the human-readable summary kept in sync with it.

## Status legend
✅ implemented · ⏳ planned (later phase)

## Auth / current user

| Method | Path | Status | Notes |
|---|---|---|---|
| GET | `/api/v1/me` | ✅ Phase 1 | Returns `{id, clerk_user_id, role, company_id, name, email}` |
| POST | `/api/v1/auth/register-company` | ✅ Phase 1 | One-time: creates a Company + first HR_ADMIN for a new Clerk identity. Body: `{company_name, name, email}`. 409 if already provisioned. |

## HR dashboard

| Method | Path | Status | Notes |
|---|---|---|---|
| GET | `/api/v1/hr/dashboard` | ✅ Phase 2 | `total_interviews`/`completed`/`pending` are currently derived from `Employee.status` since `interview_sessions` doesn't exist until Phase 6 — shape is stable, values sharpen later. `expired_interviews` and `active_campaigns` are `0` until Phase 4. |

## Employees

| Method | Path | Status | Notes |
|---|---|---|---|
| GET | `/api/v1/hr/employees` | ✅ Phase 2 | Query params: `search`, `department`, `status`, `page`, `limit` |
| GET | `/api/v1/hr/employees/{employee_id}` | ✅ Phase 2 | 404 (not 403) if the employee belongs to another company |
| POST | `/api/v1/hr/employees` | ✅ Phase 2 | 409 on duplicate `employee_id` or `email` within the same company |
| PUT | `/api/v1/hr/employees/{employee_id}` | ✅ Phase 2 | Partial update — only supplied fields change |
| DELETE | `/api/v1/hr/employees/{employee_id}` | ✅ Phase 2 | Returns 204 |

## Employee import

| Method | Path | Status | Notes |
|---|---|---|---|
| POST | `/api/v1/hr/employees/import` | ✅ Phase 3 | Multipart upload (`file`), `.xlsx`/`.xls`/`.csv`/`.pdf`. Validates synchronously; creates **nothing** yet. Returns `{import_id, total_rows, valid_rows, invalid_rows, errors[]}`. |
| GET | `/api/v1/hr/employees/imports/{import_id}` | ✅ Phase 3 | Full detail incl. all row errors |
| POST | `/api/v1/hr/employees/imports/{import_id}/confirm` | ✅ Phase 3 | Creates employees from the staged valid rows. Re-checks for conflicts introduced since validation and skips (not fails) those. Returns `{import_id, created_count, skipped_count, errors[]}`. 409 if already confirmed. |

## Campaigns

| Method | Path | Status | Notes |
|---|---|---|---|
| GET | `/api/v1/hr/campaigns` | ✅ Phase 4 | Query params: `status`, `page`, `limit` |
| POST | `/api/v1/hr/campaigns` | ✅ Phase 4 | Body: `{name, description?, instructions?, start_at, end_at, employee_ids[]}`. 422 `CAMPAIGN_INVALID_SCHEDULE` if `start_at >= end_at`. No employees → created as `DRAFT`. |
| GET | `/api/v1/hr/campaigns/{campaign_id}` | ✅ Phase 4 | Includes per-employee `assignments[]` (invitation_status, interview_status, timestamps) |
| PUT | `/api/v1/hr/campaigns/{campaign_id}` | ✅ Phase 4 | `employee_ids`, if provided, REPLACES the full assignment list. Only `CANCELLED` may be set explicitly via `status`. 409 if campaign is `COMPLETED`/`CANCELLED`, or if changing employees on an `ACTIVE` campaign. |
| DELETE | `/api/v1/hr/campaigns/{campaign_id}` | ✅ Phase 4 | Hard-deletes if `DRAFT`; otherwise soft-cancels (sets `CANCELLED`) and returns 204 either way |
| POST | `/api/v1/hr/campaigns/{campaign_id}/invitations` | ✅ Phase 5 | Body: `{employee_ids?}` — omit to invite all not-yet-invited employees, or pass explicit IDs to (re)send regardless of current status. 409 `CAMPAIGN_EXPIRED` if the campaign has ended/cancelled/completed. |
| POST | `/api/v1/hr/campaigns/{campaign_id}/reminders` | ✅ Phase 5 | Only reaches employees who were successfully invited but haven't yet completed the interview |

## Employee-facing

| Method | Path | Status | Notes |
|---|---|---|---|
| GET | `/api/v1/employee/me` | ✅ Phase 5 | The caller's own linked employee record only |
| GET | `/api/v1/employee/interview` | ✅ Phase 6 | Never 4xx's for "nothing assigned yet" — returns `{available, status, reason, campaign, interview_session}` |
| GET | `/api/v1/employee/interview/status` | ✅ Phase 6 | Lightweight poll target: `{status, interview_session_id, completed_at}` |
| POST | `/api/v1/employee/interview/start` | ✅ Phase 6 | Full server-side gate (see below). Idempotent — resuming an in-progress interview returns the same `interview_id`/`session_id` rather than creating a new AI session. |

## Interview start logic (POST /api/v1/employee/interview/start)

Checked server-side, in order, on every call — never bypassable from the client:

1. Clerk token valid  2. role is `EMPLOYEE`  3. employee record linked to this identity  4. employee belongs to caller's company  5. employee has an assigned campaign  6. campaign exists  7. campaign is `ACTIVE` (server-computed)  8. current server time within `start_at`/`end_at`  9. not already `COMPLETED`  10. `Employee.status != DISABLED`

Response: `{interview_id, session_id, status, interview_url}`. `session_id`/`interview_url` come from the AI Interview service adapter (`app/services/ai_interview_service.py`), which runs in a stub mode returning synthetic values when `AI_INTERVIEW_SERVICE_URL` isn't configured.

## Internal (backend-to-backend only, never called by frontend)

| Method | Path | Status | Notes |
|---|---|---|---|
| POST | `/api/v1/internal/ai/interview-completed` | ✅ Phase 7 | Auth: `X-Webhook-Secret` header (== `AI_INTERNAL_WEBHOOK_SECRET`), NOT a Clerk token. Body: `{ai_session_id, status: "COMPLETED"\|"ERROR", completed_at?, result?: {transcript?, summary?, satisfaction_score?, exit_reasons[], themes[], recommendations[]}, raw?}`. Idempotent — redelivering an already-processed `ai_session_id` is a safe no-op. This is our defined contract pending the real AI service's exact shape (see `app/schemas/interview_completion.py`). |

## Analytics / Reports

| Method | Path | Status | Notes |
|---|---|---|---|
| GET | `/api/v1/hr/analytics` | ✅ Phase 8 | Fully aggregated: `overall_satisfaction`, `completion_rate`, `department_participation[]`, `department_satisfaction[]`, `common_exit_reasons[]`, `common_themes[]`, `recommendations[]`, `key_comments[]`. `key_comments` is empty unless ≥3 completed interviews exist for the company (data-minimization — see `analytics_service.py`). Never includes an `employee_id`, name, or transcript. |
| GET | `/api/v1/hr/reports` | ✅ Phase 9 | Paginated list of previously generated reports |
| POST | `/api/v1/hr/reports/generate` | ✅ Phase 9 | Body: `{campaign_id?, format: "PDF"\|"EXCEL"}`. Synchronous — returns once generated. `status: "FAILED"` with `error_message` is a 200, not an HTTP error (the request was valid; generation itself failed). |
| GET | `/api/v1/hr/reports/{report_id}` | ✅ Phase 9 | Metadata only |
| GET | `/api/v1/hr/reports/{report_id}/download` | ✅ Phase 9 | Returns the actual file bytes with the correct `Content-Type` and `Content-Disposition: attachment` |

## Error format (all endpoints)

```json
{
  "error": {
    "code": "INTERVIEW_NOT_AVAILABLE",
    "message": "Your interview is not currently available."
  }
}
```

Codes currently defined (`app/core/exceptions.py`): `UNAUTHORIZED`,
`FORBIDDEN`, `NOT_FOUND`, `VALIDATION_ERROR`, `CONFLICT`,
`INTERVIEW_NOT_AVAILABLE`, `INTERVIEW_ALREADY_COMPLETED`,
`CAMPAIGN_EXPIRED`, `CAMPAIGN_INVALID_SCHEDULE`, `IMPORT_VALIDATION_FAILED`,
`UNSUPPORTED_FILE_TYPE`, `FILE_TOO_LARGE`, `AI_SERVICE_ERROR`,
`INTERNAL_ERROR`.

## List response format (all list endpoints)

```json
{ "items": [...], "page": 1, "limit": 20, "total": 120 }
```


## Security & audit (Phase 10)

- **Response headers**: every response includes `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`; API responses (`/api/v1/*`) also get `Cache-Control: no-store`. `Strict-Transport-Security` is added when `APP_ENV=production`.
- **Rate limiting**: `POST /auth/register-company` and `POST /auth/employee-access` are limited to 10 requests/60s per client IP; the internal webhook to 60/60s. In-process only — see `DEPLOYMENT.md` for the multi-instance caveat. Returns `429` with code `RATE_LIMITED`.
- **Audit trail**: every significant write (employee/campaign CRUD, import confirmation, invitations/reminders sent, interview started/completed, report generated, company registered, invitation redeemed) is recorded in `audit_logs` with actor, action, resource, and a small amount of non-sensitive context — never transcripts or full PII. Not yet exposed via an API endpoint (internal/db-only for now).
- **Fail-fast startup**: in `APP_ENV=production`, the app refuses to start if `SECRET_KEY`, `CLERK_JWKS_URL`/`CLERK_JWT_KEY`, `DATABASE_URL`, `AI_INTERNAL_WEBHOOK_SECRET`, or `FRONTEND_URL` are missing or still placeholder values.
