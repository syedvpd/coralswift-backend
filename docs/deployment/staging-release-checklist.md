# Staging Release Checklist (prepared 2026-11-09, nothing executed on staging yet)

Scope: a dedicated Render **staging** environment (`render.staging.yaml`). No production service is created. Every item below is **PENDING** until someone runs it and records the result; a mock-only run does not count for a real-integration item.

## A. Completed locally (evidence is in `docs/qa/final-backend-test-report.md`)
- Git repository initialised, baseline commit on `main`; no remote, nothing pushed.
- Staging app profile: `APP_ENV=staging` loads the same strict validation as production plus a mandatory `EMAIL_RECIPIENT_ALLOWLIST`; tested in `tests/unit/test_config.py`.
- `render.staging.yaml` written; every variable name checked against `Settings`. Not validated by Render.
- CI workflow extended (not yet run on GitHub).

## B. Credential inventory (names only; values live only in each environment's secret store)
| Variable | Development (`.env`) | Staging (Render) | Production (Render) |
|---|---|---|---|
| `DATABASE_URL` | Supabase dev project | **separate staging DB** | separate production DB |
| `SECRET_KEY` | dev value | new random 48+ chars | new random 48+ chars |
| `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | dev project keys | staging keys | production keys |
| `S3_ENDPOINT_URL`, `S3_REGION`, `S3_BUCKET`, `S3_PARTNER_BUCKET` | dev buckets | **separate private staging buckets** | production buckets |
| `BREVO_API_KEY`, `EMAIL_SENDER_ADDRESS` | not set (console backend) | staging key; sender on verified domain | production key |
| `EMAIL_RECIPIENT_ALLOWLIST` | unset | **required**, internal inboxes only | unset |
| `TURNSTILE_SECRET_KEY` (+ site key in the frontend) | unset (`CAPTCHA_ENABLED=false`) | Turnstile widget for the staging hostname | widget for the production hostname |
| `CORS_ALLOWED_ORIGINS`, `ALLOWED_HOSTS`, `PORTAL_BASE_URL` | localhost | staging hostnames | production hostnames |
| `NOTIFY_*_EMAILS` | unset | internal inboxes on the allow-list | real owners (after decisions 1-2) |
| `TEST_DATABASE_URL`, `POSTGRES_*` | local Docker only | never set | never set |

Never reuse a value across columns. Staging must not point at the dev Supabase project or any production resource.

## C. Credential rotation (owner performs; nothing was changed by Claude)
Exposed in chat during development, **rotation required**: Supabase database password (`DATABASE_URL`), Supabase S3 access key pair (`S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`). Also rotate the dev `SECRET_KEY` if it was ever shared. Future: Brevo key and Turnstile secret are issued fresh per environment; if ever pasted in chat, rotate them too.

Procedure per credential:
1. Provider dashboard: create the new credential; keep the old one active.
2. Update only the intended environment's secret store (`.env` locally, Render dashboard for staging/production).
3. Restart the service/script; check `/health/ready` (database) and a storage round trip (database credential and S3 keys are separate).
4. Revoke the old credential.
5. Record date and tester here. **Rotation is complete only after the owner confirms step 4 and the app works with the new values.**

Status: Supabase DB password - OPEN. Supabase S3 keys - OPEN. Brevo - not issued. Turnstile - not issued.

## D. GitHub (needs the owner; Claude did not create or push to a remote)
1. Create a **private** repository, add it as `origin`, push `main` (explicit approval needed).
2. Settings: branch protection on `main` requiring the `checks` and `docker` jobs; Actions read-only default token.
3. Repository secrets: **none required.** CI uses an ephemeral Postgres service, `SECRET_KEY` placeholder and mocked integrations, so it cannot reach Supabase, Brevo, Turnstile or storage. Do not add production secrets to GitHub.
4. CI is "passing" only after a real Actions run finishes green. Status: NOT RUN.

## E. Render staging actions (dashboard; owner approval)
1. Create the staging database (separate Supabase project or database) and two private buckets. Confirm bucket privacy in the dashboard.
2. Create the Blueprint from `render.staging.yaml`; fill every `sync: false` value from section B.
3. Create the Turnstile widget for the staging hostname; put the site key in the staging frontend and the secret in `TURNSTILE_SECRET_KEY`.
4. Brevo: verify sender domain (SPF, DKIM, DMARC); put internal inboxes in `EMAIL_RECIPIENT_ALLOWLIST`.
5. Back up the staging DB, confirm the target host, then run `alembic upgrade head` (session-mode connection, port 5432) from a shell with staging `DATABASE_URL`. Expected revision `0010`.
6. Create the first staff user (`scripts/create_staff_user.py`), enrol TOTP.
7. Confirm the service started: a missing security setting aborts startup with an `Invalid staging configuration` message listing the problems (tested locally).
Built in: non-root uid 10001 (checked), health checks `/health/live` and `/health/ready`, request-body limit (`MAX_REQUEST_BODY_BYTES`), rate limit (`RATE_LIMIT_PER_MINUTE`, per process), HSTS and security headers, docs disabled, secrets redacted in logs. Proxy headers are trusted from any source (`--forwarded-allow-ips='*'`), which is correct only because Render's load balancer is the sole path to the container. Add edge rate limiting and a body-size cap at the proxy/CDN; **verify TLS, proxy limits and header handling on the live staging URL.**

## F. Staging verification scenarios (use test personas and test records; internal inboxes only)
Mark each with date, tester, result. Items that need Turnstile, Brevo or real storage are not satisfied by local tests.
| # | Scenario | Steps / pass criteria | Real integration? | Result |
|---|---|---|---|---|
| 1 | Public enquiries | POST `/api/v1/enquiries/contact`, `/project`, `/partner`, `/strategic` with test data and valid Turnstile token; 201 + reference; `GET /enquiries/{ref}/status` with token; strategic is absent from public search | Turnstile, DB | PENDING |
| 2 | CAPTCHA | Missing, tampered and reused token each -> 403 `BOT_CHECK_FAILED`; valid token -> 201 | **real Turnstile** | PENDING |
| 3 | Brevo mail | Submit a contact enquiry using an allow-listed address: ack delivered, admin notifications list shows `sent`. Submit with a non-listed address: row `failed`, no mail. | **real Brevo**, internal inbox only | PENDING |
| 4 | Invitation, login, MFA | Super admin invites partner and staff; accept invitation; login; staff enrol TOTP, verify, use and regenerate recovery codes; staff session limited before MFA | Brevo (link email), DB | PENDING |
| 5 | Partner documents | Upload PDF (private bucket, status `quarantined`); wrong type and oversize rejected; authorised download works and is audited; no public URL (anonymous request fails); other organisation gets 404 | **real storage** | PENDING |
| 6 | Six-stage workflow | Partner submits application; super admin assigns reviewer; reviewer walks eligibility, capability, commercial/legal, pilot, scale-up; information request and response; skipping a stage refused | DB | PENDING |
| 7 | Admin operations | Role matrix (BDM, reviewer, content admin, super admin); lead assignment and follow-ups; `/admin/audit`; `/admin/reports/enquiries.csv` and `applications.csv` open safely in a spreadsheet | DB | PENDING |
| 8 | Content governance | Draft -> in_review -> approved (super admin) -> published; claim not cleared blocks publish; clearing a claim un-blocks; un-clearing pulls content | DB | PENDING |
| 9 | Privacy and failures | Submit privacy requests; handle them; make a notification fail (non-listed recipient) and retry from `/admin/notifications` | DB, Brevo | PENDING |
| 10 | SLA and maintenance | Set `sla.general`; create an enquiry; after due time `/admin/enquiries?sla_breached=true` lists it; run `python scripts/run_maintenance.py --dry-run` on staging and compare counts; real run only after review | DB | PENDING |
| 11 | Isolation | Two partner organisations: every cross-access returns 404; anonymous calls to protected routes return 401 | DB | PENDING |
| 12 | Health and recovery | `/health/live` 200; `/health/ready` 200; with the DB credentials wrongly set (separate throwaway deploy) readiness 503 with no leak; with the storage key wrong, an upload fails cleanly and the document is marked failed; restore the setting and confirm recovery | DB, storage | PENDING |

Exit criteria for "staging verified": all 12 rows PASS with evidence, rotation (section C) done for staging credentials, Phase 1 criteria re-evaluated by the owner. This does not make the system production-ready.

## G. Maintenance safety
- `python scripts/run_maintenance.py --dry-run` is read-only (database transaction forced READ ONLY; no email, storage or queue client is built). Verified locally: pytest (SLA, expiry, retention counters with data; storage and notification rows unchanged), and inside Docker against the local test database (`exit 0`, all counters 0 on an empty database).
- The staging cron in `render.staging.yaml` runs `--dry-run`. Change it to the real command only after reviewing the counts.
- Real run requires: confirmed target, verified backup, explicit authorisation. It deletes files from storage (retention) and sends email (notifications). The real purge was never run against Supabase.
