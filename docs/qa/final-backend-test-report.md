# Final Backend Test Report (2026-11-09)

All runs used the local Docker PostgreSQL (`coralswift_p2_test`, plus `coralswift_p2_conc_test` for real-commit concurrency tests). Nothing ran against Supabase data. Repository revision unavailable (not a git checkout).

## Results
| Check | Command | Result |
|---|---|---|
| Tests | `pytest -q` | **211 passed, 0 failed, 0 skipped** (63.9 s); 1 Starlette `httpx` deprecation warning |
| Lint | `ruff check .` | All checks passed |
| Format | `ruff format --check .` | 195 files already formatted (as recorded then; the audit rerun below shows 198, so the earlier count was not copied from the final state) |
| Types | `mypy` | Success, no issues in 159 source files |
| Startup | `create_app()` import + live `uvicorn` | OK; `/health`, `/health/live`, `/health/ready`, `/api/v1/meta`, `/catalog/*`, `/content`, `/openapi.json` all 200; `/admin/overview` without token 401 |
| Alembic (local test DB) | `current` / `heads` / `check` | `0010 (head)` / `0010 (head)` / no drift |
| Docker | `docker build`; `docker run` | image builds; runs as uid 10001 `appuser`; `/srv/var/storage` writable; honours `$PORT`; `/health/live` 200; `/health/ready` 503 when the DB is unreachable |

## Test counts by area
Phase 0/foundation: `test_app` 12, `test_health` 4, `test_config` 12, `test_logging_security_pagination` 7, `test_database` 6, `test_adapters` 6.
Phase 1: `test_contact` 12, `test_project_partner_strategic` 21, `test_documents_status_security` 17, `test_idempotency` 10 (includes concurrent claims and reference numbers), `test_notifications` 6.
Phase 2: `test_auth` 16, `test_mfa` 7, `test_organizations` 5, `test_partner_documents` 7, `test_applications` 5, `test_reviewer` 6, `test_transitions` 9, `test_security_p2` 7 (anonymous sweep of every protected route, IDOR matrix, role separation), `test_audit_e2e` 2 (immutable audit table, full partner journey), `test_concurrency_p2` 6.
Phase 3 and s.28: `test_admin` 7, `test_content_engagement` 6, `test_ops` 7, `test_section28` 8 (claims gate, routing/SLA/backup owner/ack promise, escalation, failure visibility, launch gate, catalog, privacy deletion, MFA recovery).

## Defects found and fixed during this cycle
1. Follow-up completion did not clear `next_follow_up_at` (sessions run with autoflush off; recompute query ran before the flush). Fixed with an explicit flush.
2. `EnquiryDetail` failed to serialise follow-ups (missing `from_attributes`). Fixed.
3. Claims were pulled from the site even when they had never been cleared. Fixed: only a claim that was cleared and then un-cleared pulls content.
4. Deprecated `ARRAY.any()` replaced with `any_()`.
5. Outdated or mistaken tests corrected, not weakened: template-key assertion (new keys without a reference), public-route filter for the strategic no-read-API test, an unused throw-away mail fake.
6. Type-checking fixes for SQLAlchemy 2.1 `Select` generics and Response typing.

## Test-harness note
API tests nest every session in one outer transaction. An endpoint that does work in a *different* session while its auth dependency session is still open would be rolled back by the harness at teardown. `POST /admin/notifications/dispatch` is such a case (it runs the dispatcher in a background task); its effect is therefore asserted by calling the dispatcher directly. Production uses separate connections and is not affected.

## Not executed / not verifiable here
Real Brevo delivery (no key), CAPTCHA, calendar, malware scanning (none configured), GitHub CI run, Render deployment, load/performance, browser/accessibility tests (frontend).

## Audit rerun (2026-11-09, final evidence audit)
Files edited after the 211-run were not provably older than it, so the checks were rerun on the current tree; a Cloudflare Turnstile verifier (`app/integrations/botcheck.py`, 3 tests in `tests/unit/test_botcheck.py`) was added during the audit and the checks were rerun again.

