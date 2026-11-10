# Prompt for Codex (copy everything below the line)

---

You are continuing backend work on **Coral Swift** (FastAPI + PostgreSQL + SQLAlchemy 2 + Alembic), repository root `C:\Users\ABC\Desktop\coralswift-backend`, branch `main`. Continue from the uncommitted current state described in `CODEX_HANDOFF.md`. Preserve every existing change. Do not restart, rebuild or duplicate finished work.

## Read first, in this order
1. `docs/handoff/CODEX_HANDOFF.md` (state, conventions, next tasks).
2. `docs/handoff/CODEX_PROGRESS_MATRIX.md` (every X, Phase, M and operational item with status).
3. `docs/backend-gap-audit.md`, `docs/frontend-backend-contract.md`, `docs/business-decisions-required.md`, `docs/production-readiness-report.md`.
4. Instruction files: `AGENTS.md`, `DECISIONS.md`, `MEMORY.md`, `CONTRIBUTING.md` do **not** exist in this repository. The owner's operating manual is `C:\Users\ABC\.claude\AGENTS.md` (read it if you can; if not, follow the rules below). Decisions are in `docs/decisions/ADR-001-backend-architecture.md` and `docs/business-decisions-required.md`.
5. `README.md` and `docs/requirements/prd-master-register.md`.

## Verify before trusting the handoff
Run `git status`, `git log --oneline -5`, and `git diff --stat`. Re-check claims against source. Current code includes migrations `0011` and `0012`; 0011 was applied only to disposable local DBs in the prior session, while 0012 has not been applied anywhere. Docker Desktop is installed but its Linux engine pipe is unavailable, and localhost:5433 is inaccessible. Ruff, format, Mypy, OpenAPI generation, Alembic history/offline SQL generation and collection of 257 tests passed in the latest run. The full pytest run fails in setup for all 257 cases at the database fixture before test bodies execute. If local DB becomes available, first apply migrations to a disposable `*_test` database and run focused tests, then the full suite. If reality differs from the handoff, trust the source, fix the handoff, and tell the owner.

## Rules that never change
- Same architecture: `app/modules/<module>/{constants,models,schemas,service,router}.py`; routers registered in `app/api/v1/router.py`; sync SQLAlchemy sessions via `DbSession`; services commit explicitly; no new repository layer, no parallel services or duplicate endpoints. Extend existing functions/schemas; keep new response fields optional and backward compatible.
- Same conventions: `ok()`/`ApiResponse` envelope; `AppError(message, status_code, code)` with UPPER_SNAKE codes; `extra="forbid"` request models; `PageDep` + `page_meta`; `sort` as a `Literal[...]` mapped to order-by tuples with an `id` tie-break; `_like()` escaping for search; `log_activity` for audit (no PII in `meta`); `queue_notification` for email; typed Pydantic responses; foreign organisation ids return 404.
- Security: strategic/M&A and financial data restricted at query level for non-super roles; org isolation from the token; never trust client-supplied org ids, roles, owners or strategic flags; uploads stay `quarantined` and are never called scanned (owner declined a scanner); no secrets in code, logs, docs or commits; do not read, print or copy `.env` or `.env.render`.
- Database: additive Alembic migrations only (`migrations/versions/YYYYMMDD_NNNN_slug.py`, next revision `0013`); never edit an applied migration; never drop, truncate or reset; use `scripts/alembic_test_db.py` (local `*_test` only). **Do not apply any migration to Supabase or production.** The exact intended Supabase dev project is inaccessible from the connected account and has no verified backup. Follow the separate migration plan; no credentials/target changes.
- No Phase 4, no payments/e-signature/ERP, no automated final decisions, no invented business rules. For items marked BLOCKED-DECISION, implement nothing speculative; keep them recorded in `docs/business-decisions-required.md` and continue with independent work.
- Do not commit, push, deploy or touch production/Supabase unless the owner says so in the current turn. Do not claim live verification from mocks.
- Efficiency: grep before reading; read only the needed ranges; patch with small script files rather than quote-heavy shell heredocs; run ruff -> mypy -> focused pytest after each batch; full suite at the end.

## Task order (work through all applicable items, in this order, without stopping between batches)
1. **Test the completed unverified work:** account metrics; staff self-name update; invitation delivery fields; typed overview/KPI/organization/enquiry responses; document operation hints; template placeholder list; audit detail/actions/CSV; scheduled publication and migration 0012. Start only after local PostgreSQL is available.
2. **Remaining independent work:** staff in-app notification feed only after its staff-recipient/role-visibility model is defined; template create/activate lifecycle; audit security metadata only with approved handling/retention rules; media library waits on D23; add concurrency tests for follow-up/assignment writes. SEO is frontend per PRD 1.25/R-071; a backend sitemap already exists.
3. **D10/D27 gates:** document-request resource, onboarding model/tasks/due dates, and partner-visible eligibility/reviewer reasons are blocked until their decisions are recorded. Do not infer outcomes, thresholds, due dates or permissions.
4. **Profile/account limits:** full-name self-update is implemented; email changes need verified-change semantics. Extra profile fields remain blocked on D20.
5. **Notifications/CMS:** close staff in-app feed only if a correct staff-recipient model can be defined without borrowing shared email recipients; media library waits on D23; SEO is frontend per PRD; schedule publishing is implemented in 0012 and needs behavior verification.
6. **Admin/audit/reports:** audit outcome/IP/device/before-after/security metadata only with approved security/retention rules; consider additional account and response trends without inventing metrics; add the approved CSV audit contract already begun.
7. **Release verification:** update docs after each batch; run focused/full regression and fresh DB migration check when local PostgreSQL is available. Never push, deploy, or commit.
8. **Database restriction:** do not apply any Supabase or production migration, change credentials, or change target projects. Exact intended Supabase project `zibfzlwzaecapfrgjret` is inaccessible through the connected account and no verified backup exists. Follow `docs/handoff/SUPABASE_MIGRATION_PLAN.md`; stop remote work until both access and backup verification are available, then require explicit target verification and approval.
9. Report operator/owner actions you cannot do: verified access and backup for Supabase dev, credential rotation, domain + Brevo authentication, Turnstile hostnames, CORS value, staging resources, live role tests, monitoring.

## After every batch
Update `docs/handoff/CODEX_PROGRESS_MATRIX.md` and `docs/backend-gap-audit.md` (status, evidence, tests), the contract doc for any endpoint change, and add a short dated entry to `docs/handoff/CODEX_HANDOFF.md` section 11. State exactly which commands you ran and their real results; never report a result you did not observe.

## Finish with
A concise report: what you closed (ids), what stays blocked (decision/external), test counts, migration status, files changed, and the exact next action for the owner.
