# Frontend-Backend Contract (2026-11-10)

Machine-readable contract: [`docs/api/openapi.json`](api/openapi.json) (regenerate with the snippet in `README`/this file after endpoint changes) and the live `/openapi.json` while `APP_ENV` is development. Base path `/api/v1`. Responses use `{ "success", "message", "data", "meta" }`; errors use `{ "success": false, "message", "error": { "code", "details" } }`.

## Conventions
- **Pagination:** `page` (from 1) and `page_size` (max 100). Lists return `meta: { page, page_size, total, pages }`. Fixed small lists are not paginated: `/admin/assignees`, `/admin/notification-templates`, `/auth/sessions`, `/reviewer/transitions`, `/catalog/project-categories`, `/content/sitemap`, and the partner lists of applications, documents, enquiries, change requests and revisions.
- **Sorting:** `sort` takes a fixed list of values (a leading `-` is descending); anything else returns 422. Ties are broken by id so pages are stable.
- **Dates:** ISO 8601; `*_from` is inclusive, `*_to` exclusive. Send the `+` of a timezone as `%2B`.
- **Search:** `q` is a case-insensitive partial match on the fields named in each endpoint.
- **Auth:** `Authorization: Bearer <access_token>`. Refresh with `POST /auth/refresh`; MFA state survives a refresh. Lifetimes: `GET /admin/security-policy`.
- **Public forms:** `X-Bot-Token` (Turnstile) and optional `Idempotency-Key`.

## Auth and accounts
| Endpoint | Who | Notes |
|---|---|---|
| `POST /auth/login`, `/refresh`, `/logout` | anyone / session | login of a deactivated account with the right password: 403 `ACCOUNT_DEACTIVATED`; otherwise a generic 401 `INVALID_CREDENTIALS` |
| `POST /auth/change-password` | staff, partner | `{current_password, new_password}`; other sessions are signed out; errors `INVALID_CURRENT_PASSWORD` (400), `PASSWORD_UNCHANGED`, `WEAK_PASSWORD` (422) |
| `POST /auth/invitations/accept`, `/password-reset/confirm` | token holder | 400 codes: `TOKEN_EXPIRED`, `TOKEN_ALREADY_USED`, `TOKEN_REVOKED`, `INVALID_OR_EXPIRED_TOKEN` |
| Links in emails | | invitation `{PORTAL_BASE_URL}/activate?token=...`; reset `{PORTAL_BASE_URL}/reset-password?token=...` |
| `GET /auth/permissions` | any signed-in | modules and endpoints this account may call; super administrators also get `role_matrix` |
| `GET /admin/assignees?purpose=enquiries\|applications` | any staff | `[{id, full_name, staff_role}]`, active staff only |
| `GET /admin/accounts`, `/{id}` | super admin | filters `q, user_type, role, status, invitation (pending\|expired\|revoked), created_from/to`, `sort`; `invitation_state`, `organization`, `recent_activity`, latest `invitation_delivery_status` and `invitation_delivery_at` |
| `GET /admin/accounts/metrics` | super admin | totals by user type/status/staff role, active partner accounts, and accounts that have never logged in |
| `PATCH /auth/me` | signed-in staff | `{full_name}`; updates only the current staff member's name and records an audit event |
| `POST /admin/accounts/{id}/invitation/resend`, `/revoke`, `/password-reset`, `/suspend`, `/reactivate` | super admin | resend and reset are rate limited (429); not yourself (409 `SELF_CHANGE`) |
| `GET /admin/users` | super admin | `q, role, status, sort`, meta |

## Permissions (role -> modules, source: guards)
`super_administrator`: everything. `business_development_manager`: `admin/enquiries`, `admin/follow-ups`, `admin/workload`, `admin/organizations`, `admin/overview`, `admin/reports` (enquiries.csv, kpis), `admin/meetings`, `admin/assignees`. `partner_reviewer`: `reviewer/*`, `admin/documents` (including assigned-organization review history), `admin/assignees`. `content_administrator`: `admin/content*`, `admin/assignees` (approve/reject are super administrator only). Strategic/M&A enquiries: super administrators only, at query level. Always read the live matrix from `/auth/permissions` rather than hard-coding this table.

