# Codex Handoff - Coral Swift Backend (written 2026-11-10)

Source-verified on this date against Git `main` at `15ebe59` (equal to `origin/main`), working tree clean before this handoff was written. The three files in `docs/handoff/` are the only uncommitted changes. Nothing here is a claim of completion: see the matrices.

**Current continuation state:** work since the original handoff remains uncommitted across application, tests and docs; migration `0012` is a local repository change only. The current progress matrix and end-of-section entries below supersede the historical baseline statements above.

## 1. Objective and scope
Coral Swift backend (FastAPI, PostgreSQL, SQLAlchemy 2, Alembic) for the PRD v2.0 website, partner portal and admin platform, **Phases 0-3 only**. Out of scope: Phase 4 ecosystem, payments, e-signature, ERP/CRM replacement, automated final decisions. The current task is closing the backend gaps in "Coral Swift - Backend Gaps (all sessions, Phase 1 to Phase 29)" (the register pasted by the owner; its items are reproduced with verified status in `docs/backend-gap-audit.md`). The register is an input, not proof: always verify against code.

## 2. Phase matrix (Phases 1-29 of the register)
All 29 were inspected. Status is derived from `CODEX_PROGRESS_MATRIX.md` rows (evidence there).
| Phase | Status | Notes |
|---|---|---|
| 1-3 auth/foundation | PARTIAL | change-password, token errors, deactivated-login done; CORS value (ops), session persistence (D1), live tests open |
| 4 dashboard | PARTIAL | decided_at, documents queue, list filters done; approved counts (D7), onboarding feed, typed overview/KPIs open |
| 5 applications | **COMPLETE** (no open code) | filters, contact, names, transitions table |
| 6 review/decision | PARTIAL | actor names/updated done; checklist, recommend, reversal, approved status, exceptions blocked on D5-D11 |
| 7 onboarding/provisioning | PARTIAL | invitation state, mandatory docs verified; onboarding model blocked (D10) |
| 8 enquiries | PARTIAL | row contract, filters, activity, note kinds, assignees done; typed detail objects open; status workflow (D8) |
| 9 strategic | PARTIAL | confidentiality fully tested; `discussion_type` filter, outcome statuses (D8), typed objects open |
| 10 assignment | PARTIAL | history, clear reviewer, filters done; workload endpoint open; capacity (D13) |
| 11 follow-ups | PARTIAL | list/update/cancel/counts done; external reply (D15), follow-up notifications, calendar (D16) open |
| 12 documents | PARTIAL | admin queue done; staff review history, attachment list open; admin upload (D17); scanning declined |
| 13 partner management | PARTIAL | filters/sort/contact and typed detail done; org activity open; D19-D21 |
| 14 partner accounts | MOSTLY COMPLETE | list/detail/invite/suspend/reset and account metrics implemented; tests unverified |
| 15 communications | PARTIAL | outbox filters/typed; template versions and placeholder list implemented; staff in-app feed open; receipts external |
| 16 CMS | PARTIAL | sort/dates, permissions and scheduled publication implemented but untested; media library blocked on D23; SEO is frontend per PRD |
| 17 users/roles | MOSTLY COMPLETE | staff full-name self-update implemented; email change verification and permission editing D25 remain |
| 18 reports | PARTIAL | typed KPIs and aggregate account/follow-up/document/communication reports implemented; tests unverified; onboarding metrics D10 |
| 19 audit/settings | PARTIAL | search/sort/actor names, typed settings, policy API; audit detail, action catalogue and CSV implemented; other audit fields open |
| 20-21 integration/readiness | VERIFIED EXISTING / BLOCKED | mostly decisions and external setup |
| 22-23 partner auth | COMPLETE except decisions D1, D2 | |
| 24 invitation | MOSTLY COMPLETE | latest invitation outbox status/time appears on account rows; tests unverified |
| 25 partner dashboard | PARTIAL | inbox and `/auth/me` account status done; document-request resource blocked on D10 |
| 26 company profile | PARTIAL | editable metadata, revision history and null-clearing done; extra fields blocked on D20 |
| 27 partner documents | PARTIAL | operation hints implemented; request resource remains blocked on D10 |
| 28 status tracking | PARTIAL | `last_updated`/`decided_at` exposed; eligibility outcome/reason blocked on D27; D10 timestamps open |
| 29 onboarding | NOT STARTED | blocked on D10 |

