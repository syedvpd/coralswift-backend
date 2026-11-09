# Phase 1 Verification and Acceptance Report

**Verification date:** 2026-11-09  
**Repository revision:** unavailable; this directory has no `.git` metadata (`git rev-parse HEAD` failed).  
**Environment:** Windows, Python 3.12.10, project virtual environment, Ruff 0.17.4, MyPy 2.4.1, pytest 9.2.0.  
**Database safety:** before each run, the effective `TEST_DATABASE_URL` was checked without displaying credentials. It resolved to `localhost:5433/coralswift_test`; read-only queries confirmed `current_database() = coralswift_test`, loopback target, no Supabase host, separation from the development target, CONNECT privilege, and public-schema CREATE privilege. `.env` values were not displayed.

## Acceptance decision

**FAIL — PHASE 1 NOT ACCEPTED**

This remains the broader Phase 1 acceptance decision; this task covered automated regression only. Static checks and the full test suite pass, but real S3/Brevo integrations, live deployment checks, bucket privacy, and business-owned dependencies remain unverified. The historical README result (111 passed, 1 failed) was superseded by the current runs below. Phase 2 remains **NOT STARTED** and is not authorized by this audit.

## Stage 1: repository and configuration

- Inspected the repository tree, README, architecture overview and ADR, backend standards, requirements register, Phase 1 test strategy, API contract, data model, application factory, settings, DB fixtures, Docker files, dependencies, and migrations.
- The directory is not a Git checkout; commit identity and tracked-file state cannot be confirmed.
- `.env` exists locally and `.gitignore` excludes `.env` and `.env.*`, with `.env.example` allowed. No `.env` values were printed.
- Pytest fixture guard checks that the configured `TEST_DATABASE_URL` database name ends in `_test` before its session migration fixture upgrades to head. The configured name and host resolve to `coralswift_test` and loopback. A live connection attempt failed with `OperationalError`; the database was unavailable. Docker Compose also failed because access to the Docker API is denied.
- Python 3.12 compatibility is declared (`>=3.12`) and the active interpreter is 3.12.10.
- `pyproject.toml` initially had a UTF-8 BOM, rejected by `tomllib.loads()`; removed the BOM and confirmed it parses with Python's standard TOML parser.
- Import paths use `app.main:create_app` with `--factory`; settings are Pydantic Settings and required DB/secret fields have no defaults. Secrets are represented by `SecretStr`; production settings require explicit secure choices.
- `.gitignore` excludes common Python caches and `.env`; `.dockerignore` excludes tests/docs/caches and `.env`.

## Stage 2: static checks

Final commands were executed from the repository root after fixes:

| Command | Result | Evidence |
|---|---|---|
| `.venv\Scripts\ruff.exe check .` | Pass, exit 0 | “All checks passed!” |
| `.venv\Scripts\ruff.exe format --check .` | Pass, exit 0 | 100 files already formatted |
| `.venv\Scripts\mypy.exe .` | Pass, exit 0 | 91 source files, no issues |
| Python `tomllib.loads()` on `pyproject.toml` | Pass | Parsed project metadata and Python requirement |

Before fixes Ruff found five line-length errors. MyPy found four errors: two untyped boto imports, a FastAPI `responses` mapping annotation mismatch, and an obsolete unused type-ignore. Those were addressed with narrowly scoped changes. Ruff formatting was applied to the modified regression test. No broad lint suppression or dependency was added.

## Stage 3: tests and regression coverage

**Executed twice successfully.** See section G for pre-test safety evidence, exact commands, exit codes, counts, the warning, and regression areas exercised. The fixture upgraded only the guarded `coralswift_test` database; per-test transactions rolled back, and the committed concurrency test removed only its own keyed idempotency row.

## Stage 4: migrations and database

Code inspection confirms revisions `0001 -> 0002 -> 0003`, with `0003` as the repository head. `0001` is an empty baseline; `0002` creates Phase 1 entities, constraints, indexes, and `enquiry_reference_seq`; `0003` adds nullable `documents.retention_date`. The reviewed downgrade functions reverse only their own revision's objects. Models and migration files indicate unique reference numbers, idempotency scope/key uniqueness, outbox deduplication, document storage-key uniqueness, FK relationships, timezone-aware timestamps, and constraints for core fields.

The test fixture successfully ran `alembic upgrade head` against `coralswift_test` before both runs, so the disposable test database reached repository head. This is not evidence about Supabase: no command connected to or changed the development database. A separate live schema-drift check (`alembic check`) and applied-revision query against Supabase were not performed.

## Stage 5: endpoints and live server

The full API/integration suite ran through TestClient against the guarded test database. Submission validation, status token behavior, strategic confidentiality, upload validation/failure paths, idempotency, rate limits, and no-public-download behavior all passed their automated tests. This is test-client verification, not a separate live-server or production deployment check. No raw storage retrieval endpoint is present in the documented API contract.

