# Backend Gap Test Report (2026-11-10)

All runs: local Docker PostgreSQL (disposable `*_test` databases), in-memory storage, fake email, mocked Cloudflare. **No** Supabase, Brevo, Turnstile, Render or GitHub Actions run was made. Mocks are not evidence of live behaviour.

## Final commands and results (run once at the end, after the last code change)
| Check | Command | Result |
|---|---|---|
| Lint | `ruff check .` | All checks passed |
| Format | `ruff format --check .` | 218 files already formatted |
| Types | `mypy` | no issues in 173 source files |
| Tests | `pytest -q` | **254 passed, 0 failed**, 1 Starlette `httpx` deprecation warning (74.6 s) |
| Fresh-database migration | `alembic upgrade head`, `current`, `check` on an empty scratch database created on the local Docker server, then dropped | `upgrade` exit 0; `current` = `0011 (head)`; `check` = no new upgrade operations |
| Test-database drift | `scripts/alembic_test_db.py check` / `heads` | no drift / `0011 (head)` |
| OpenAPI generation | `create_app().openapi()` | valid 3.1.0 document, 134 paths, 218 schemas, written to `docs/api/openapi.json` |
| Docker | `docker build`; `docker run --entrypoint id <image> -u` | image builds; uid 10001 |
| Not run | Docker container health against a database, GitHub CI, Render, any provider, load test | - |

Progress runs during the work: 211, 214, 219, 222, 223 (earlier sessions), 253 (before the last additions), 254 final.

## New and changed test files
| File | Covers |
|---|---|
| `test_strategic_confidentiality.py` (3) | every admin/reviewer GET for BDM, reviewer, content admin; search, CSV, detail, documents, follow-up and assign attempts; aggregates |
| `test_gap_phase_a.py` (7) | change-password (staff and partner, session revocation), token failure reasons, deactivated login, permission matrix == enforcement, audit actor names / `is_strategic` / search / sort, typed outbox rows |
| `test_gap_accounts.py` (6) | assignee picker, account list filters and sort, invitation lifecycle, suspend/reactivate/reset, self-protection, rate limit (429) |
| `test_gap_enquiries.py` (4) | enquiry row contract and filters, follow-up kinds/owner/update/cancel, global follow-ups with strategic isolation, activity feed |
| `test_gap_applications.py` (3) | reviewer list contract and filters, transition table, clearing assignment, actor names |
| `test_gap_lists.py` (5) | pagination meta sweep over every list, user and organisation lists, partner inbox isolation and read state, content sort/dates, CSV cap |
| `test_gap_reference.py` (3) | document queue scope and filters, typed settings/launch readiness, security policy |
| updated: `test_auth.py`, `test_config.py`, `test_app.py` | new error codes, staging/CAPTCHA rules |

## Defects found by the tests and fixed
1. `GET /reviewer/applications?pathway=` accepted any text and returned a 500 for an unknown value (now an enum, 422).
2. Privacy-request and profile-change lists returned no `total`/`pages` and the change-request list was unpaginated.
3. The enquiry CSV export raised a 500 after the shared filter gained `sort` (fixed; covered by the strategic and CSV tests).
4. Audit/outbox pages could reorder rows sharing one timestamp; an `id` tie-breaker was added.

## Security-focused regression
IDOR and organisation isolation (`test_security_p2`, `test_partner_documents`, `test_gap_lists` inbox), privilege escalation and role separation (`test_gap_phase_a` matrix, `test_gap_accounts`), mass assignment (`extra="forbid"` bodies, `422` on unknown fields), unauthorised exports (`test_strategic_confidentiality`, `test_admin`), invalid transitions (`test_transitions`, `test_gap_applications`), token replay/expiry/revocation (`test_gap_phase_a`, `test_gap_accounts`), concurrency (`test_concurrency_p2`, `test_idempotency`), rate limits (`test_gap_accounts`, `test_security_p2`).

## Limitations
- Concurrency tests for the new follow-up and assignment operations were not added; existing row locks (`FOR UPDATE`) are used but not stress-tested.
- No test sends real email or contacts Cloudflare; Turnstile and Brevo remain mock-only.
- Migration `0011` was applied only to local disposable databases.

## Claude Code continuation (2026-11-10)
Verified 2026-11-10 (Claude Code): branch `main`, HEAD `15ebe59`; the working tree is uncommitted and holds the earlier agent's 34 modified files plus this session's changes. Supabase dev (`postgres.zibfzlwzaecapfrgjret`) is at `0012` with no drift (read-only check). **Migrations `0013`, `0014`, `0015` exist and are applied to local disposable databases only; they are NOT applied to Supabase** (needs a fresh approval, a backup and target confirmation).