**Last module worked on:** reference/policy endpoints (`reference_router.py`), then documentation. Nothing was in progress when stopped; no half-written file exists.

## 3. X1-X14 and M1-M12
Exact per-item status: `CODEX_PROGRESS_MATRIX.md` (rows X1-X14, M1-M12, A26.x). Summary: **closed** X1, X2, X4, X6, X7, X8, X11, M1, M2, M3, M4, M8, M10; **open (code)** X3, X5 (enquiries part, plus D8), M5, M6; **blocked decision** X10, X13, M7, M9, M11 (decision part), M12; **blocked external** X9, X14; **not applicable (owner declined)** X12.

## 4. What exists (files, endpoints, schemas) - commit 15ebe59
New: `app/modules/admin/{lookups,people_router,followups_router,reference_router}.py`, `app/modules/auth/permissions.py`, `migrations/versions/20261110_0011_gap_closure_columns.py`, tests `tests/api/test_{strategic_confidentiality,gap_phase_a,gap_accounts,gap_enquiries,gap_applications,gap_lists,gap_reference}.py`, docs listed in section 13.
Modified: `api/v1/router.py` (registers new routers), `admin/{models,schemas,service,router,ops_router}.py`, `auth/{models,schemas,service,router,dependencies}.py`, `applications/transitions.py`, `reviews/{router,schemas,service}.py`, `content/{router,service}.py`, `engagement/{router,service}.py`, `organizations/extras.py`, `notifications/models.py`, `tests/api/test_auth.py`.
Endpoints added: `POST /auth/change-password`; `GET /auth/permissions`; `GET /admin/assignees`; `GET /admin/accounts`, `/{id}`; `POST /admin/accounts/{id}/{invitation/resend,invitation/revoke,password-reset,suspend,reactivate}`; `GET /admin/follow-ups`; `PATCH /admin/enquiries/{id}/follow-ups/{fid}`; `POST .../{fid}/cancel`; `GET /admin/enquiries/{id}/activity`; `GET /reviewer/transitions`; `GET /admin/documents`; `GET /admin/security-policy`; `POST /partner/notifications/{id}/read`, `/read-all`. Changed contracts (all listed with schemas in `docs/frontend-backend-contract.md` and `docs/api/openapi.json`): enquiry list/CSV filters and row fields; follow-up in/out; reviewer list and detail; audit and outbox rows; users and organisations lists; settings and launch readiness; partner notification and enquiry rows; privacy and profile-change lists now paginated.
Models/DB (0011, all nullable or defaulted): `auth_tokens.revoked_at`, `notifications.read_at`, `enquiry_followups.kind` (default `follow_up`, CHECK note|follow_up|communication), `enquiry_followups.assignee_id` (FK users, indexed), `enquiry_followups.cancelled_at`. Behaviour changes: token replay returns `TOKEN_ALREADY_USED`; superseded token is `revoked_at` not `used_at`; deactivated login with right password is 403.
Planned but never implemented: see `NOT CLOSED` rows in the matrix.