## Stage 6: security review

Code inspection indicates request IDs, a central error envelope, body-size middleware, security headers, trusted-host checks, CORS origin restrictions, HMAC status lookup tokens, payload validation, idempotency, server-generated document keys, and private-storage adapter APIs. These controls were not fully exercised end-to-end.

**Finding fixed and regression verified:** CORS previously allowed only Authorization, Content-Type, and request ID. Browser callers could not preflight Phase 1's `Idempotency-Key`, `X-Bot-Token`, or `X-Lookup-Token` headers. Added the three headers and the `tests/api/test_app.py` regression test; both full test runs passed it.

**External/security dependencies:** the default bot verifier is a no-op, so bot-check rejection is not active until a provider is configured. Rate limiting is per-process and the API contract documents that production enforcement must also exist at the proxy/CDN. TLS and request-size limits at the edge require deployment verification. Strategic confidentiality and status/document access tests passed in the automated suite. Log redaction and infrastructure controls still need separate operational review. No claim of complete security verification is made.

## Stage 7: external integrations

- Local storage adapter: temporary write/exists/delete check passed using a workspace-local temporary directory; the temporary files were removed.
- S3: adapter inspected only; no real reads/writes/deletes were made. Real S3 behavior is unverified. Owner must confirm `coral-swift-enquiry-attachments` and `coral-swift-partner-documents` are private in the Supabase dashboard.
- Email: automated tests for template rendering, outbox queueing, provider failure/retry, retry cap, and console logged-not-sent behavior passed. No real email was sent; real Brevo delivery and DNS authentication remain unverified. Console remains the documented configured backend.
- Redis: optional `jobs` profile is not verified; Docker is unavailable and the application does not currently use Redis.

## Stage 8: Docker and server

Docker daemon and Compose status checks succeeded outside the network sandbox; Compose reported the database and API containers healthy. Docker image rebuild, non-root runtime inspection, lifecycle behavior, and a separate live endpoint sweep were not performed. No ports or environment configuration were changed.

## Stage 9: Phase 1 requirements traceability

The requirements register contains an evidence-based status snapshot from the initial audit before database recovery. This report’s section G records the later passing automated regression run; it does not independently verify external integrations or satisfy the broader Phase 1 acceptance gate.

## Stage 10: fixes

1. **TOML parser compatibility:** removed the UTF-8 BOM from `pyproject.toml`; standard parser validation now passes.
2. **Ruff line-length errors:** shortened comments/docstrings and wrapped the idempotency header description in the email, document, notification, and submission modules.
3. **MyPy errors:** narrowed third-party import ignores for untyped boto packages, corrected the FastAPI response mapping key annotation, and removed an obsolete ignore.
4. **CORS preflight:** allowed the three Phase 1 custom headers and added `test_cors_allows_phase_1_custom_headers`.

The final static suite passes. The CORS fix and existing Phase 1 behavior were regression-tested in both full-suite runs; no failures required additional fixes.

## Remaining blockers

- The automated regression suite is green. Coverage was not requested or run.
- A live-server sweep and Docker image/non-root/lifecycle verification remain open.
- Re-run migration status/schema checks only against approved targets; no Supabase mutation is authorized.
- Business/external owners must confirm private bucket policies, provide/configure Brevo and DNS authentication, choose CAPTCHA/bot-check integration, approve privacy notice/retention rules, and name notification owners/recipients.
- Repository revision cannot be reported until Git metadata is available.

**Phase 2 gate:** not met. Phase 2 — Partner Portal Backend remains **NOT STARTED**.



## G. Automated regression execution (2026-11-09)

### Pre-test safety confirmation

- Effective test configuration source: `.env` (no credentials or complete URL displayed).
- Configured target: `localhost:5433`, database `coralswift_test`; loopback and not Supabase. Its host/port/database tuple differs from the development target.
- Read-only identity query returned `current_database() = coralswift_test`. The test user has database CONNECT and `public` schema CREATE privileges required for the fixture's migration upgrade.
- Fixture review: `tests/conftest.py` refuses URLs whose DB name does not end in `_test`; it sets `DATABASE_URL` to the test settings before Alembic `upgrade head`. It does not downgrade or drop tables. API fixtures roll back an outer transaction. Two concurrency tests use committed connections: idempotency deletes only its own UUID-keyed test row; reference uniqueness only advances the disposable DB sequence. Other explicit deletes in tests are constrained to records created by the test.
- All test database-changing operations in this run were directed to `coralswift_test`. No Supabase connection was made.

### Commands and outcomes

Both invocations used `.venv\Scripts\pytest.exe -q` (the repository virtual environment equivalent of `pytest -q`), from the repository root, with loopback access enabled for the confirmed test DB.