| Check | Result |
|---|---|
| Baseline of the uncommitted tree before my changes | 250 passed, **7 failed** (null keys in typed responses; 500 in `/admin/reports/follow-ups`) |
| After fixing those | 257 passed |
| Final `pytest -q` (after Phase 1-3 work) | **270 passed, 0 failed** (162 s) |
| `ruff check .` / `ruff format --check .` / `mypy` | clean / 241 files / 180 source files |
| Fresh empty database, `alembic upgrade head`/`current`/`check` | exit 0 / `0015 (head)` / no drift |
| OpenAPI | regenerated: 3.1.0, 158 paths, 276 schemas (`docs/api/openapi.json`) |
| Docker | image builds; uid 10001 |
| Supabase | read-only verification only (revision `0012`, six columns present, no drift); nothing applied |
| Not run | GitHub CI, Render, live Brevo/Turnstile, container health with a database |

New tests this session: `test_phase1_seo_privacy.py` (4), `test_phase2_account.py` (4), `test_phase2_privacy.py` (1), `test_phase2_document_requests.py` (2), `test_phase3_feed.py` (2); updated `test_content_engagement.py`, `test_section28.py`, `test_gap_accounts.py`, `test_admin.py`, `test_ops.py`, `test_gap_lists.py`.

## Second pass (2026-11-10, local only)
| Check | Result |
|---|---|
| `pytest -q` (full) | **273 passed, 0 failed** (125 s) |
| `ruff check` on `app`, `tests`, `migrations` and the maintained scripts / `ruff format --check` / `mypy` | clean / 245 files / 182 source files |
| `ruff check .` | **17 E402 errors in `scripts/inspect_and_seed.py`**, a file added by another agent after my last run (not mine, not edited; it also targets the `.env` database, so it was not run) |
| Fresh empty database `alembic upgrade head` / `check` | exit 0, head `0015`, no drift |
| OpenAPI regenerated | 162 paths, 280 schemas |
| Not run | GitHub CI, Render, live providers, anything on Supabase |
New tests: `test_phase3_org_history.py` (3). Changed: `test_gap_lists.py`.

## Third pass (2026-11-10): review of inherited work, local only
New `tests/api/test_review_inherited.py` (7 tests, passed): audit detail/actions/CSV authorisation and CSV safety, workload counts and strategic exclusion, document-history scoping, follow-up reports (strategic excluded for BDM, other roles denied), scheduled-publication negatives (draft, past, role, drafts never auto-published), field metadata / template placeholders / typed organisation detail (financial fields null for BDM), `discussion_type` filter. The five remaining untyped endpoints (`/auth/permissions`, `/catalog/*`, `/content/sitemap`, `/reviewer/transitions`) now have Pydantic schemas. One regression found and fixed (permissions response must omit `role_matrix` for non-super roles). OpenAPI: 162 paths, 291 schemas.

## Current takeover verification (2026-11-11)
- Remote development migration: `0012` before; applied `0013`, `0014`, `0015`; `0015` after. `alembic check`: no drift. Schema object verification is recorded in `docs/handoff/SUPABASE_MIGRATION_PLAN.md`. No backup was created, per owner instruction.
- Local full regression: `280 passed, 0 failed`, one Starlette/httpx deprecation warning (184.32 s), using the local disposable test database. An earlier run without network access failed during fixture setup and is superseded by this run.
- Ruff check: passed. Ruff format check: 245 files formatted. Mypy: no issues in 183 source files.
- Live provider tests, frontend browser flow and deployment were not performed.

## Verification (2026-11-11 requirements batch)
Baseline before changes: full suite `333 passed` (local Postgres in Docker, database name ending `_test`). Changes: `ACCOUNT_LOCKED`, `GET/PATCH /admin/users/{id}`, `GET /admin/users/{id}/activity`, `GET /reviewer/workload`, `scan_status`. Final results are in the session report; see `docs/frontend-backend-requirements-tracker.md`.
Final gates (2026-11-11): `ruff check` pass; `ruff format --check` 252 files clean; `mypy` 186 files no issues; `alembic heads` 0015 and `alembic check` "No new upgrade operations detected" on the local disposable DB; app builds; full `pytest`: **336 passed** (333 baseline + 3 new; two existing lock-out assertions were changed to the new 423 `ACCOUNT_LOCKED`). OpenAPI regenerated locally: 165 paths / 297 schemas. Not run: any live/remote check, deployed OpenAPI republish, remote DB revision check.