## 5. Architecture and conventions (extracted from the code)
- **Layout:** `app/modules/<module>/{constants,models,schemas,service,router}.py`; `app/core` (config, errors, protection, logging, security), `app/common` (responses, pagination, idempotency, validation), `app/database`, `app/integrations` (email, storage, botcheck adapters). All routers are included in `app/api/v1/router.py`. FastAPI here uses lazy included routers: **do not walk `app.routes`**; use the OpenAPI document or `auth/permissions.py`.
- **Layers:** router (auth, validation, response shaping) -> service (rules, transactions, audit) -> SQLAlchemy models. No repository layer. Sync SQLAlchemy 2.1, psycopg 3. Per-request session `DbSession`; services `db.commit()` explicitly; autoflush is off, so `db.flush()` before a query that must see pending changes.
- **Auth/authz:** `AuthDep`, `PendingAuthDep` (MFA-pending), `PartnerDep`, and `require_staff(*roles)` (sets `.allowed_roles`); per-file aliases `AdminDep` (super admin + BDM), `ReviewerDep` (reviewer + super admin), `SuperAdminDep`, `ContentAdminDep`. Partner org comes from the token only. Foreign ids return 404, not 403. Strategic/M&A restriction is applied in queries (`visible_types`, `get_visible`), never by hiding fields. Financial fields are super-admin only.
- **Envelope and errors:** `ok(data, message, meta)` returns `ApiResponse`; errors are `AppError(message, status_code=, code=)` (`NotFoundError`, etc.), UPPER_SNAKE codes, 404/409/422 conventions, `extra="forbid"` request models, never a stack trace.
- **Pagination/filter/sort:** `PageDep` + `page_meta(page, total)` -> `{page,page_size,total,pages}`; sort values are a `Literal[...]` mapped through a dict of order-by tuples with an `id` tie-break (422 on unknown value); search uses `_like()` escaping with `ilike(..., escape="\\")`; `*_from` inclusive, `*_to` exclusive.
- **Audit:** `log_activity(db, record_type, record_id, action, meta, ActorType, actor_user_id=, organization_id=)`; actions like `admin.*`, `auth.*`, `application.*`; `meta` never holds PII, secrets or free text. `activities` is append-only (DB trigger).
- **Notifications:** `queue_notification(..., dedupe_key=)` writes the outbox in the same transaction; `dispatch_notifications` runs as a background task or the maintenance job.
- **Migrations:** `migrations/versions/YYYYMMDD_NNNN_slug.py`, `revision = "NNNN"` zero-padded, additive, `op.f("...")` for constraint/index names (naming convention is on the metadata), enums stored as VARCHAR + CHECK (`enum_column`). Never edit an applied migration. Guard script `scripts/alembic_test_db.py` only touches a local `*_test` database.
- **Tests:** `tests/api/test_<area>.py`, `tests/unit`, `tests/integration`; fixtures `client`, `db`, `settings`, `email` (RecordingEmail), `storage`, `app_factory`; helpers in `tests/helpers.py` (`make_staff`, `login`, `bearer`, `onboard_partner`, `submitted_application`, `staff_headers`, `PASSWORD`) and `tests/factories.py`. All tests share one connection in an outer transaction with savepoints (created_at is constant inside a test, so order by id tie-break; background-task commits are asserted by calling the function). Concurrency tests use `<name>_conc_test`.
- **Style gates:** ruff (line length 100, includes S105-style secret-literal rules: avoid string literals in names containing "password"), `ruff format`, strict mypy. SQLAlchemy 2.1 typing uses `Select[Model]` (not `Select[tuple[Model]]`) and `Row[A, B]`. Typed sort dicts `dict[str, tuple[Any, ...]]`.
- **Strategy used:** read the relevant router/service first (grep, then targeted reads), extend the existing function or schema instead of adding a parallel one, keep new fields optional with defaults for backward compatibility, apply changes with a small patch script (not shell heredocs with quotes), run ruff -> mypy -> focused pytest per batch, full suite at the end. Business-decision items are recorded in `docs/business-decisions-required.md` and left `BLOCKED-DECISION`; external services get adapters with mocks and are labelled unverified.
- **Tooling gotchas:** Docker Desktop must be running for the local PostgreSQL (`docker compose up -d db`, port 5433); `python - <<'EOF'` with quote-heavy bodies can fail in this shell - write a script file; `ruff format` rewrites lines, so string-replace patches must re-read the file; `+` in an ISO timestamp query string must be percent-encoded (use `params=`).

## 6. Business rules and security (do not weaken)
No auto-approve/reject from form values; eligibility is a human record. Strategic/M&A and financial documents restricted by role at query level; BDM sees neither (D12). Uploads stay `quarantined`; never call them scanned or clean (owner accepted quarantine-only, no scanner/ClamAV, 2026-11-10). No Phase 4, no payments/e-signature. Passwords/tokens/keys never printed, logged, committed or returned. Admins cannot see or set passwords. Org isolation for partners. Rate limits on auth and invitation actions. Fail closed on missing production configuration (staging/production profile in `core/config.py`).