- `GET /admin/notification-templates/placeholders` (super admin) returns the current allowed placeholder names used by template validation.
- `GET /admin/audit/actions`, `GET /admin/audit/{activity_id}`, and `GET /admin/audit.csv` (super admin) list recorded action keys, retrieve one event, and export the filtered audit log. CSV exports are formula-safe, capped at 10,000 rows, private/no-store, and audited.
- `GET /admin/reports/follow-ups` (super admin and BDM) returns aggregate counts by follow-up kind and open/completed/cancelled state plus monthly counts, restricted to the caller's visible enquiry types. `GET /admin/reports/document-review` and `/admin/reports/communications` (super admin) return document-review counts/observed average turnaround and notification delivery/template counts; all accept `created_from` (inclusive) and `created_to` (exclusive).
- Partner document rows add `can_replace`, `can_remove`, `can_download` based on current document/version state; these are UI hints and do not replace authorization checks on each operation.
- Content admins can `POST /admin/content/{id}/schedule` with a future timezone-aware `{publish_at}` for approved content whose claims are cleared; `DELETE /admin/content/{id}/schedule` cancels it. `scripts/run_maintenance.py --dry-run` reports `content_would_publish`; scheduled publication requires the maintenance job to run. Migration `0012` adds the nullable schedule field.

## Enquiries (BDM, super admin)
- `GET /admin/enquiries` filters: `type, status, priority, assigned_user_id, assigned_any, unassigned, overdue, sla_breached, q, category, discussion_type, project_group (it|non_it), created_from/to, updated_from/to`, `sort` (`-created_at, created_at, -updated_at, updated_at, next_follow_up_at, response_due_at`). Row adds `contact_phone, assigned_user_name, category, updated_at, first_response_at, response_due_at`.
- `GET /admin/workload` returns count-only open enquiry, overdue follow-up, and SLA-breached totals by assignee, scoped to enquiries visible to the caller. It does not apply capacity limits (D13).
- `GET /admin/enquiries/{id}/documents` returns paginated attachments, excluding financial statements for BDMs.
- `GET /admin/enquiries/{id}/activity` (`action` partial match) - status, assignment and follow-up history with `actor_name`.
- Follow-ups: `POST /admin/enquiries/{id}/follow-ups` `{note, kind: note|follow_up|communication, due_at (follow_up only), assignee_id}`; `PATCH .../{fid}` (null clears due date / assignee), `POST .../{fid}/complete`, `.../cancel`; `GET /admin/follow-ups` filters `status (open|completed|cancelled), kind, assignee_id, mine, due_from/to`, `sort`; `meta.counts` has open, overdue, upcoming, completed, cancelled. A `note` does not count as the first response; `follow_up` and `communication` do.
- Status values: the `EnquiryStatus` enum; any value may be set (no transition table until decision D8).

## Applications (reviewer, super admin)
- `GET /reviewer/applications` filters `status, unassigned, assigned_reviewer_id, q, pathway, submitted_from/to, updated_from/to`, `sort`. Row adds `updated_at, decided_at, assigned_reviewer_name, primary_contact, allowed_next`.
- `GET /reviewer/transitions` - rule table `{from, to, needs_reason, needs_assigned_reviewer, dedicated_endpoint}`.
- `POST /reviewer/applications/{id}/assign` `{reviewer_id}`; `null` clears and removes the reviewer's access.
- Six allocation stages map 1:1 to statuses: expression of interest `submitted`; `eligibility_verification`; `capability_review`; `commercial_legal_review`; `pilot_onboarding`; `scale_up`. Outcomes `information_requested`, `rejected`, `withdrawn`. There is no "approved" status (D7).
- Partner application responses include `last_updated` and nullable `decided_at`. `/auth/me` includes `account_status`. Partner-visible decision reasons/eligibility outcomes remain blocked on D27; information-request deadlines and provisioning timestamps have no approved data model yet.

