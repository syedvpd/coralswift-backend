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