## 7. Database and migration state
- Alembic head in code: **0012**. Local disposable databases (`coralswift_test`, `_conc_test` on `localhost:5433`, plus a scratch DB that was dropped) were at 0011 and `alembic check` was clean before this batch. Migration 0012 was added locally but not applied because local PostgreSQL/Docker is unavailable.
- **Configured Supabase target:** project ref `zibfzlwzaecapfrgjret`; user confirms the connected account cannot access it and no verified backup exists. Current instruction forbids remote migrations. No Supabase or production migration was run. See `SUPABASE_MIGRATION_PLAN.md`.
- **Hazard:** the deployed Render development service tracks `main`. If it auto-deployed `15ebe59`, code now selects `auth_tokens.revoked_at`, `notifications.read_at` and `enquiry_followups.*` that the Supabase dev database lacks, so token flows, notification queries and follow-ups may fail until pending migrations are applied to the verified dev target. Not verified live.
- Running processes: none by this work except the local Docker `coralswift-backend-db-1` container (healthy). No unfinished commands.

## 8. Test evidence (executed 2026-11-10, after the last code change)
| Check | Result |
|---|---|
| `ruff check .` | All checks passed |
| `ruff format --check .` | 218 files formatted |
| `mypy` | no issues, 173 source files |
| `pytest -q` | **254 passed, 0 failed**, 1 deprecation warning |
| Fresh DB: `alembic upgrade head` / `current` / `check` on an empty scratch DB (then dropped) | exit 0 / `0011 (head)` / no drift |
| OpenAPI | generated valid 3.1.0, 134 paths, 218 schemas, `docs/api/openapi.json` |
| Docker | image built; `id -u` = 10001 |
| Security/authz suites | included in the 254 (strategic confidentiality, permission matrix, IDOR, token replay, rate limit) |
Not executed: GitHub Actions run; Docker container health with a database; Render; any live Brevo/Turnstile/Supabase call (mock only); load tests. Not written: concurrency tests for the new follow-up/assignment operations; tests for items still NOT CLOSED. No known failing test, lint or type error.

## 9. Known issues and unresolved decisions
Decisions D1-D27: `docs/business-decisions-required.md`. External: Brevo (key works; sender is a Gmail address, no domain; delivery from the app unverified), Turnstile (secret valid; hostnames must include the frontend and `localhost`; a valid token pass unverified), CORS value on Render, staging resources, credential rotation (DB password, S3 keys, Brevo key and Turnstile secret were pasted in chat), monitoring, backups.

## 10. Database restriction
Do not apply a Supabase or production migration. `0011` is pending on the intended development target as reported, but access and backup are unverified. The detailed migration impact and preflight plan is `SUPABASE_MIGRATION_PLAN.md`.

## 11. Ordered remaining work
**Progress entry (2026-11-10):** Batch 1 typed response schemas implemented for overview, KPIs, organization detail and enquiry detail (X3). OpenAPI generation succeeded (134 paths, 235 schemas); ruff check/format and mypy passed on changed files after import sorting. Focused pytest was attempted but all 17 cases failed at fixture setup because localhost:5433 refused/denied the PostgreSQL connection; no behavioral test result is available. Owner approval to apply pending Supabase migrations was later received, but execution is blocked because the configured target is unavailable in the connected Supabase account and its backup could not be verified.

**Progress entry (2026-11-10):** Batch 2 code added `discussion_type` filtering (P9.2), count-only `/admin/workload` reporting (P10.2; capacity remains D13), paginated staff document review history (P12.2), and a paginated enquiry attachment list (P12.5; onboarding documents remain D10). Focused tests were added but not run: `docker compose up -d db` failed because Docker Desktop's named pipe was unavailable. Ruff check/format and mypy passed on changed code; OpenAPI regenerated successfully (137 paths, 242 schemas). The configured Supabase project ref is not listed in the connected Supabase account, so its migration state and backup could not be verified and no remote migration was attempted.

**Progress entry (2026-11-10):** Batch 3 added `account_status` to `/auth/me` and `last_updated`/`decided_at` to partner application responses. Eligibility outcomes and reviewer reasons remain blocked on D27; due dates and provisioning timestamps have no approved model. Tests were updated but not run (Docker Desktop unavailable). OpenAPI regenerated successfully (138 paths, 244 schemas).

