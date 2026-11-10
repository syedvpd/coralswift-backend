# Backend Gap Implementation Report (2026-11-10)

Scope: the register in `backend-gap-audit.md`. All changes are additive; migration `0011` adds nullable columns only. Nothing was deployed, no migration was applied to Supabase, no secret was committed. Changes are **uncommitted** in the working tree.

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

Migration 0011: applied to the local disposable test database only (`alembic check` clean, head `0011`). **Not applied to Supabase.** Downgrade drops the added columns (data in them is lost); the follow-up `kind` CHECK is dropped first. No existing data is changed.

## Remaining work (NOT CLOSED)
X3 typed overview, KPIs, org detail, enquiry detail objects (M5); `discussion_type` filter; workload endpoint; staff document review history; enquiry attachment list; staff in-app notification feed; template versioning and placeholder list; media library, SEO, scheduled publication; profile update of staff users; audit get-by-id, catalogue and export; account metrics, trends and extra reports; delivery result on account rows; `/auth/me` account status; partner-visible application fields (decision, due dates, provisioning, `last_updated`); editable-field metadata, revision before/after, null semantics; document-request resource. Items tied to a decision (D1-D27) stay blocked until answered.