## Documents and partner area
- `GET /admin/documents` (reviewer: assigned organisations only; super admin: all) filters `organization_id, category, review_status, upload_status, status, expires_before, uploaded_from/to, q`, `sort`. `upload_status=quarantined` means stored and **never scanned**.
- `GET /admin/documents/{id}/history` returns paginated versions and review outcomes, restricted to super administrators and reviewers assigned to the document's organisation.
- `GET /partner/notifications` `{id, template, delivery_status, created_at, read_at, is_read}` with `meta.unread`; `POST /partner/notifications/{id}/read`, `/read-all`.
- Upload limits and types: `GET /admin/security-policy` (`max_upload_bytes`, `allowed_upload_types`, `max_documents_per_enquiry`).
- `GET /partner/organization/editable-fields` describes direct-update, approval-required, nullable and null-clearing behavior. On `PUT /partner/organization`, omit a field to leave it unchanged; send explicit `null` to clear nullable fields. `legal_name` cannot be cleared. `GET /partner/organization/history` records `{old,new}` values for each revision.

## Admin reference and logs
- `GET /admin/audit` filters `record_type, action, actor_user_id, organization_id, created_from/to, q`, `sort`; rows add `actor_name`, `is_strategic`.
- `GET /admin/notifications` (outbox) `status` (`pending|sent|failed|all`, default failed), `template`, `q` (recipient), dates, `sort`; typed rows with `is_strategic`.
- `GET /admin/settings` -> `{values, allowed_keys, definitions[{key, group, value_kind, unit}]}`; `GET /admin/launch-readiness` -> `{contact, queues, ready, pending_items}`; `GET /admin/security-policy` (read-only).
- `GET /admin/organizations` filters `q, status, country, created_from/to`, `sort`; `GET /admin/content` adds `updated_from/to`, `sort`.

## Typed dashboard and detail responses
`/admin/overview` and `/admin/reports/kpis` now have published typed response schemas. Super-administrator-only aggregates (`applications`, `failed_notifications`, recent activity, and partner application, portal, eligibility, and document-review metrics) remain omitted for BDMs. `/admin/organizations/{id}` has a typed profile and application response; registration, turnover, references and authorized contacts remain omitted for BDMs. `/admin/enquiries/{id}` now types its contact, company, type-specific details and document objects; strategic and financial visibility remains enforced by the existing query/service logic.

## Additions 2026-11-10 (Claude Code) - see `docs/api/openapi.json` for schemas
- `POST /privacy/requests/verify` `{token}`: confirms a public privacy request (link `{PORTAL_BASE_URL}/privacy/verify?token=`); errors `INVALID_OR_EXPIRED_TOKEN`, `TOKEN_EXPIRED`. Admin rows gain `email_verified`, `submitted_by_partner`; staff actions return 409 `EMAIL_NOT_VERIFIED` until confirmed (rejection is allowed).
- Content (public and admin): `seo_title, seo_description, canonical_url, og_title, og_description, og_image_url, image_url, image_alt` (https only; send null to clear).
- `GET /auth/me` adds `phone, partner_role, mfa_enabled, mfa_required, last_login_at`; `PATCH /auth/me` `{full_name?, phone?}` (E.164 phone; null clears phone); `GET /auth/sessions` adds `expires_at`; `DELETE /auth/sessions` signs out all other sessions; `POST /auth/mfa/disable` `{password, code}` (partners only).
- Partner: `POST/GET /partner/privacy-requests`; `GET /partner/document-requests[/{id}]` (`meta.open`); upload `POST /partner/documents` accepts form field `request_id` to fulfil a request (errors `REQUEST_CLOSED`, `CATEGORY_MISMATCH`, 404 for other organisations' ids).
- Reviewer: `POST|GET /reviewer/applications/{id}/document-requests`, `POST /reviewer/document-requests/{id}/cancel`.
- Staff feed (any staff, own items): `GET /admin/feed` (`unread`, `archived`, `meta.unread`), `POST /admin/feed/{id}/read|archive`, `POST /admin/feed/read-all`.

## Additions 2026-11-10 (second pass)
- `GET /admin/organizations/{id}/revisions` (`{field: {old, new}}`, `changed_by_name`) and `/activity` (BDM/super admin; strategic enquiry events excluded; paginated).
- `GET /admin/profile-change-requests` rows add `organization_name` and, for pending requests, `before` (current values of the requested fields).
- `GET /partner/notifications` rows add `title`, `category`, `related_reference`; `GET /partner/notifications/unread-count`; `POST /partner/notifications/{id}/unread`.