**Progress entry (2026-11-10):** Batch 4 added `/partner/organization/editable-fields` metadata and explicit null-clearing for nullable organization profile fields. Omitted fields remain unchanged; `legal_name` rejects null. Existing revision history records before/after values. Regression tests were updated but not run because Docker Desktop is unavailable. Ruff, format, mypy, OpenAPI generation and test collection passed; OpenAPI is 138 paths/244 schemas.
**Progress entry (2026-11-10):** Source review confirmed account metrics, staff self-name update, latest invitation delivery fields, typed organization and enquiry contracts, and document operation flags. Added a super-admin template placeholder catalogue, audit event/detail/CSV endpoints, approved-content scheduling with a claims recheck in maintenance (migration 0012), and typed follow-up/document-review/communication reports. Ruff, format and mypy passed; collection passed (257 tests). The full suite reached 100% with 257 setup errors because Docker's Linux engine pipe is absent and localhost:5433 refuses connections; test bodies did not execute. OpenAPI regenerated at 147 paths/259 schemas; Alembic history and offline SQL generation passed, while actual DB migration checks remain untested. Added `SUPABASE_MIGRATION_PLAN.md`; no live database operation occurred. Latest batch stays uncommitted.
1. **Verification once local PostgreSQL is available:** run focused tests for typed contracts, account metrics, staff self-name update, invitation delivery, document flags, placeholder catalogue, audit detail/actions/CSV, reports, scheduled publishing; then all 257 tests and a fresh disposable DB migration check for 0012.
2. **Remaining independent work:** staff in-app feed only after its staff-recipient and role-visibility model is defined; template create/activate lifecycle; audit security metadata only with approved handling/retention rules; concurrency tests for follow-up and assignment writes.
3. **Decision gates:** document-request/onboarding model (D10), partner eligibility/reviewer-note visibility (D27), profile fields (D20), media library (D23). Do not infer thresholds, due dates, permissions, retention or outcomes.
4. **PRD scope:** SEO metadata is frontend per PRD 1.25/R-071; backend sitemap already returns published slugs and last-modified values. Scheduled publication is implemented locally in migration 0012 and needs behavior verification.
5. **Ops (owner/operator):** no Supabase or production migration; follow `SUPABASE_MIGRATION_PLAN.md` only after verified project access and a restorable backup. Other ops: credential rotation, domain + Brevo authentication, Turnstile hostnames, CORS value, staging, live role tests (X14), monitoring.
After each batch: ruff, format, mypy, focused tests, then the full suite; update `docs/backend-gap-audit.md`, this matrix and `docs/frontend-backend-contract.md`; regenerate `docs/api/openapi.json`; fresh-DB migration check when a migration is added.

## 12. Preservation rules
Do not reimplement closed rows. Extend existing services and schemas. Keep response fields additive and optional. Do not rename routes or change codes already in the contract without recording it under "behaviour changes". Do not delete or rewrite applied migrations. No commit, push, deploy or Supabase/production change without the owner's explicit approval.

## 13. Reference documents
`docs/backend-gap-audit.md` (item-by-item), `docs/backend-gap-implementation-report.md`, `docs/backend-gap-test-report.md`, `docs/frontend-backend-contract.md`, `docs/business-decisions-required.md`, `docs/production-readiness-report.md`, `docs/requirements/prd-master-register.md` (PRD rows), `docs/deployment/*`, `docs/decisions/ADR-001-backend-architecture.md`, `README.md`.
Instruction files: the repository has **no** `AGENTS.md`, `DECISIONS.md`, `MEMORY.md`, `CONTRIBUTING.md` or `CLAUDE.md`. The operating manual used so far is the owner's global `C:\Users\ABC\.claude\AGENTS.md` (outside the repo; summary: report only what was run, no destructive DB actions, ask before commit/push/deploy, smallest correct change). Decisions are in `docs/decisions/` and `docs/*decision*`. Copy the manual into the repo as `AGENTS.md` if Codex cannot read it.
Local-only secret file: `.env.render` (git-ignored) holds real Brevo and Turnstile values; never print, copy or commit it. `.env` likewise.
