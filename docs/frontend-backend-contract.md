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
| `GET /admin/accounts`, `/{id}` | super admin | filters `q, user_type, role, status, invitation (pending\|expired\|revoked), created_from/to`, `sort`; `invitation_state`, `organization`, `recent_activity` |
| `POST /admin/accounts/{id}/invitation/resend`, `/revoke`, `/password-reset`, `/suspend`, `/reactivate` | super admin | resend and reset are rate limited (429); not yourself (409 `SELF_CHANGE`) |
| `GET /admin/users` | super admin | `q, role, status, sort`, meta |

## Permissions (role -> modules, source: guards)
`super_administrator`: everything. `business_development_manager`: `admin/enquiries`, `admin/follow-ups`, `admin/organizations`, `admin/overview`, `admin/reports` (enquiries.csv, kpis), `admin/meetings`, `admin/assignees`. `partner_reviewer`: `reviewer/*`, `admin/documents`, `admin/assignees`. `content_administrator`: `admin/content*`, `admin/assignees` (approve/reject are super administrator only). Strategic/M&A enquiries: super administrators only, at query level. Always read the live matrix from `/auth/permissions` rather than hard-coding this table.

## Enquiries (BDM, super admin)
- `GET /admin/enquiries` filters: `type, status, priority, assigned_user_id, assigned_any, unassigned, overdue, sla_breached, q, category, project_group (it|non_it), created_from/to, updated_from/to`, `sort` (`-created_at, created_at, -updated_at, updated_at, next_follow_up_at, response_due_at`). Row adds `contact_phone, assigned_user_name, category, updated_at, first_response_at, response_due_at`.
- `GET /admin/enquiries/{id}/activity` (`action` partial match) - status, assignment and follow-up history with `actor_name`.
- Follow-ups: `POST /admin/enquiries/{id}/follow-ups` `{note, kind: note|follow_up|communication, due_at (follow_up only), assignee_id}`; `PATCH .../{fid}` (null clears due date / assignee), `POST .../{fid}/complete`, `.../cancel`; `GET /admin/follow-ups` filters `status (open|completed|cancelled), kind, assignee_id, mine, due_from/to`, `sort`; `meta.counts` has open, overdue, upcoming, completed, cancelled. A `note` does not count as the first response; `follow_up` and `communication` do.
- Status values: the `EnquiryStatus` enum; any value may be set (no transition table until decision D8).

## Applications (reviewer, super admin)
- `GET /reviewer/applications` filters `status, unassigned, assigned_reviewer_id, q, pathway, submitted_from/to, updated_from/to`, `sort`. Row adds `updated_at, decided_at, assigned_reviewer_name, primary_contact, allowed_next`.
- `GET /reviewer/transitions` - rule table `{from, to, needs_reason, needs_assigned_reviewer, dedicated_endpoint}`.
- `POST /reviewer/applications/{id}/assign` `{reviewer_id}`; `null` clears and removes the reviewer's access.
- Six allocation stages map 1:1 to statuses: expression of interest `submitted`; `eligibility_verification`; `capability_review`; `commercial_legal_review`; `pilot_onboarding`; `scale_up`. Outcomes `information_requested`, `rejected`, `withdrawn`. There is no "approved" status (D7).

## Documents and partner area
- `GET /admin/documents` (reviewer: assigned organisations only; super admin: all) filters `organization_id, category, review_status, upload_status, status, expires_before, uploaded_from/to, q`, `sort`. `upload_status=quarantined` means stored and **never scanned**.
- `GET /partner/notifications` `{id, template, delivery_status, created_at, read_at, is_read}` with `meta.unread`; `POST /partner/notifications/{id}/read`, `/read-all`.
- Upload limits and types: `GET /admin/security-policy` (`max_upload_bytes`, `allowed_upload_types`, `max_documents_per_enquiry`).

## Admin reference and logs
- `GET /admin/audit` filters `record_type, action, actor_user_id, organization_id, created_from/to, q`, `sort`; rows add `actor_name`, `is_strategic`.
- `GET /admin/notifications` (outbox) `status` (`pending|sent|failed|all`, default failed), `template`, `q` (recipient), dates, `sort`; typed rows with `is_strategic`.
- `GET /admin/settings` -> `{values, allowed_keys, definitions[{key, group, value_kind, unit}]}`; `GET /admin/launch-readiness` -> `{contact, queues, ready, pending_items}`; `GET /admin/security-policy` (read-only).
- `GET /admin/organizations` filters `q, status, country, created_from/to`, `sort`; `GET /admin/content` adds `updated_from/to`, `sort`.

## Still untyped (documented gaps)
`/admin/overview`, `/admin/reports/kpis`, `/admin/organizations/{id}`, and the `contact/company/details/documents` objects of `/admin/enquiries/{id}` return JSON objects without a published schema. Keys in use: overview `enquiries` (`type:status` -> count), `unassigned_enquiries`, `overdue_follow_ups`, `sla_breached`, `failed_notifications`; KPIs `avg_hours_to_first_follow_up`, `enquiries_by_type_and_source`, `enquiries_by_type_and_status`, `overdue_follow_ups`, `meeting_requests_by_status`, and for super administrators `partner_application_completion`, `portal_adoption`, `eligibility_outcomes_recorded`, `document_review_turnaround_hours_avg`.
