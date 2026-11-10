# Backend Gap Implementation Report (2026-11-10)

Scope: the register in `backend-gap-audit.md`. The counts immediately below are the historical baseline at commit `15ebe59`, not the current source-verified status. Nothing was deployed, no migration was applied to Supabase, no secret was committed. Changes are **uncommitted** in the working tree.

## Status of the whole register
Rows classified: 188 (mixed-status rows are counted once under their first label).
- CLOSED-TESTED: 88; CLOSED-EXISTING: 17
- BLOCKED-DECISION: 31; BLOCKED-EXTERNAL: 7; N/A-JUSTIFIED: 5
- **NOT CLOSED: 40** (code still to write)
The project is therefore **not** complete. Do not read the 253 passing tests as "every gap closed".

## Implemented in this work
| Area | Change | Files |
|---|---|---|
| Auth | `POST /auth/change-password`; distinct token errors (`TOKEN_EXPIRED`, `TOKEN_ALREADY_USED`, `TOKEN_REVOKED`); `ACCOUNT_DEACTIVATED` (403, only with the right password); invitation state/resend/revoke | `auth/service.py`, `auth/router.py`, `auth/schemas.py` |
| Permission matrix | `GET /auth/permissions`, derived from the route guards | `auth/permissions.py`, `auth/dependencies.py` |
| Accounts | `/admin/accounts` list/detail/filters, resend/revoke invitation, suspend/reactivate, admin-sent password reset, rate limit; `/admin/assignees` | `admin/people_router.py` |
| Enquiries | richer rows (phone, owner name, category, updated, SLA times), filters (`category`, `project_group`, `assigned_any`, `updated_*`), `sort`; activity feed | `admin/service.py`, `admin/router.py`, `admin/followups_router.py` |
| Follow-ups | kinds (note / follow_up / communication), owner, update/reschedule/reassign/cancel, global list with counts | `admin/followups_router.py`, `admin/service.py`, `admin/models.py` |
| Applications | list: q, dates, sort, reviewer, pathway; names, contact, `allowed_next`; `GET /reviewer/transitions`; clear reviewer | `reviews/router.py`, `reviews/service.py`, `applications/transitions.py` |
| Documents | `GET /admin/documents` (reviewers scoped to assigned organisations) | `admin/reference_router.py` |
| Lists | audit: q, sort, actor names, `is_strategic`; outbox: filters, typed rows, `is_strategic`; users: q/status/sort/meta; organisations: country/dates/sort/contact; content: sort/dates; privacy and change-request lists paginated | `admin/*`, `engagement/*`, `organizations/extras.py`, `content/*` |
| Partner inbox | typed notifications with read state, unread count, mark read / read-all; typed enquiry rows | `organizations/extras.py` |
| Typed contracts | settings, launch readiness, security policy (read-only) | `admin/ops_router.py`, `admin/reference_router.py` |
| Migration | `0011`: `auth_tokens.revoked_at`, `notifications.read_at`, `enquiry_followups.kind/assignee_id/cancelled_at` | `migrations/versions/20261110_0011_*.py` |

Behaviour changes a client must know: a replayed invitation/reset token now returns `TOKEN_ALREADY_USED` (was `INVALID_OR_EXPIRED_TOKEN`); login of a deactivated account with the right password returns 403 `ACCOUNT_DEACTIVATED` (was 401); `GET /admin/notifications` accepts `status=all` and its rows gained fields; the partner notification list gained `id`, `read_at`, `is_read` and `meta.unread`; `GET /admin/users` and `/admin/profile-change-requests` are now paginated.

At the original report baseline, migration 0011 was applied to disposable local test databases (`alembic check` clean, head `0011`) and not to Supabase. The current uncommitted head is `0012`; 0012 is not applied to any database. See `docs/handoff/SUPABASE_MIGRATION_PLAN.md` for both migration impacts and the no-remote-operation preconditions.

## Remaining work (NOT CLOSED)
Remaining gaps are listed in the current source-verified audit and progress matrix. SEO metadata is frontend per PRD 1.25/R-071; media library waits on D23. New endpoint work since the initial baseline is summarized below. Decision-blocked status/onboarding and unverified behavior are not considered complete.

## Source-verified follow-up (2026-11-10)

Since the initial report, uncommitted code adds typed overview/KPI/organization/enquiry contracts, account metrics, staff self-name update with audit, account-row invitation delivery status/time, partner document operation hints, template placeholder listing, audit event/detail/action catalogue/CSV, approved-content scheduling with maintenance execution and dry-run reporting (`0012`), and typed aggregate follow-up/document-review/communication reports. Focused regression assertions exist for these changes. Ruff, format, Mypy, OpenAPI generation and offline Alembic SQL/history checks pass; pytest collection passes (257 tests). The latest full suite reported 257 setup errors because Docker cannot connect to its Linux engine and local PostgreSQL at `localhost:5433` refuses the connection; test bodies did not execute. `0011` and `0012` remain unapplied to Supabase; see `docs/handoff/SUPABASE_MIGRATION_PLAN.md`. Do not infer completion of decision-blocked fields or missing test evidence.