| Check | Result |
|---|---|
| `pytest -q` before the Turnstile change | 211 passed, 0 failed (63.95 s) |
| `ruff check .` / `ruff format --check .` / `mypy` after it | all passed / 199 files formatted / no issues in 160 source files |
| `pytest -q` after it | **214 passed, 0 failed** (65.08 s), 1 Starlette `httpx` deprecation warning |
| `alembic_test_db.py current / heads / check` (local test DB) | `0010 (head)` / `0010 (head)` / no new upgrade operations |
| `create_app(load_settings())` | imports and builds without error |
| Not rerun | Docker build/run, live server, Supabase checks and storage round trip (results above are from the earlier run and were not repeated; no Supabase connection was made during the audit) |

## Corrections rerun (2026-11-09, latest local verification)
Changes since the audit rerun above: `CAPTCHA_ENABLED` setting and production rule, 5 new Turnstile/config tests, maintenance `--dry-run` (+2 tests), portal-adoption KPI (+1 assertion), one existing test updated.

| Check | Result |
|---|---|
| `pytest -q` after the CAPTCHA production rule | 1 failed, 218 passed: `test_app.py::test_docs_disabled_in_production` built production settings without CAPTCHA. The test fixture was corrected to supply `captcha_enabled` and a secret; the rule itself stayed. |
| `pytest -q` after the fix (**latest**) | **219 passed, 0 failed** (64.54 s), 1 Starlette `httpx` deprecation warning |
| `ruff check .` / `ruff format --check .` / `mypy` | all passed / 200 files formatted / no issues in 161 source files |
| `alembic_test_db.py check` / `heads` (local test DB) | no new upgrade operations / `0010 (head)` |
| `python scripts/run_maintenance.py --help` | prints usage with `--dry-run`, exit 0 (argparse exits before settings load; no database touched) |
| App startup with the real `.env` | OK; `captcha_enabled=False` (development), `NoopBotVerifier` |
| Not rerun | Docker, live server, Supabase, storage, any real Brevo/Turnstile call. `--dry-run` was **not** executed against Supabase. The dry-run test uses the local test DB and monkeypatches the script's settings/engine, so `.env` is never read. |

New tests: `tests/unit/test_botcheck.py` (5: success sends secret, fails closed on invalid/expired/provider error/garbage/no token, selection by `captcha_enabled`, API 403 `BOT_CHECK_FAILED` for missing/invalid/expired token and 201 for a valid one, all against a mocked Cloudflare); `tests/unit/test_config.py::test_captcha_rules`; `tests/api/test_maintenance_dry_run.py` (2: preview counts two overdue enquiries and changes nothing, the real escalation still finds both afterwards; the script's `--dry-run` never calls the real jobs, storage or email builders). The dry-run test does not cover the document-purge and expiry-reminder counters with data.

## Release preparation checks (2026-11-09, latest local verification)
Changes: `APP_ENV=staging` profile, `EMAIL_RECIPIENT_ALLOWLIST` guard, CI workflow additions, `.gitignore` additions, dry-run test with expiry/retention data.

| Check | Result |
|---|---|
| `pytest -q` (full) | **222 passed, 0 failed** |
| ruff / format / mypy | clean (see run output in the task summary) |
| `alembic_test_db.py check` / `heads` (local test DB) | no new upgrade operations / `0010 (head)` |
| `docker build` + `id -u` in the image | builds; uid 10001 |
| Docker `run_maintenance.py --help` and `--dry-run` against the **local test database** (via `host.docker.internal`) | both exit 0; dry run printed all-zero counters on the empty database |
| Secret scan of the 213 repository files (rules + literal `.env` values, locations only) | no live value of `DATABASE_URL`, `S3_*` or `SECRET_KEY` found; remaining matches are placeholders and fake test strings |
| Git | `git init -b main`; baseline commit `c9ea50634c7a41c6dd82acc143d6c30e4347afc7`; clean at commit time; the release-preparation changes listed above are uncommitted (no second commit was authorised) |
| Not executed | GitHub Actions run (no remote), `actionlint` (tool use was declined), Render validation, any staging scenario, real Brevo/Turnstile/storage, `--dry-run` or any job against Supabase |
