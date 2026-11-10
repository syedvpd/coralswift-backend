# Production Readiness Report (2026-11-10)

**Not production-ready.** Evidence below is split into what was observed and what is still unverified. Production has not been created, deployed to or migrated.

## Observed (dated evidence)
| Area | Evidence |
|---|---|
| Local quality gates | `ruff`, `ruff format --check`, `mypy` clean; `pytest` 254 passed; fresh-database migration to `0011` and `alembic check` clean; Docker image builds, runs as uid 10001 (2026-11-10, `backend-gap-test-report.md`) |
| Deployed development service | `https://coralswift-backend.onrender.com` answered `/health/ready` 200 and redirected `/` to `/docs` (2026-11-10, earlier session; not rechecked after the gap work). It runs `APP_ENV=development` against the Supabase **development** database |
| Cloudflare Turnstile | the secret key is accepted by Cloudflare (dummy-token check); the deployed service rejected a missing and an invalid token with 403 `BOT_CHECK_FAILED`. A **valid** token has not been accepted yet: the widget refused `localhost` (error 110200) until hostnames are added in Cloudflare |
| Brevo | the API key is valid (account call 200 after the IP restriction was disabled); three test emails were accepted by Brevo from a local script. Delivery to inboxes and sending **from the deployed app** are unverified. The sender is a Gmail address, which gets no SPF/DKIM alignment |
| Git | repository pushed to `github.com/syedvpd/coralswift-backend` (`main`); the gap-closure changes in the working tree are **uncommitted and unpushed** |

## Not verified
Real Brevo delivery from the app; a Turnstile pass; GitHub Actions result; Render blueprint validity; staging environment (database, buckets, domain); live role/MFA accounts (X14); CORS preflight against the deployed origin; production TLS, proxy rate limiting and request-size limits; backups and restore (one manual development dump, restore-tested once, earlier); monitoring and alerting (none).

## Configuration
- Staging and production start-up enforce: strong `SECRET_KEY`, `DEBUG=false`, explicit CORS and hosts, S3 + buckets, Brevo + sender, `STAFF_MFA_REQUIRED`, `CAPTCHA_ENABLED=true` with a Turnstile secret; staging also needs `EMAIL_RECIPIENT_ALLOWLIST`. Tested in `tests/unit/test_config.py`.
- Environment names per environment: `docs/deployment/staging-release-checklist.md` section B. `.env` and `.env.render` are git-ignored.
- Effective security policy readable by super administrators: `GET /admin/security-policy`.

## Security posture
Org isolation, strategic/M&A confidentiality, role matrix and token handling are covered by automated tests (see the test report). Uploads are quarantined and never scanned: the owner accepted this on 2026-11-10; no document may be described as scanned or clean. Passwords never leave the system; admins can only email reset links.

## Required before go-live
1. **Rotate** the Supabase database password and S3 keys (pasted in chat), the Brevo key and the Turnstile secret (also pasted in chat). Use separate credentials per environment.
2. Own a domain: Brevo sender authentication (SPF, DKIM, DMARC), frontend and API hostnames, Turnstile hostnames, `CORS_ALLOWED_ORIGINS`, `ALLOWED_HOSTS`.
3. Staging: separate database and private buckets; apply `alembic upgrade head` (revision `0011`) only after a backup and target confirmation; run the 12 scenarios in `staging-release-checklist.md`.
4. Production backups with a tested restore; monitoring, uptime checks, error tracking; incident owner.
5. Decisions D1-D27 (`business-decisions-required.md`), at minimum D3 (queue owners/SLA/contact) and D4 (retention and privacy).
6. A green GitHub Actions run and the code-complete items listed as NOT CLOSED in `backend-gap-audit.md`.

## Migration status
Head is `0011`. Local disposable databases: applied. Supabase development database: still at `0010` (no migration applied in this work). Production: none.
