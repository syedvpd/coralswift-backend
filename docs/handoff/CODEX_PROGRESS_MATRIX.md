# Codex Progress Matrix

Updated 2026-11-10 against the uncommitted working tree (base HEAD `15ebe59`). Statuses: CLOSED-TESTED, CLOSED-EXISTING, IMPLEMENTED-UNTESTED, BLOCKED-DECISION, BLOCKED-EXTERNAL, NOT CLOSED, N/A-JUSTIFIED. Behavior remains unverified while local PostgreSQL is unavailable. Decisions D1-D27: `docs/business-decisions-required.md`.

| ID | Requirement | Current status | Evidence/files | Tests | Remaining action | Dependencies |
|---|---|---|---|---|---|---|
| X1 | Pagination meta on every list | CLOSED-TESTED | `page,page_size,total,pages` on every paginated list; sweep test over all list endpoints `test_gap_lists.py::test_every_paginated_list_reports_page_total_and_pages`. Privacy-request and profile-change lists lacked it and were fixed. Small fixed lists are deliberately unpaginated (listed in the test and contract) | test_gap_lists.py::test_every_paginated_list_reports_page_total_and_pages | None; re-verify only | - |
| X2 | Server-side search/sort/date on `/reviewer/applications`, `/admin/organizations`, `/admin/users`, `/admin/notifications`, `/admin/content`, `/admin/audit` | CLOSED-TESTED | all six: `test_gap_applications`, `test_gap_lists`, `test_gap_phase_a` (invalid sort/status values return 422) | test_gap_applications, test_gap_lists, test_gap_phase_a | None; re-verify only | - |
| X3 | Typed schemas for overview, KPIs, settings, org detail, outbox rows, partner notification/enquiry rows, enquiry contact/company/details/documents | IMPLEMENTED-UNTESTED | `OverviewOut`, `KpisOut`, `OrganizationDetailOut`, typed enquiry detail nested objects; OpenAPI generated 147 paths and 259 schemas. Role-limited financial fields remain omitted by service authorization | Focused behavior tests not run (local PostgreSQL/Docker unavailable) | Run focused tests when local DB is available | - |
| X4 | Updated-at and actor names | CLOSED-TESTED | enquiry rows (`updated_at`, `assigned_user_name`), follow-ups (`author_name`, `assignee_name`), enquiry activity, audit (`actor_name`), reviewer list/detail (`updated_at`, `assigned_reviewer_name`, history `actor_name`, notes `author_name`), accounts. `test_gap_enquiries`, `test_gap_phase_a`, `test_gap_applications` | test_gap_enquiries, test_gap_phase_a, test_gap_applications | None; re-verify only | - |
| X5 | Transition tables / allowed-next states | NOT CLOSED | **applications: CLOSED-TESTED** (`GET /reviewer/transitions`, `allowed_next` on rows; `test_gap_applications`). **enquiries:** status can be set to any `EnquiryStatus`; restricting it and new statuses ("awaiting response") need a decision (D8) | test_gap_applications | IMPLEMENT: **applications: CLOSED-TESTED** (`GET /reviewer/transitions`, `allowed_next` on rows; `test_gap_applications`) | D8 |
| X6 | Strategic flag on audit/outbox/notification rows | CLOSED-TESTED | `is_strategic` on audit and outbox rows (`test_gap_phase_a`). Access control never relies on it | test_gap_phase_a | None; re-verify only | - |
| X7 | Strategic/M&A authorization on every path | CLOSED-TESTED | `test_strategic_confidentiality.py`: every admin/reviewer GET as BDM, reviewer and content admin; search, CSV, detail, documents, follow-ups, activity, assign/patch, overview and KPI aggregates. Also `test_admin`, `test_project_partner_strategic` | test_strategic_confidentiality.py, test_admin, test_project_partner_strategic | None; re-verify only | - |
| X8 | Role-to-module permission matrix | CLOSED-TESTED | `GET /auth/permissions` built from the live route guards (no second source); test calls every staff GET route with all four roles and asserts matrix == enforcement (`test_permission_matrix_matches_real_enforcement`). Partner modules included | test_permission_matrix_matches_real_enforcement | None; re-verify only | - |
| X9 | CORS for the deployed frontend origin | BLOCKED-EXTERNAL | code and preflight tests exist (`test_app`); the allow-list is the `CORS_ALLOWED_ORIGINS` environment value on Render. No live preflight was run | test_app | Needs external access/config: code and preflight tests exist (`test_app`); the allow-list is the `CORS_ALLOWED_ORIGINS` environment value on Render | - |
| X10 | HttpOnly cookie session / persistence | BLOCKED-DECISION | D1. Tokens are returned in the response body; refresh works with the refresh token | - | Wait for owner answer D1, then implement the recommended option | D1 |
| X11 | Change-password endpoint | CLOSED-TESTED | `POST /auth/change-password` (staff and partner, other sessions revoked); `test_gap_phase_a` | test_gap_phase_a | None; re-verify only | - |
| X12 | Malware scanner | N/A-JUSTIFIED | owner formally accepted quarantine-only uploads on 2026-11-10 and declined a scanner. Uploads stay `quarantined`; nothing claims a scan. If the owner reverses, an adapter is needed | - | None (justified) | - |
| X13 | Retention dates and secure deletion | BLOCKED-DECISION | mechanism exists and is tested with fake storage (`test_ops::test_retention_purge_and_expiry_reminders`); retention periods and legal checks are D4 | - | Wait for owner answer D4, then implement the recommended option | D4 |
| X14 | Live authenticated test accounts | BLOCKED-EXTERNAL | needs authorised access to the deployed service and staff creation via `scripts/create_staff_user.py`; none made | - | Needs external access/config: needs authorised access to the deployed service and staff creation via `scripts/create_staff_user | - |
| P1.1 | No API documentation originally | CLOSED-EXISTING | live `/openapi.json`; contract in `frontend-backend-contract.md` | - | None; re-verify only | - |
| P1.2 | CORS rejects origins | BLOCKED-EXTERNAL | see X9 | - | Needs external access/config: see X9 | X9 |
| P1.3 | `/auth/me` not staff-only | N/A-JUSTIFIED | one endpoint serves staff and partners by design; `user_type` tells them apart | - | None (justified) | - |
| P1.4 | No change-password; memory-only sessions | CLOSED-TESTED / BLOCKED-DECISION | change-password closed (X11); persistence is D1 | - | None; re-verify only (second part of the status is not closed: see Evidence) | D1; X11 |
| P1.5 | One generic 401 for every login failure | CLOSED-TESTED / BLOCKED-DECISION | a deactivated account with the **correct** password now gets 403 `ACCOUNT_DEACTIVATED` (`test_gap_phase_a`, `test_auth`). "Not activated" cannot be told apart without revealing which emails have accounts: D2 | test_gap_phase_a, test_auth | None; re-verify only (second part of the status is not closed: see Evidence) | D2 |
| P1.6 | Login/MFA/me/refresh/logout never tested live | BLOCKED-EXTERNAL | local coverage: `test_auth` (16), `test_mfa` (7). Live = X14 | test_auth, test_mfa | Needs external access/config: local coverage: `test_auth` (16), `test_mfa` (7) | X14 |
| P4.1 | Pending / Approved application counts | BLOCKED-DECISION | there is no "approved" status; D7 | - | Wait for owner answer D7, then implement the recommended option | D7 |
| P4.2 | Recent decisions (decision timestamp) | CLOSED-TESTED | `decided_at` on reviewer rows; `updated_at`; sort `-updated_at` | - | None; re-verify only | - |
| P4.3 | Recent onboarding activity feed | NOT CLOSED | no feed endpoint; depends on the onboarding model (D10) | - | IMPLEMENT: no feed endpoint; depends on the onboarding model (D10) | D10 |
| P4.4 | Documents awaiting verification | CLOSED-TESTED | `GET /admin/documents?review_status=pending` (`test_gap_reference`) | test_gap_reference | None; re-verify only | - |
| P4.5 | Keys of overview/KPIs undocumented | IMPLEMENTED-UNTESTED | `OverviewOut`/`KpisOut` and contract define the response keys | X3 | Run behavior tests when local DB is available | X3 |
| P4.6 | Reviewer list totals/date filter | CLOSED-TESTED | `meta.total` + `submitted_from/to`, `updated_from/to` | - | None; re-verify only | - |
| P5.1 | Search, date range, sort, category filters | CLOSED-TESTED | `q`, dates, `sort`, `pathway`, reviewer, unassigned (no separate "category": pathway is the category) | - | None; re-verify only | - |
| P5.2 | Applicant name/email/phone, last updated on rows | CLOSED-TESTED | `primary_contact` (first authorised contact), `updated_at` | - | None; re-verify only | - |
| P5.3 | Reviewer-name lookup for non-super roles | CLOSED-TESTED | `GET /admin/assignees`, `assigned_reviewer_name` | - | None; re-verify only | - |
| P5.4 | Transition table | CLOSED-TESTED | X5 | - | None; re-verify only | X5 |
| P5.5 | Pagination meta | CLOSED-TESTED | X1 | - | None; re-verify only | X1 |
| P6.1 | Checklist/scoring endpoints | BLOCKED-DECISION | checklist items and scoring are not defined in the PRD; automated scoring is out of scope (D9). Human eligibility records exist (`test_reviewer`) | test_reviewer | Wait for owner answer D9, then implement the recommended option | D9 |
| P6.2 | Start-review / recommend / decision endpoints | BLOCKED-DECISION | forward moves and decisions go through `POST /reviewer/applications/{id}/transition` with enforced rules and mandatory reasons (`test_transitions`); a separate "recommend" step is D9 | test_transitions | Wait for owner answer D9, then implement the recommended option | D9 |
| P6.3 | Reversal / reconsideration | BLOCKED-DECISION | D11. Rejected/withdrawn are terminal today | - | Wait for owner answer D11, then implement the recommended option | D11 |
| P6.4 | No approved status | BLOCKED-DECISION | D7 | - | Wait for owner answer D7, then implement the recommended option | D7 |
| P6.5 | Actor names on history/notes; updated time | CLOSED-TESTED | `test_gap_applications` | test_gap_applications | None; re-verify only | - |
| P6.6 | Eligibility exception workflow; per-pathway thresholds | BLOCKED-DECISION | PRD requires an "approved internal process" that is not defined: D5, D6 | - | Wait for owner answer D5, D6, then implement the recommended option | D5, D6 |
| P7.1 | Onboarding records, initiation, progress, completion | BLOCKED-DECISION | PRD names "pilot / onboarding" with milestones and acceptance criteria but defines no tasks: D10 | - | Wait for owner answer D10, then implement the recommended option | D10 |
| P7.2 | Invitation/account state readable | CLOSED-TESTED | `invitation_state` on `/admin/accounts` (`test_gap_accounts`) | test_gap_accounts | None; re-verify only | - |
| P7.3 | List lacks applicant fields/filters | CLOSED-TESTED | P5.1/P5.2 | - | None; re-verify only | P5.1, P5.2 |
| P7.4 | Which document categories are mandatory | CLOSED-EXISTING | `GET /partner/applications/{id}/readiness` lists missing items; the seven PRD s.8 categories; per-pathway differences are D6 | - | None; re-verify only | D6 |
| P8.1 | Row fields (phone, category, updated, assignee name) | CLOSED-TESTED | `test_gap_enquiries` | test_gap_enquiries | None; re-verify only | - |
| P8.2 | Filter by category / IT vs Non-IT, sort | CLOSED-TESTED | `category`, `project_group=it \| non_it`, `sort`, `assigned_any`, `updated_from/to` | - | None; re-verify only | - |
| P8.3 | Typed contact/company/details/documents | IMPLEMENTED-UNTESTED | typed enquiry detail schemas | X3 | Run behavior tests when local DB is available | X3 |
| P8.4 | Activity and assignment history | CLOSED-TESTED | `GET /admin/enquiries/{id}/activity?action=assign` | - | None; re-verify only | - |
| P8.5 | Internal note vs follow-up vs communication | CLOSED-TESTED | `kind` = note / follow_up / communication; a note is not a response, a communication is | - | None; re-verify only | - |
| P8.6 | Status workflow, extra statuses | BLOCKED-DECISION | D8 | - | Wait for owner answer D8, then implement the recommended option | D8 |
| P8.7 | Assignee lookup for non-super roles | CLOSED-TESTED | `GET /admin/assignees?purpose=enquiries` | - | None; re-verify only | - |
| P9.1 | Staff read/list access for strategic | CLOSED-TESTED | super administrators only (D12 if BDM should see them); confidentiality tests | - | None; re-verify only | D12 |
| P9.2 | Strategic category (`discussion_type`) on rows + filter | NOT CLOSED | Enum-validated `/admin/enquiries?discussion_type=` filter; shared visibility query scopes strategic records | Test added, not run (Docker Desktop/local PostgreSQL unavailable) | Rerun focused test when local DB is available | - |
| P9.3 | Notes vs discussion vs follow-up types with visibility | CLOSED-TESTED | follow-up `kind`; strategic enquiries are visible to super administrators only | - | None; re-verify only | - |
| P9.4 | Assessment outcome / decision endpoint, extra statuses | BLOCKED-DECISION | D8 | - | Wait for owner answer D8, then implement the recommended option | D8 |
| P9.5 | Activity history, assignee names, sort, total | CLOSED-TESTED | P8 endpoints | - | None; re-verify only | - |
| P9.6 | Typed objects | IMPLEMENTED-UNTESTED | typed enquiry detail schemas include strategic details; query-level access restrictions remain | X3 | Run behavior tests when local DB is available | X3 |
| P9.7 | Strategic queue, owner, response target | CLOSED-EXISTING | settings `route.owner.strategic`, `route.backup.strategic`, `sla.strategic`, `escalation.email.strategic` (`test_section28`); values are D3 | test_section28 | None; re-verify only | D3 |
| P10.1 | Assignment history | CLOSED-TESTED | enquiry activity feed; application history | - | None; re-verify only | - |
| P10.2 | Workload/aggregate endpoint, capacity rules | NOT CLOSED | `/admin/workload` reports count-only open, overdue and SLA-breached enquiry totals by assignee; capacity rules await D13 | Test added, not run (Docker Desktop/local PostgreSQL unavailable) | Rerun test; await D13 before capacity rules | D13 |
| P10.3 | Reviewer list owner/search/priority/date filters | CLOSED-TESTED | owner, search, dates done; applications have no priority/follow-up in the PRD (N/A for those two) | - | None; re-verify only | - |
| P10.4 | Clear an application assignment | CLOSED-TESTED | `reviewer_id: null`; reviewer loses access (`test_gap_applications`) | test_gap_applications | None; re-verify only | - |
| P10.5 | Staff list super-admin only | CLOSED-TESTED | `/admin/assignees` | - | None; re-verify only | - |
| P10.6 | Last updated, "any assigned" filter | CLOSED-TESTED | `updated_at`, `assigned_any` | - | None; re-verify only | - |
| P10.7 | Partner/meeting assignment workflow | BLOCKED-DECISION | D14 | - | Wait for owner answer D14, then implement the recommended option | D14 |
| P10.8 | Statuses vs the six allocation stages | CLOSED-EXISTING | see M2 | - | None; re-verify only | M2 |
| P11.1 | Global follow-up list | CLOSED-TESTED | `GET /admin/follow-ups` with counts in `meta` | - | None; re-verify only | - |
| P11.2 | Update, reschedule, reassign, cancel; status; assignee | CLOSED-TESTED | `PATCH` and `/cancel` on follow-ups; `status`, `assignee_id` | - | None; re-verify only | - |
| P11.3 | Date filter and counts | CLOSED-TESTED | `due_from`, `due_to`, `counts` open/overdue/upcoming/completed/cancelled | - | None; re-verify only | - |
| P11.4 | Reply to requester / external message; reviewer message POST beyond information requests | BLOCKED-DECISION | D15 (sending ad-hoc email to requesters is an integration decision). Contact is logged with `kind=communication` | - | Wait for owner answer D15, then implement the recommended option | D15 |
| P11.5 | Follow-up notifications | NOT CLOSED | no staff in-app notification model (see P15.1) | - | IMPLEMENT: no staff in-app notification model (see P15 | P15.1 |
| P11.6 | Calendar view / integration | BLOCKED-DECISION | D16; real calendar also BLOCKED-EXTERNAL | - | Wait for owner answer D16, then implement the recommended option | D16 |
| P12.1 | Admin document list/filter | CLOSED-TESTED | `GET /admin/documents` (reviewers scoped to assigned organisations) | - | None; re-verify only | - |
| P12.2 | Staff view of per-document review history | NOT CLOSED | Paginated `GET /admin/documents/{id}/history`, reviewer restricted to assigned organisation | Test updated, not run (Docker Desktop/local PostgreSQL unavailable) | Rerun focused test when local DB is available | - |
| P12.3 | Admin upload/replace/delete | BLOCKED-DECISION | D17 (not in PRD; partners own their documents) | - | Wait for owner answer D17, then implement the recommended option | D17 |
| P12.4 | Document-level notes | CLOSED-EXISTING | `review_comment` per version (`test_reviewer`) | test_reviewer | None; re-verify only | - |
| P12.5 | Enquiry-attachment list; onboarding documents | NOT CLOSED | Paginated `GET /admin/enquiries/{id}/documents`; financial attachment filtering preserved. Onboarding document list awaits D10 | `test_gap_enquiries::test_enquiry_rows_carry_names_phone_category_and_filter_server_side` added; not run (PostgreSQL unavailable) | Onboarding documents await D10; rerun focused test when local DB is available | D10 |
| P12.6 | "Replacement requested" status | BLOCKED-DECISION | D18 (uses `clarification_needed`) | - | Wait for owner answer D18, then implement the recommended option | D18 |
| P12.7 | Malware scanning, retention, deletion | N/A-JUSTIFIED / BLOCKED-DECISION | X12, X13 | - | None (justified) | X12, X13 |
| P13.1 | Staff edit of a partner profile | BLOCKED-DECISION | D19; today partners edit and staff decide change requests | - | Wait for owner answer D19, then implement the recommended option | D19 |
| P13.2 | Org rows: category/type, contact | CLOSED-TESTED / BLOCKED-DECISION | `primary_contact` done; organisation category/type is a profile-field decision (D20) | - | None; re-verify only (second part of the status is not closed: see Evidence) | D20 |
| P13.3 | Filters location, date, sort | CLOSED-TESTED | `country`, dates, `sort` | - | None; re-verify only | - |
| P13.4 | Org activity history, agreements, relationship manager, metrics | NOT CLOSED | org activity feed not built; agreements/relationship manager are D21 | - | IMPLEMENT: org activity feed not built; agreements/relationship manager are D21 | D21 |
| P13.5 | Typed org detail; list meta | IMPLEMENTED-UNTESTED / CLOSED-TESTED | typed organization detail; list meta already present | `tests/api/test_gap_enquiries.py` | Run behavior tests when local DB is available | - |
| P14.1 | Account list/search/detail | CLOSED-TESTED | `GET /admin/accounts`, `/{id}` (`test_gap_accounts`) | test_gap_accounts | None; re-verify only | - |
| P14.2 | Invitation status, expiry, resend, revoke | CLOSED-TESTED | states pending/expired/revoked/accepted; rate limited | - | None; re-verify only | - |
| P14.3 | Suspend / reactivate | CLOSED-TESTED | sessions revoked on suspend; self-suspend blocked | - | None; re-verify only | - |
| P14.4 | Partner roles/permissions | CLOSED-TESTED / BLOCKED-DECISION | partner modules in `/auth/permissions`; owner/member membership roles exist; role-specific limits are D22 | - | None; re-verify only (second part of the status is not closed: see Evidence) | D22 |
| P14.5 | Admin-initiated password reset | CLOSED-TESTED | emails the holder a link; admins never see or set passwords | - | None; re-verify only | - |
| P14.6 | Account history, filters, metrics | IMPLEMENTED-UNTESTED | `/admin/accounts/metrics` counts by type/status/staff role, active partners, never-logged-in; test added, DB unavailable | `tests/api/test_gap_accounts.py` | Run focused and full DB suites when local PostgreSQL is available | - |
| P14.7 | "Already has an account" read | BLOCKED-DECISION | D2 (account enumeration) | - | Wait for owner answer D2, then implement the recommended option | D2 |
| P15.1 | Admin notification feed (read/unread/archive/delete) | NOT CLOSED | only the email outbox exists; no in-app staff feed | - | IMPLEMENT: only the email outbox exists; no in-app staff feed | - |
| P15.2 | Ad-hoc email, attachments, preferences | BLOCKED-DECISION | D15 | - | Wait for owner answer D15, then implement the recommended option | D15 |
| P15.3 | Communication history by record | CLOSED-TESTED | follow-ups `kind=communication` + activity feed | - | None; re-verify only | - |
| P15.4 | Delivered/opened receipts | BLOCKED-EXTERNAL | needs Brevo webhooks and a verified domain | - | Needs external access/config: needs Brevo webhooks and a verified domain | - |
| P15.5 | Template create/activate/versions/placeholder list | PARTIAL / IMPLEMENTED-UNTESTED | overrides and version increments exist; super-admin placeholder list implemented | `tests/api/test_ops.py` | Run focused and full DB suites when local PostgreSQL is available; create/activate lifecycle remains open | - |
| P15.6 | Outbox filters and typed rows | CLOSED-TESTED | status, template, q, dates, sort; typed | - | None; re-verify only | - |
| P16.1 | Homepage/hero/banners/services/menus | BLOCKED-DECISION | D23 (content model not specified) | - | Wait for owner answer D23, then implement the recommended option | D23 |
| P16.2 | Media library and image upload | BLOCKED-DECISION | D23 content/media model is undefined; current attachment is a single downloadable document | - | Wait for D23 content model | D23 |
| P16.3 | SEO fields | N/A-JUSTIFIED | PRD 1.25 and traceability R-071 classify SEO as frontend; API already has published-content sitemap with last-modified | - | None for backend | - |
| P16.4 | Scheduled publication; category filter; sort | IMPLEMENTED-UNTESTED / CLOSED-TESTED | approved-content scheduling/cancel, maintenance claim recheck, and dry-run count implemented; additive migration 0012; tests added | `tests/api/test_content_engagement.py` | Run focused behavior and migration checks when local PostgreSQL is available | - |
| P16.5 | "Unpublished" status; audit history; owner | CLOSED-EXISTING | unpublish endpoint, version history; owner field not added | - | None; re-verify only | - |
| P16.6 | Rich text | BLOCKED-DECISION | D23 | - | Wait for owner answer D23, then implement the recommended option | D23 |
| P16.7 | Content Administrator permissions | CLOSED-TESTED | visible in the permission matrix; approval needs a super administrator (D24) | - | None; re-verify only | D24 |
| P17.1 | Get by id, search, pagination | CLOSED-TESTED | `/admin/users` (q, status, sort, meta), `/admin/accounts/{id}` | - | None; re-verify only | - |
| P17.2 | Profile update; contact fields | PARTIAL / IMPLEMENTED-UNTESTED | staff can update own full name with audit; email change remains unsupported without a verified-change flow | `tests/api/test_gap_accounts.py` | Run focused tests when local PostgreSQL is available; design verified email flow separately | - |
| P17.3 | Permission matrix; editing | CLOSED-TESTED / BLOCKED-DECISION | view done; editing permissions D25 | - | None; re-verify only (second part of the status is not closed: see Evidence) | D25 |
| P17.4 | Suspend/reactivate; admin reset; invitation list/resend | CLOSED-TESTED | accounts endpoints | - | None; re-verify only | - |
| P17.5 | Dates; per-user activity; typed status | CLOSED-TESTED |  | - | None; re-verify only | - |
| P17.6 | Reviewer and content-admin roles confirmed | CLOSED-TESTED | all four roles exercised in the matrix test | - | None; re-verify only | - |
| P18.1 | Date filters on applications / partners / outbox | CLOSED-TESTED |  | - | None; re-verify only | - |
| P18.2 | Assignee/category filters; IT/Non-IT | CLOSED-TESTED |  | - | None; re-verify only | - |
| P18.3 | Turnaround, onboarding, document KPIs | PARTIAL | document-review turnaround KPI exists; onboarding KPIs depend on D10 | - | Onboarding metrics after D10 model is approved | D10 |
| P18.4 | Partner-account metrics, follow-up trends | IMPLEMENTED-UNTESTED | account metrics and aggregate follow-up kind/status/month report implemented; BDM visibility is scoped | `tests/api/test_gap_accounts.py`, `tests/api/test_ops.py` | Run behavior/role tests when local DB is available | - |
| P18.5 | Document-review / communication reports | IMPLEMENTED-UNTESTED | aggregate review-state/turnaround and outbox status/template reports added | `tests/api/test_ops.py` | Run behavior and role tests when local DB available | - |
| P18.6 | PDF / Excel export, CSV titles | BLOCKED-DECISION | D26 (optional per PRD; CSV only today) | - | Wait for owner answer D26, then implement the recommended option | D26 |
| P18.7 | Typed KPI/overview totals | IMPLEMENTED-UNTESTED | `KpisOut`/`OverviewOut` | X3 | Run behavior tests when local DB is available | X3 |
| P19.1 | Audit get-by-id, search, sort, total | PARTIAL / IMPLEMENTED-UNTESTED | search/sort/total plus event detail implemented; DB assertions added | `tests/api/test_gap_phase_a.py` | Run focused and full DB suites when local PostgreSQL is available | - |
| P19.2 | Outcome, IP/device, before/after, event catalogue, export, security classification | PARTIAL / IMPLEMENTED-UNTESTED | action catalogue and filtered formula-safe CSV export implemented; outcome/IP/device/before-after and classification remain open; meta excludes PII by convention | `tests/api/test_gap_phase_a.py` | Run behavior tests; do not add IP/device data without approved security/retention requirements | - |
| P19.3 | Typed settings, definitions | CLOSED-TESTED | `GET /admin/settings` | - | None; re-verify only | - |
| P19.4 | Security-policy API | CLOSED-TESTED | read-only `GET /admin/security-policy` | - | None; re-verify only | - |
| P19.5 | Secrets API | N/A-JUSTIFIED | secrets are never exposed or edited through the API | - | None (justified) | - |
| P20.1 | Business decisions (thresholds, retention, owners, providers) | BLOCKED-DECISION | see `business-decisions-required.md` | - | Wait for owner answer, then implement the recommended option | - |
| P20.2 | Meeting confirm/decline/cancel and requester notification | CLOSED-EXISTING | `test_content_engagement`; real calendar BLOCKED-EXTERNAL (M11) | test_content_engagement | None; re-verify only | M11 |
| P20.3 | Own sessions and recovery codes | CLOSED-EXISTING | `/auth/sessions`, `/auth/mfa/recovery-codes` | - | None; re-verify only | - |
| P20.4 | Health page, newsletter CSV | CLOSED-EXISTING | `/health*`, `/admin/reports/newsletter.csv` | - | None; re-verify only | - |
| P20.5 | SPA fallback, HTTPS, CSP | BLOCKED-EXTERNAL | frontend host and edge | - | Needs external access/config: frontend host and edge | - |
| P20.6 | Privacy procedure and legal retention checks | BLOCKED-DECISION | D4 | - | Wait for owner answer D4, then implement the recommended option | D4 |
| P22.1 | Partner roles/permissions in the contract | CLOSED-TESTED | `/auth/permissions` for partners; membership roles in the contract | - | None; re-verify only | - |
| P22.2 | Partner MFA policy; session timing | CLOSED-TESTED | MFA optional for partners (enforced once enabled, `test_mfa`); lifetimes in `/admin/security-policy` | test_mfa | None; re-verify only | - |
| P22.3 | Change password; persistence | CLOSED-TESTED / BLOCKED-DECISION | X11 / D1 | - | None; re-verify only (second part of the status is not closed: see Evidence) | D1; X11 |
| P22.4 | Unactivated vs suspended | CLOSED-TESTED / BLOCKED-DECISION | P1.5 | - | None; re-verify only (second part of the status is not closed: see Evidence) | P1.5 |
| P24.1 | Invitation state and delivery result | IMPLEMENTED-UNTESTED | account list includes latest invitation outbox status/time; DB assertion added | `tests/api/test_gap_accounts.py` | Run focused and full DB suites when local PostgreSQL is available | - |
| P24.2 | Resend/revoke with rate limit | CLOSED-TESTED | `test_invitation_actions_are_rate_limited` | test_invitation_actions_are_rate_limited | None; re-verify only | - |
| P24.3 | Distinct expired/used/revoked codes | CLOSED-TESTED | `TOKEN_EXPIRED`, `TOKEN_ALREADY_USED`, `TOKEN_REVOKED`, `INVALID_OR_EXPIRED_TOKEN` | - | None; re-verify only | - |
| P24.4 | Password policy documented | CLOSED-TESTED | `/admin/security-policy`, contract | - | None; re-verify only | - |
| P24.5 | Link target | CLOSED-TESTED | `{PORTAL_BASE_URL}/activate?token=` (asserted); reset `/reset-password?token=` | - | None; re-verify only | - |
| P24.6 | Provisioning history action names | CLOSED-TESTED | `auth.invitation_issued`, `_resent`, `_revoked`, `auth.account_activated` in account activity | - | None; re-verify only | - |
| P25.1 | In-app feed, read state, unread count | CLOSED-TESTED | `GET /partner/notifications`, `POST .../{id}/read`, `read-all` (`test_gap_lists`) | test_gap_lists | None; re-verify only | - |
| P25.2 | Typed notification and enquiry rows | CLOSED-TESTED |  | - | None; re-verify only | - |
| P25.3 | Document-request resource | BLOCKED-DECISION | D10 must define request lifecycle/deadlines; existing messaging supports information requests and replies | - | Wait for D10 | D10 |
| P25.4 | Account status on `/auth/me` | IMPLEMENTED-UNTESTED | `/auth/me` returns `account_status` | `tests/api/test_gap_accounts.py` | Run behavior tests when local DB is available | - |
| P26.1 | Missing profile fields | BLOCKED-DECISION | D20 (not in PRD s.12 field list) | - | Wait for owner answer D20, then implement the recommended option | D20 |
| P26.2 | Editable vs approval-required metadata | IMPLEMENTED-UNTESTED | `/partner/organization/editable-fields` exposes direct/approval/nullable behavior | `tests/api/test_organizations.py` | Run behavior tests when local DB is available | - |
| P26.3 | Previous/new values in revisions | IMPLEMENTED-UNTESTED | revisions carry `{old,new}`; explicit clear writes `new: null` | `tests/api/test_organizations.py` | Run behavior tests when local DB is available | - |
| P26.4 | Null-clearing semantics | IMPLEMENTED-UNTESTED | explicit null clears nullable profile fields; `legal_name` cannot be cleared; omitted fields unchanged | `tests/api/test_organizations.py` | Run behavior tests when local DB is available | - |
| P27.1 | File size limit documented | CLOSED-TESTED | `max_upload_bytes`, types, in `/admin/security-policy` and the contract | - | None; re-verify only | - |
| P27.2 | Scanning / retention | N/A-JUSTIFIED / BLOCKED-DECISION | X12 / X13 | - | None (justified) | X12, X13 |
| P27.3 | Additional-document request resource | BLOCKED-DECISION | D10 must define request lifecycle/deadlines; see P25.3 | - | Wait for D10 | D10 |
| P27.4 | Per-document lock/permission flags | IMPLEMENTED-UNTESTED | response hints derive replace/remove/download permissions from active document/current attachable version; no additional policy inferred | `tests/api/test_partner_documents.py` | Run focused test when local PostgreSQL is available; decide whether additional locks are needed | - |
| P27.5 | Multiple documents per category | CLOSED-EXISTING | several logical documents per category; each has versions | - | None; re-verify only | - |
| P28.1 | Partner-visible eligibility outcome | BLOCKED-DECISION | D27 | - | Wait for owner answer D27, then implement the recommended option | D27 |
| P28.2 | Decision date/reason as fields | PARTIAL / IMPLEMENTED-UNTESTED | partner `ApplicationOut` returns `decided_at`; partner-visible reason is D27 | `tests/api/test_applications.py` | Run date behavior test; reason after D27 | D27 |
| P28.3 | Information-request due date/status/link | BLOCKED-DECISION | due-date model and onboarding stages are D10 | - | Wait for D10 | D10 |
| P28.4 | Provisioning timestamps | BLOCKED-DECISION | provisioning timeline is part of onboarding model D10 | - | Wait for D10 | D10 |
| P28.5 | `last_updated` on partner `ApplicationOut` | IMPLEMENTED-UNTESTED | `last_updated` maps to `PortalApplication.updated_at` | `tests/api/test_applications.py` | Run behavior tests when local DB is available | - |
| P29.1 | Onboarding record, checklist/tasks, history, due dates, documents | BLOCKED-DECISION | D10 | - | Wait for owner answer D10, then implement the recommended option | D10 |
| M1 | Assignee picker for non-super roles | CLOSED-TESTED | `GET /admin/assignees` | - | None; re-verify only | - |
| M2 | Six allocation stages | CLOSED-EXISTING | 1:1 mapping, tested by `test_transitions`/`test_reviewer`: expression of interest = `submitted`; `eligibility_verification`; `capability_review`; `commercial_legal_review`; `pilot_onboarding`; `scale_up`. Timestamps/owners/notes via status history | test_transitions, test_reviewer | None; re-verify only | - |
| M3 | Discussion thread per record | CLOSED-TESTED | internal notes and logged communications; external replies D15 | - | None; re-verify only | D15 |
| M4 | Typed launch readiness | CLOSED-TESTED | `LaunchReadinessOut` incl. `pending_items` | - | None; re-verify only | - |
| M5 | Typed org detail with role-limited financial fields | IMPLEMENTED-UNTESTED | response schema and role omission are implemented | `tests/api/test_gap_enquiries.py` | Run focused tests when local PostgreSQL is available | - |
| M6 | Profile-change before/after | IMPLEMENTED-UNTESTED | Revisions retain old/new values; null-clear regression added | Test updated, not run (local PostgreSQL unavailable) | Rerun focused test when local DB is available | - |
| M7 | Criteria exceptions workflow | BLOCKED-DECISION | D5 | - | Wait for owner answer D5, then implement the recommended option | D5 |
| M8 | Strategic queue/owner/target | CLOSED-EXISTING | P9.7 | - | None; re-verify only | P9.7 |
| M9 | Mandatory categories per pathway | BLOCKED-DECISION | D6 (single list today) | - | Wait for owner answer D6, then implement the recommended option | D6 |
| M10 | CMS attachment limits | CLOSED-TESTED | policy endpoint | - | None; re-verify only | - |
| M11 | Meeting calendar/notification | BLOCKED-DECISION / BLOCKED-EXTERNAL | D16 | - | Wait for owner answer D16, then implement the recommended option | D16 |
| M12 | Privacy access/correction completion and legal checks | BLOCKED-DECISION | D4 | - | Wait for owner answer D4, then implement the recommended option | D4 |
| A26.2 | Reset link format | CLOSED-TESTED | `/reset-password?token=` | - | None; re-verify only | - |
| A26.2 | Refresh keeps MFA state | CLOSED-EXISTING | `test_mfa` ("refresh keeps the verified state") | test_mfa | None; re-verify only | - |
| A26.2 | Password policy | CLOSED-TESTED | policy endpoint | - | None; re-verify only | - |
| A26.2 | Staff invitation accept + link | CLOSED-TESTED | `/activate?token=`, `POST /auth/invitations/accept` | - | None; re-verify only | - |
| A26.2 | Token/session lifetimes | CLOSED-TESTED | policy endpoint | - | None; re-verify only | - |
| A26.2 | Partner MFA | CLOSED-TESTED | optional | - | None; re-verify only | - |
| A26.3 | meta keys on every list | CLOSED-TESTED | X1 | - | None; re-verify only | X1 |
| A26.3 | Per-role 403 matrix | CLOSED-TESTED | X8 | - | None; re-verify only | X8 |
| A26.3 | Self-change 409; last super admin | CLOSED-TESTED | `SELF_CHANGE` (`test_gap_accounts`); the last-super-administrator guard exists but cannot be reached through the API because the acting super administrator always remains | test_gap_accounts | None; re-verify only | - |
| A26.3 | CSV exports | CLOSED-TESTED | strategic exclusion; 10,000-row cap checked with a lowered cap (`test_content_list_sort_date_and_csv_cap`) | test_content_list_sort_date_and_csv_cap | None; re-verify only | - |
| A26.3 | Audit values/filters | NOT CLOSED | filters partial match on action and record type (documented); no event catalogue | - | IMPLEMENT: filters partial match on action and record type (documented); no event catalogue | - |
| A26.3 | Outbox field names | CLOSED-TESTED | typed | - | None; re-verify only | - |
| A26.3 | Settings shape | CLOSED-TESTED | typed | - | None; re-verify only | - |
| A26.3 | Partner row field names | CLOSED-TESTED | typed | - | None; re-verify only | - |
| A26.3 | Enquiry document keys; reopen semantics | NOT CLOSED | X3 / D8 | - | IMPLEMENT: X3 / D8 | D8; X3 |
| A26.3 | Profile fields direct vs change request | NOT CLOSED | P26.2 | - | IMPLEMENT: P26 | P26.2 |
| A26.3 | Strategic access matrix | CLOSED-TESTED | X7 | - | None; re-verify only | X7 |
| A26.3 | Meeting end to end | CLOSED-EXISTING | local only | - | None; re-verify only | - |
| A26.3 | Partner isolation | CLOSED-EXISTING | `test_security_p2` | test_security_p2 | None; re-verify only | - |
| A26.3 | Attachment download headers | CLOSED-EXISTING | `attachment`, `Cache-Control: private, no-store` | - | None; re-verify only | - |
| A26.3 | Invitation email delivery; mfa-reset | BLOCKED-EXTERNAL / CLOSED-EXISTING | delivery needs a real provider; reset tested in `test_ops` | test_ops | Needs external access/config: delivery needs a real provider; reset tested in `test_ops` | - |
| A26.3 | Draft/publish on the public site | CLOSED-EXISTING | `test_content_engagement` | test_content_engagement | None; re-verify only | - |

Rows: 188. Count by first status label: BLOCKED-DECISION 31, BLOCKED-EXTERNAL 7, CLOSED-EXISTING 17, CLOSED-TESTED 88, N/A-JUSTIFIED 5, NOT 40.

## Update 2026-11-10 (Claude Code is the active agent)
Verified 2026-11-10 (Claude Code): branch `main`, HEAD `15ebe59`; the working tree is uncommitted and holds the earlier agent's 34 modified files plus this session's changes. Supabase dev (`postgres.zibfzlwzaecapfrgjret`) is at `0012` with no drift (read-only check). **Migrations `0013`, `0014`, `0015` exist and are applied to local disposable databases only; they are NOT applied to Supabase** (needs a fresh approval, a backup and target confirmation).
Closed since this matrix was generated: privacy verification, SEO/media fields, `MeOut` fields, `PATCH /auth/me`, session expiry and revoke-others, MFA disable (partners), partner privacy requests, document-request resource, staff feed. Details: `docs/phase-scope/DEVELOPER_REQUEST_TO_PRD_MAPPING.md` (Update 2026-11-10). Full suite: 270 passed.

## Update 2026-11-10 (second pass)
Authoritative requirement list now: `docs/phase-scope/REQUIREMENT_AUDIT_PHASES_1_3.md`. 273 tests pass. **A new untracked file `scripts/inspect_and_seed.py` appeared that is not from Claude Code: it runs against the `.env` database (Supabase dev) and fails `ruff` (E402). Do not run it without review.** Migrations `0013`-`0015` are local only; Supabase dev is at `0012` (last verified).
