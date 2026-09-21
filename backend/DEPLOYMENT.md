# Deployment Guide

This backend is a stateless FastAPI container plus a Neon Postgres
database — it deploys cleanly to any container platform. This guide
covers AWS, since that's the most common target, but nothing here is
AWS-specific at the application layer.

**Note on AWS App Runner**: as of April 30, 2026, AWS App Runner no
longer accepts new customers (existing App Runner customers are
unaffected). AWS's official recommendation for new deployments is
**Amazon ECS Express Mode** — the same "point at a container image, get
a running HTTPS service" simplicity App Runner offered, built on top of
standard ECS/Fargate. That's Option A below. If you already have an AWS
account with an existing App Runner service, it still works exactly as
before and you can skip straight to Option B or C.

## Prerequisites

- A Neon Postgres project (or any Postgres 14+) — `DATABASE_URL`
- A Clerk application configured for both HR and employee users —
  `CLERK_JWKS_URL`, `CLERK_ISSUER`
- Cloudinary account (optional but recommended) — `CLOUDINARY_*`
- An email provider (Resend/SendGrid/SES) for anything beyond local `console` logging
- A generated `AI_INTERNAL_WEBHOOK_SECRET` (e.g. `openssl rand -hex 32`) shared with whoever operates the AI Interview service
- A generated `SECRET_KEY`

The app **refuses to start** in `APP_ENV=production` if any of the above
critical values are missing or left as placeholders — see
`app/core/config.py::validate_production_config`. This is intentional:
better a failed deploy than a running server no client can authenticate
against.

## Option A — Amazon ECS Express Mode (simplest, recommended)

1. Build and push the image to ECR:
   ```bash
   aws ecr create-repository --repository-name exit-interview-backend
   aws ecr get-login-password | docker login --username AWS --password-stdin <account>.dkr.ecr.<region>.amazonaws.com
   docker build -t exit-interview-backend .
   docker tag exit-interview-backend:latest <account>.dkr.ecr.<region>.amazonaws.com/exit-interview-backend:latest
   docker push <account>.dkr.ecr.<region>.amazonaws.com/exit-interview-backend:latest
   ```
2. Store each secret (`DATABASE_URL`, `CLERK_SECRET_KEY`, `CLOUDINARY_API_SECRET`, `AI_INTERNAL_WEBHOOK_SECRET`, `SECRET_KEY`) in AWS Secrets Manager — one secret per value.
3. In the AWS Console: **ECS → Express mode → create a new app.** Point it at the ECR image above.
4. Set **Container port** to `8000` and **Health check path** to `/health`.
5. Choose "Create new role" for both the Task execution role and Infrastructure role if you don't have them yet — Express Mode provisions them automatically.
6. Add environment variables from `.env.example`, referencing the Secrets Manager ARNs from step 2 for the sensitive ones.
7. Create. Express Mode provisions a Fargate service, Application Load Balancer, HTTPS certificate, and networking automatically, and gives you a URL like `https://<service>.ecs.<region>.on.aws`.

Express Mode services share ALBs across up to 25 services to keep cost
down, and only deploy pre-built images (no source-build option) — you
need the ECR push step above rather than pointing it at a GitHub repo
directly.

## Option B — Standard ECS Fargate (more control)

1. Same ECR push as step 1 above.
2. Create a Fargate task definition manually:
   - Container port `8000`, health check `curl -f http://localhost:8000/health` (already baked into the image's `HEALTHCHECK`; ECS can also probe it directly).
   - Secrets (`DATABASE_URL`, `CLERK_SECRET_KEY`, `CLOUDINARY_API_SECRET`, `AI_INTERNAL_WEBHOOK_SECRET`, `SECRET_KEY`) sourced from AWS Secrets Manager via the task definition's `secrets` field — never baked into the image or task definition as plaintext.
   - CPU/memory: 0.5 vCPU / 1GB is a reasonable starting point; tune `GUNICORN_WORKERS` alongside it (roughly `2 × vCPU + 1`).
3. Put an Application Load Balancer in front with the target group health-checking `/health`.
4. Run the service across at least 2 tasks / 2 AZs for availability.
5. **Rate limiting caveat**: `app/core/middleware.py`'s rate limiter is in-process/in-memory. With multiple Fargate tasks behind the ALB, each task tracks its own counters — a caller effectively gets `limit × task_count` requests before being blocked anywhere. Fine for the identity-bootstrapping endpoints it currently covers at small-to-medium scale; move to a Redis-backed limiter (e.g. ElastiCache) if this needs to be exact across many tasks.

Choose this over Express Mode if you need custom VPC networking, WAF in
front of the ALB, non-default scaling policies, or multiple services
sharing infrastructure in ways Express Mode's defaults don't cover.

## Option C — Existing App Runner customers only

If your AWS account already used App Runner before April 30, 2026, it
remains fully available: create a service from the same ECR image,
port `8000`, health check `/health`, and reference the same Secrets
Manager entries — functionally identical to Option A's setup, just
through the App Runner console instead of ECS Express Mode.

## Migrations

`scripts/entrypoint.sh` runs `alembic upgrade head` automatically before
starting the server, on every container start. This is safe (migrations
are additive and idempotent — Alembic tracks the applied revision), but
for a multi-task deployment, only one task's migration run actually does
work; the others see "already at head" and continue immediately. No
separate migration step is required in the deploy pipeline.

## Logging

Both `access` and `error` gunicorn logs go to stdout/stderr (`--access-logfile -`,
`--error-logfile -`), which is what CloudWatch Logs (via the `awslogs`
ECS log driver, or App Runner's built-in log capture) expects.

## Zero-downtime deploys

- ECS: use a rolling deployment with `minimumHealthyPercent: 100`,
  `maximumPercent: 200`, and the ALB health check on `/health` — new tasks
  must pass health checks before old ones are drained.
- App Runner: rolling deploys are automatic.
- Gunicorn's `--graceful-timeout 30` gives in-flight requests 30s to
  finish before a worker is force-killed during a deploy/restart.