| Run | Exit code | Passed | Failed | Skipped | Result |
|---|---:|---:|---:|---:|---|
| Initial complete run | 0 | 113 | 0 | 0 | Pass; 13.27s |
| Final complete rerun | 0 | 113 | 0 | 0 | Pass; 13.17s |

Each run emitted one `StarletteDeprecationWarning`: Starlette's current `TestClient` integration warns that using `httpx` is deprecated and suggests `httpx2`. It did not fail a test. There were no failing tests, so no test failures required root-cause fixes.

The passing suite includes the email provider-failure/retry-success and retry-cap cases; CORS custom-header preflight; idempotency replay, payload mismatch, in-flight and concurrent claims; concurrent reference uniqueness; upload type/size/path traversal/storage failure cases; status token failure equivalence and rate limiting; and strategic confidentiality/no public read API.

### Result and remaining unverified areas

**Automated regression result: PASS — 113 passed, 0 failed, 0 skipped, exit code 0 on both runs.** No application or migration files were changed during this task.

This automated result does not accept Phase 1. Real S3 access and bucket privacy, real Brevo delivery/DNS, malware scanning and retention policy, business routing/privacy decisions, separate live-server checks, production infrastructure controls, and the broader acceptance gates remain unverified or externally dependent. The overall acceptance decision remains **FAIL — PHASE 1 NOT ACCEPTED** pending those gates.


## H. Re-review against the Phase 1 blockers (2026-11-09, after the final verification cycle)

Evidence source: `docs/qa/final-backend-test-report.md` (211 tests passed; this file's 113 are a subset superseded by it) and the Supabase dev checks in `docs/qa/final-backend-completion-report.md`. This section re-reads the section "Remaining blockers" above. Nothing was re-run for this review.

| Blocker from above | Now | Evidence |
|---|---|---|
| Live-server endpoint sweep | CLOSED (dev DB) | live `uvicorn` against Supabase dev: public routes 200, protected route 401 |
| Docker image, non-root, lifecycle | CLOSED | build OK, uid 10001, `/health/live` 200, `/health/ready` 503 without DB |
| Migration status / drift on a real target | CLOSED (dev only) | Supabase dev at 0010, `alembic check` clean; backup taken and restore-tested first |
| Real S3 read/write/delete | CLOSED (dev buckets) | put/get/exists/delete of dedicated test objects on both buckets, then removed |
| Bucket privacy | PARTLY CLOSED | anonymous public URL returned HTTP 400 (not served) on both buckets; owner dashboard confirmation not obtained |
| Real Brevo delivery + SPF/DKIM/DMARC | OPEN | no key or sender domain; mocked transport only |
| CAPTCHA / bot-check provider | OPEN | no-op verifier; rate limiting only |
| Malware scanning | OPEN | all uploads stay `quarantined` |
| Retention rules, privacy notice text, notification owners/recipients | OPEN | business decisions; purge job inert until retention is set |
| Edge TLS, proxy/CDN rate limit, request-size limit | OPEN | needs a deployed environment |
| Repository revision | OPEN | not a git repo |
| Full Phase 1 journeys against the real stack | OPEN | tests ran on local DB only; Supabase got schema, smoke and storage checks |

### Decision
**FAIL - PHASE 1 NOT ACCEPTED (unchanged).** Engineering blockers are closed on the dev stack. Remaining blockers need external providers, business decisions or a deployed environment, none of which exist yet. Suggested path to acceptance: configure Brevo and send one test mail to an internal inbox; choose CAPTCHA and a scanning approach (or formally accept quarantine-only uploads); owners approve retention, privacy notice and recipients; confirm bucket privacy in the Supabase dashboard; put the code in git; re-run the Phase 1 journeys on a deployed staging environment. Acceptance itself is the owner's decision.


## I. Final audit note (2026-11-09)
Rerun in the audit: ruff, format, mypy, full pytest (214 passed, includes the Phase 1 tests), `alembic check` (local). Section H stands; no criterion changed state, except: CAPTCHA now has a Cloudflare Turnstile verifier (mock-tested, inactive without `TURNSTILE_SECRET_KEY`, not verified against Cloudflare). Brevo keys are expected 2026-11-10. **FAIL - PHASE 1 NOT ACCEPTED (unchanged).** Remaining owner actions: Brevo test mail; Turnstile keys; scanner decision or formal acceptance of quarantine-only uploads; retention, privacy notice and recipients approval; bucket privacy confirmation in the dashboard; git; staging journey run.

### I.2 Corrections (2026-11-09)
Latest local run: 219 passed. Turnstile now needs `CAPTCHA_ENABLED=true` plus `TURNSTILE_SECRET_KEY`, and production configuration refuses to load without both; the integration is still mock-tested only. Decision unchanged: **FAIL - PHASE 1 NOT ACCEPTED**.
