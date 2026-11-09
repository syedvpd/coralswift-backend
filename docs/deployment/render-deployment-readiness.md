# Render Deployment Readiness (2026-11-09)

**Status: PREPARED, NOT DEPLOYED.** Nothing was deployed to Render. No production migration was run. Deployment needs separate authorisation. The Render blueprint ([render.yaml](../../render.yaml)) has not been validated by Render itself.

## What was verified locally
- Docker image builds; container runs as non-root uid 10001; honours `$PORT`.
- `/health/live` returns 200; `/health/ready` returns 503 when the database is unreachable (so Render keeps the old instance during a bad deploy).
- Live `uvicorn` against the Supabase **development** database: public and auth-protected routes behaved correctly.
- Production settings validation (unit tests): app refuses to start in production without S3 + buckets, Brevo key + sender, `STAFF_MFA_REQUIRED=true`, a strong non-placeholder `SECRET_KEY`, `DEBUG=false`, and with `*` in CORS or hosts.

## Services (from render.yaml)
| Service | Type | Command | Notes |
|---|---|---|---|
| `coralswift-api` | web, docker | image `CMD` (uvicorn factory on `$PORT`) | `healthCheckPath: /health/live`; `preDeployCommand: alembic upgrade head` |
| `coralswift-maintenance` | cron, docker | `python scripts/run_maintenance.py`, every 15 min | SLA escalation, expiry reminders, retention purge, email retries |

Decision for the release owner: `preDeployCommand` applies migrations automatically on every deploy. Remove it if migrations must be a separate approved step.

## Environment variables (names only; set values in the Render dashboard)
Secrets (`sync: false`, never in the repo): `DATABASE_URL`, `SECRET_KEY`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `BREVO_API_KEY`, `TURNSTILE_SECRET_KEY` (required in production: the app refuses to start without it).
Fixed by blueprint: `CAPTCHA_ENABLED=true` (web service), `APP_ENV=production`, `DEBUG=false`, `LOG_LEVEL`, `STAFF_MFA_REQUIRED=true`, `STORAGE_BACKEND=s3`, `EMAIL_BACKEND=brevo`, `EMAIL_SENDER_NAME`.
Must be set per environment: `CORS_ALLOWED_ORIGINS` (exact frontend origins, no `*`), `ALLOWED_HOSTS` (API hostname, no `*`), `PORTAL_BASE_URL`, `S3_ENDPOINT_URL`, `S3_REGION`, `S3_BUCKET`, `S3_PARTNER_BUCKET`, `EMAIL_SENDER_ADDRESS`, `PRIVACY_NOTICE_VERSION`, `NOTIFY_GENERAL_EMAILS`, `NOTIFY_PROJECT_EMAILS`, `NOTIFY_PARTNER_EMAILS`, `NOTIFY_STRATEGIC_EMAILS`.
Optional tuning with code defaults: `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_MINUTES`, `MFA_ISSUER`, `PASSWORD_*`, `LOGIN_*`, `INVITATION_TTL_HOURS`, `PASSWORD_RESET_TTL_MINUTES`, `RATE_LIMIT_PER_MINUTE`, `MAX_REQUEST_BODY_BYTES`, `MAX_UPLOAD_BYTES`, `MAX_DOCUMENTS_PER_ENQUIRY`, `NOTIFICATION_MAX_RETRIES`, `IDEMPOTENCY_TTL_HOURS`.
Local only, do not set on Render: `TEST_DATABASE_URL`, `POSTGRES_*`, `DB_HOST_PORT`, `API_HOST_PORT`, `STORAGE_LOCAL_ROOT`.

Rules:
- `SECRET_KEY` for production must be newly generated and random (48+ chars). Do not reuse the development value.
- The S3 access key pair is **not** the database credential. The Supabase S3 endpoint uses its own key pair.
- Both buckets must be private (verified for the dev buckets: anonymous URL returns HTTP 400, not served).
- `DATABASE_URL` for the running app: use the Supabase pooler. Alembic needs a session-mode connection (port 5432); do not run migrations through transaction-mode port 6543.
- The development DB password and S3 keys were shared in chat during development. Rotate them, and use separate production credentials.

## Blockers before a real production go-live
1. Brevo account: API key, verified sender domain, SPF/DKIM/DMARC. Until then `EMAIL_BACKEND=brevo` cannot be tested end to end (production validation also blocks `console`).
2. Production Supabase project (or confirmed decision to reuse), with backup/PITR policy. The only backup taken so far is a manual dump of the dev DB (restore-tested once).
3. Business values: queue owners, backup owners, SLA hours, escalation emails, contact details, privacy notice version, retention periods.
4. Malware scanning: none configured. Uploaded files remain in quarantine status; do not describe uploads as scanned.
5. CAPTCHA: Turnstile code is ready, but production configuration refuses to load without `CAPTCHA_ENABLED=true` and `TURNSTILE_SECRET_KEY`, so **the web service will not start until the secret exists**; nothing was verified against Cloudflare. Calendar integration: not configured.
6. Monitoring, error tracking, uptime alerts: not set up.
7. Production TLS, proxy rate limiting and request-size limits can only be verified on the deployed environment; Supabase bucket privacy needs dashboard confirmation.
8. Frontend origin and custom domain (needed for `CORS_ALLOWED_ORIGINS`, `ALLOWED_HOSTS`, `PORTAL_BASE_URL`).
9. The code is not in a git repository; Render needs a repo connection. GitHub CI workflow exists but has never run.

## Deploy steps (when authorised)
1. Push code to a Git repo; connect it in Render; create the Blueprint from `render.yaml`.
2. Fill every `sync: false` variable and the "must be set" list above.
3. Take a Supabase backup of the target DB. Confirm the target is the intended production project.
4. Decide: automatic `preDeployCommand` or manual `alembic upgrade head`. Head revision is `0010`.
5. Deploy. Check `GET /health/live` 200 and `GET /health/ready` 200 on the live URL.
6. Create the first super administrator from a one-off shell: `python scripts/create_staff_user.py --email <addr> --name <name> --role super_administrator` (password via hidden prompt, or `STAFF_PASSWORD` env var). Enrol TOTP MFA at first login; staff sessions stay limited until verified.
7. Smoke test over HTTPS: login, one enquiry on a test address, notification delivery to an internal inbox, document upload then private download, `GET /admin/launch-readiness`.
8. Confirm the cron job ran (logs show `run_maintenance` output). To preview without changing anything: `python scripts/run_maintenance.py --dry-run` (see README; never run the real command against production data without a backup and authorisation).

## Rollback
- Application: Render "Rollback" to the previous deploy (instant).
- Database: migrations 0004-0010 are additive. Downgrades of 0009/0010 fail on purpose if rows already use the widened enum values. Roll back by restoring the pre-deploy backup, not by `alembic downgrade`, once real data exists.
- Disable the cron job in the dashboard to stop escalation emails and retention purges if misbehaving.

## Evidence status (2026-11-09)
Latest local verification: 219 tests passed, ruff/format/mypy clean, `alembic check` clean (local test DB). Docker, Supabase and storage checks are from the earlier run and were not repeated. Not verified: Render blueprint validity, Brevo, Turnstile, GitHub CI, any deployed behaviour (TLS, proxy rate limit, request-size limit).
