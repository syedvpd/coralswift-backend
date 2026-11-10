# Backend Gap Audit (2026-11-10)

Input: "Coral Swift - Backend Gaps (all sessions, Phase 1 to Phase 29)". Each item was checked against the code, OpenAPI, migrations and tests of this repository, not taken from the register. Evidence tests are under `tests/`. Latest local run: **253 passed** (see `backend-gap-test-report.md`). No live provider, Supabase or deployed check was made for any item.

**Status labels** (final set)
- `CLOSED-TESTED` = CLOSED — IMPLEMENTED AND TESTED (new or changed in this work, local automated tests)
- `CLOSED-EXISTING` = CLOSED — VERIFIED EXISTING IMPLEMENTATION
- `BLOCKED-DECISION` = BLOCKED — BUSINESS DECISION (exact decision in `business-decisions-required.md`, ids D1-D26)
- `BLOCKED-EXTERNAL` = BLOCKED — EXTERNAL CONFIGURATION / ACCESS
- `NOT CLOSED` = NOT CLOSED — IMPLEMENTATION REMAINS (see `backend-gap-implementation-report.md`, "Remaining work")
- `N/A-JUSTIFIED` = NOT APPLICABLE — JUSTIFIED

**Honest summary:** the project is **not** fully closed. Counts by status are at the end. Items marked `NOT CLOSED` need code that was not written in this session.

## X - cross-cutting
| Id | Gap | Status | Evidence / reason |
|---|---|---|---|
| X1 | Pagination meta on every list | CLOSED-TESTED | `page,page_size,total,pages` on every paginated list; sweep test over all list endpoints `test_gap_lists.py::test_every_paginated_list_reports_page_total_and_pages`. Privacy-request and profile-change lists lacked it and were fixed. Small fixed lists are deliberately unpaginated (listed in the test and contract) |
| X2 | Server-side search/sort/date on `/reviewer/applications`, `/admin/organizations`, `/admin/users`, `/admin/notifications`, `/admin/content`, `/admin/audit` | CLOSED-TESTED | all six: `test_gap_applications`, `test_gap_lists`, `test_gap_phase_a` (invalid sort/status values return 422) |
| X3 | Typed schemas for overview, KPIs, settings, org detail, outbox rows, partner notification/enquiry rows, enquiry contact/company/details/documents | NOT CLOSED | typed now: settings, launch-readiness, security-policy, admin outbox rows, partner notification and enquiry rows, follow-ups, audit. **Still untyped dicts:** `/admin/overview`, `/admin/reports/kpis`, `/admin/organizations/{id}`, enquiry detail `contact/company/details/documents` |
| X4 | Updated-at and actor names | CLOSED-TESTED | enquiry rows (`updated_at`, `assigned_user_name`), follow-ups (`author_name`, `assignee_name`), enquiry activity, audit (`actor_name`), reviewer list/detail (`updated_at`, `assigned_reviewer_name`, history `actor_name`, notes `author_name`), accounts. `test_gap_enquiries`, `test_gap_phase_a`, `test_gap_applications` |
| X5 | Transition tables / allowed-next states | NOT CLOSED | **applications: CLOSED-TESTED** (`GET /reviewer/transitions`, `allowed_next` on rows; `test_gap_applications`). **enquiries:** status can be set to any `EnquiryStatus`; restricting it and new statuses ("awaiting response") need a decision (D8) |
| X6 | Strategic flag on audit/outbox/notification rows | CLOSED-TESTED | `is_strategic` on audit and outbox rows (`test_gap_phase_a`). Access control never relies on it |
| X7 | Strategic/M&A authorization on every path | CLOSED-TESTED | `test_strategic_confidentiality.py`: every admin/reviewer GET as BDM, reviewer and content admin; search, CSV, detail, documents, follow-ups, activity, assign/patch, overview and KPI aggregates. Also `test_admin`, `test_project_partner_strategic` |
| X8 | Role-to-module permission matrix | CLOSED-TESTED | `GET /auth/permissions` built from the live route guards (no second source); test calls every staff GET route with all four roles and asserts matrix == enforcement (`test_permission_matrix_matches_real_enforcement`). Partner modules included |
| X9 | CORS for the deployed frontend origin | BLOCKED-EXTERNAL | code and preflight tests exist (`test_app`); the allow-list is the `CORS_ALLOWED_ORIGINS` environment value on Render. No live preflight was run |
| X10 | HttpOnly cookie session / persistence | BLOCKED-DECISION | D1. Tokens are returned in the response body; refresh works with the refresh token |
| X11 | Change-password endpoint | CLOSED-TESTED | `POST /auth/change-password` (staff and partner, other sessions revoked); `test_gap_phase_a` |
| X12 | Malware scanner | N/A-JUSTIFIED | owner formally accepted quarantine-only uploads on 2026-11-10 and declined a scanner. Uploads stay `quarantined`; nothing claims a scan. If the owner reverses, an adapter is needed |
| X13 | Retention dates and secure deletion | BLOCKED-DECISION | mechanism exists and is tested with fake storage (`test_ops::test_retention_purge_and_expiry_reminders`); retention periods and legal checks are D4 |
| X14 | Live authenticated test accounts | BLOCKED-EXTERNAL | needs authorised access to the deployed service and staff creation via `scripts/create_staff_user.py`; none made |

## Phases 1-3 - foundation and authentication
| Id | Gap | Status | Evidence / reason |
|---|---|---|---|
| P1.1 | No API documentation originally | CLOSED-EXISTING | live `/openapi.json`; contract in `frontend-backend-contract.md` |
| P1.2 | CORS rejects origins | BLOCKED-EXTERNAL | see X9 |
| P1.3 | `/auth/me` not staff-only | N/A-JUSTIFIED | one endpoint serves staff and partners by design; `user_type` tells them apart |
| P1.4 | No change-password; memory-only sessions | CLOSED-TESTED / BLOCKED-DECISION | change-password closed (X11); persistence is D1 |
| P1.5 | One generic 401 for every login failure | CLOSED-TESTED / BLOCKED-DECISION | a deactivated account with the **correct** password now gets 403 `ACCOUNT_DEACTIVATED` (`test_gap_phase_a`, `test_auth`). "Not activated" cannot be told apart without revealing which emails have accounts: D2 |
| P1.6 | Login/MFA/me/refresh/logout never tested live | BLOCKED-EXTERNAL | local coverage: `test_auth` (16), `test_mfa` (7). Live = X14 |

## Phase 4 - dashboard
| Id | Gap | Status | Evidence / reason |
|---|---|---|---|
| P4.1 | Pending / Approved application counts | BLOCKED-DECISION | there is no "approved" status; D7 |
| P4.2 | Recent decisions (decision timestamp) | CLOSED-TESTED | `decided_at` on reviewer rows; `updated_at`; sort `-updated_at` |
| P4.3 | Recent onboarding activity feed | NOT CLOSED | no feed endpoint; depends on the onboarding model (D10) |
| P4.4 | Documents awaiting verification | CLOSED-TESTED | `GET /admin/documents?review_status=pending` (`test_gap_reference`) |
| P4.5 | Keys of overview/KPIs undocumented | NOT CLOSED | still untyped (X3); keys are listed in the contract |
| P4.6 | Reviewer list totals/date filter | CLOSED-TESTED | `meta.total` + `submitted_from/to`, `updated_from/to` |

## Phase 5 - applications management
| Id | Gap | Status | Evidence / reason |
|---|---|---|---|
| P5.1 | Search, date range, sort, category filters | CLOSED-TESTED | `q`, dates, `sort`, `pathway`, reviewer, unassigned (no separate "category": pathway is the category) |
| P5.2 | Applicant name/email/phone, last updated on rows | CLOSED-TESTED | `primary_contact` (first authorised contact), `updated_at` |
| P5.3 | Reviewer-name lookup for non-super roles | CLOSED-TESTED | `GET /admin/assignees`, `assigned_reviewer_name` |
| P5.4 | Transition table | CLOSED-TESTED | X5 |
| P5.5 | Pagination meta | CLOSED-TESTED | X1 |

## Phase 6 - review and decision
| Id | Gap | Status | Evidence / reason |
|---|---|---|---|
| P6.1 | Checklist/scoring endpoints | BLOCKED-DECISION | checklist items and scoring are not defined in the PRD; automated scoring is out of scope (D9). Human eligibility records exist (`test_reviewer`) |
| P6.2 | Start-review / recommend / decision endpoints | BLOCKED-DECISION | forward moves and decisions go through `POST /reviewer/applications/{id}/transition` with enforced rules and mandatory reasons (`test_transitions`); a separate "recommend" step is D9 |
| P6.3 | Reversal / reconsideration | BLOCKED-DECISION | D11. Rejected/withdrawn are terminal today |
| P6.4 | No approved status | BLOCKED-DECISION | D7 |
| P6.5 | Actor names on history/notes; updated time | CLOSED-TESTED | `test_gap_applications` |
| P6.6 | Eligibility exception workflow; per-pathway thresholds | BLOCKED-DECISION | PRD requires an "approved internal process" that is not defined: D5, D6 |

## Phase 7 - onboarding and provisioning
| Id | Gap | Status | Evidence / reason |
|---|---|---|---|
| P7.1 | Onboarding records, initiation, progress, completion | BLOCKED-DECISION | PRD names "pilot / onboarding" with milestones and acceptance criteria but defines no tasks: D10 |
| P7.2 | Invitation/account state readable | CLOSED-TESTED | `invitation_state` on `/admin/accounts` (`test_gap_accounts`) |
| P7.3 | List lacks applicant fields/filters | CLOSED-TESTED | P5.1/P5.2 |
| P7.4 | Which document categories are mandatory | CLOSED-EXISTING | `GET /partner/applications/{id}/readiness` lists missing items; the seven PRD s.8 categories; per-pathway differences are D6 |

## Phase 8 - business and project enquiries
| Id | Gap | Status | Evidence / reason |
|---|---|---|---|
| P8.1 | Row fields (phone, category, updated, assignee name) | CLOSED-TESTED | `test_gap_enquiries` |
| P8.2 | Filter by category / IT vs Non-IT, sort | CLOSED-TESTED | `category`, `project_group=it|non_it`, `sort`, `assigned_any`, `updated_from/to` |
| P8.3 | Typed contact/company/details/documents | NOT CLOSED | X3 |
| P8.4 | Activity and assignment history | CLOSED-TESTED | `GET /admin/enquiries/{id}/activity?action=assign` |
| P8.5 | Internal note vs follow-up vs communication | CLOSED-TESTED | `kind` = note / follow_up / communication; a note is not a response, a communication is |
| P8.6 | Status workflow, extra statuses | BLOCKED-DECISION | D8 |
| P8.7 | Assignee lookup for non-super roles | CLOSED-TESTED | `GET /admin/assignees?purpose=enquiries` |

## Phase 9 - strategic / M&A
| Id | Gap | Status | Evidence / reason |
|---|---|---|---|
| P9.1 | Staff read/list access for strategic | CLOSED-TESTED | super administrators only (D12 if BDM should see them); confidentiality tests |
| P9.2 | Strategic category (`discussion_type`) on rows + filter | NOT CLOSED | `category` on rows is done; a `discussion_type` filter is not implemented |
| P9.3 | Notes vs discussion vs follow-up types with visibility | CLOSED-TESTED | follow-up `kind`; strategic enquiries are visible to super administrators only |
| P9.4 | Assessment outcome / decision endpoint, extra statuses | BLOCKED-DECISION | D8 |
| P9.5 | Activity history, assignee names, sort, total | CLOSED-TESTED | P8 endpoints |
| P9.6 | Typed objects | NOT CLOSED | X3 |
| P9.7 | Strategic queue, owner, response target | CLOSED-EXISTING | settings `route.owner.strategic`, `route.backup.strategic`, `sla.strategic`, `escalation.email.strategic` (`test_section28`); values are D3 |

## Phase 10 - assignment
| Id | Gap | Status | Evidence / reason |
|---|---|---|---|
| P10.1 | Assignment history | CLOSED-TESTED | enquiry activity feed; application history |
| P10.2 | Workload/aggregate endpoint, capacity rules | NOT CLOSED | no workload endpoint; capacity rules are D13 |
| P10.3 | Reviewer list owner/search/priority/date filters | CLOSED-TESTED | owner, search, dates done; applications have no priority/follow-up in the PRD (N/A for those two) |
| P10.4 | Clear an application assignment | CLOSED-TESTED | `reviewer_id: null`; reviewer loses access (`test_gap_applications`) |
| P10.5 | Staff list super-admin only | CLOSED-TESTED | `/admin/assignees` |
| P10.6 | Last updated, "any assigned" filter | CLOSED-TESTED | `updated_at`, `assigned_any` |
| P10.7 | Partner/meeting assignment workflow | BLOCKED-DECISION | D14 |
| P10.8 | Statuses vs the six allocation stages | CLOSED-EXISTING | see M2 |

## Phase 11 - follow-ups and discussions
| Id | Gap | Status | Evidence / reason |
|---|---|---|---|
| P11.1 | Global follow-up list | CLOSED-TESTED | `GET /admin/follow-ups` with counts in `meta` |
| P11.2 | Update, reschedule, reassign, cancel; status; assignee | CLOSED-TESTED | `PATCH` and `/cancel` on follow-ups; `status`, `assignee_id` |
| P11.3 | Date filter and counts | CLOSED-TESTED | `due_from`, `due_to`, `counts` open/overdue/upcoming/completed/cancelled |
| P11.4 | Reply to requester / external message; reviewer message POST beyond information requests | BLOCKED-DECISION | D15 (sending ad-hoc email to requesters is an integration decision). Contact is logged with `kind=communication` |
| P11.5 | Follow-up notifications | NOT CLOSED | no staff in-app notification model (see P15.1) |
| P11.6 | Calendar view / integration | BLOCKED-DECISION | D16; real calendar also BLOCKED-EXTERNAL |

## Phase 12 - documents
| Id | Gap | Status | Evidence / reason |
|---|---|---|---|
| P12.1 | Admin document list/filter | CLOSED-TESTED | `GET /admin/documents` (reviewers scoped to assigned organisations) |
| P12.2 | Staff view of per-document review history | NOT CLOSED | partner-side history exists; no staff endpoint |
| P12.3 | Admin upload/replace/delete | BLOCKED-DECISION | D17 (not in PRD; partners own their documents) |
| P12.4 | Document-level notes | CLOSED-EXISTING | `review_comment` per version (`test_reviewer`) |
| P12.5 | Enquiry-attachment list; onboarding documents | NOT CLOSED | attachments are inside enquiry detail; no separate list; onboarding D10 |
| P12.6 | "Replacement requested" status | BLOCKED-DECISION | D18 (uses `clarification_needed`) |
| P12.7 | Malware scanning, retention, deletion | N/A-JUSTIFIED / BLOCKED-DECISION | X12, X13 |

## Phase 13 - partner management
| Id | Gap | Status | Evidence / reason |
|---|---|---|---|
| P13.1 | Staff edit of a partner profile | BLOCKED-DECISION | D19; today partners edit and staff decide change requests |
| P13.2 | Org rows: category/type, contact | CLOSED-TESTED / BLOCKED-DECISION | `primary_contact` done; organisation category/type is a profile-field decision (D20) |
| P13.3 | Filters location, date, sort | CLOSED-TESTED | `country`, dates, `sort` |
| P13.4 | Org activity history, agreements, relationship manager, metrics | NOT CLOSED | org activity feed not built; agreements/relationship manager are D21 |
| P13.5 | Typed org detail; list meta | NOT CLOSED / CLOSED-TESTED | detail untyped (M5); meta done |

## Phase 14 - partner accounts
| Id | Gap | Status | Evidence / reason |
|---|---|---|---|
| P14.1 | Account list/search/detail | CLOSED-TESTED | `GET /admin/accounts`, `/{id}` (`test_gap_accounts`) |
| P14.2 | Invitation status, expiry, resend, revoke | CLOSED-TESTED | states pending/expired/revoked/accepted; rate limited |
| P14.3 | Suspend / reactivate | CLOSED-TESTED | sessions revoked on suspend; self-suspend blocked |
| P14.4 | Partner roles/permissions | CLOSED-TESTED / BLOCKED-DECISION | partner modules in `/auth/permissions`; owner/member membership roles exist; role-specific limits are D22 |
| P14.5 | Admin-initiated password reset | CLOSED-TESTED | emails the holder a link; admins never see or set passwords |
| P14.6 | Account history, filters, metrics | CLOSED-TESTED / NOT CLOSED | history (`recent_activity`) and filters done; account metrics beyond `portal_adoption` not built |
| P14.7 | "Already has an account" read | BLOCKED-DECISION | D2 (account enumeration) |

## Phase 15 - communication and notifications
| Id | Gap | Status | Evidence / reason |
|---|---|---|---|
| P15.1 | Admin notification feed (read/unread/archive/delete) | NOT CLOSED | only the email outbox exists; no in-app staff feed |
| P15.2 | Ad-hoc email, attachments, preferences | BLOCKED-DECISION | D15 |
| P15.3 | Communication history by record | CLOSED-TESTED | follow-ups `kind=communication` + activity feed |
| P15.4 | Delivered/opened receipts | BLOCKED-EXTERNAL | needs Brevo webhooks and a verified domain |
| P15.5 | Template create/activate/versions/placeholder list | NOT CLOSED | overrides with an allow-list exist (`test_ops`); versioning and a placeholder list endpoint are not built |
| P15.6 | Outbox filters and typed rows | CLOSED-TESTED | status, template, q, dates, sort; typed |

## Phase 16 - CMS
| Id | Gap | Status | Evidence / reason |
|---|---|---|---|
| P16.1 | Homepage/hero/banners/services/menus | BLOCKED-DECISION | D23 (content model not specified) |
| P16.2 | Media library and image upload | NOT CLOSED | only a single attachment per item exists |
| P16.3 | SEO fields | NOT CLOSED | not implemented |
| P16.4 | Scheduled publication; category filter; sort | NOT CLOSED / CLOSED-TESTED | sort and date range done; scheduled publication not built |
| P16.5 | "Unpublished" status; audit history; owner | CLOSED-EXISTING | unpublish endpoint, version history; owner field not added |
| P16.6 | Rich text | BLOCKED-DECISION | D23 |
| P16.7 | Content Administrator permissions | CLOSED-TESTED | visible in the permission matrix; approval needs a super administrator (D24) |

## Phase 17 - users and roles
| Id | Gap | Status | Evidence / reason |
|---|---|---|---|
| P17.1 | Get by id, search, pagination | CLOSED-TESTED | `/admin/users` (q, status, sort, meta), `/admin/accounts/{id}` |
| P17.2 | Profile update; contact fields | NOT CLOSED | name/email change not built |
| P17.3 | Permission matrix; editing | CLOSED-TESTED / BLOCKED-DECISION | view done; editing permissions D25 |
| P17.4 | Suspend/reactivate; admin reset; invitation list/resend | CLOSED-TESTED | accounts endpoints |
| P17.5 | Dates; per-user activity; typed status | CLOSED-TESTED | |
| P17.6 | Reviewer and content-admin roles confirmed | CLOSED-TESTED | all four roles exercised in the matrix test |

## Phase 18 - reports
| Id | Gap | Status | Evidence / reason |
|---|---|---|---|
| P18.1 | Date filters on applications / partners / outbox | CLOSED-TESTED | |
| P18.2 | Assignee/category filters; IT/Non-IT | CLOSED-TESTED | |
| P18.3 | Turnaround, onboarding, document KPIs | NOT CLOSED | document review turnaround exists; onboarding KPIs depend on D10 |
| P18.4 | Partner-account metrics, follow-up trends | NOT CLOSED | `portal_adoption` and follow-up counts exist; trends not built |
| P18.5 | Document-review / communication reports | NOT CLOSED | |
| P18.6 | PDF / Excel export, CSV titles | BLOCKED-DECISION | D26 (optional per PRD; CSV only today) |
| P18.7 | Typed KPI/overview totals | NOT CLOSED | X3 |

## Phase 19 - audit and settings
| Id | Gap | Status | Evidence / reason |
|---|---|---|---|
| P19.1 | Audit get-by-id, search, sort, total | CLOSED-TESTED / NOT CLOSED | search/sort/total done; get-by-id not built |
| P19.2 | Outcome, IP/device, before/after, event catalogue, export, security classification | NOT CLOSED | audit `meta` carries no PII by design; the rest is not built |
| P19.3 | Typed settings, definitions | CLOSED-TESTED | `GET /admin/settings` |
| P19.4 | Security-policy API | CLOSED-TESTED | read-only `GET /admin/security-policy` |
| P19.5 | Secrets API | N/A-JUSTIFIED | secrets are never exposed or edited through the API |

## Phases 20-21 - integration and production readiness
| Id | Gap | Status | Evidence / reason |
|---|---|---|---|
| P20.1 | Business decisions (thresholds, retention, owners, providers) | BLOCKED-DECISION | see `business-decisions-required.md` |
| P20.2 | Meeting confirm/decline/cancel and requester notification | CLOSED-EXISTING | `test_content_engagement`; real calendar BLOCKED-EXTERNAL (M11) |
| P20.3 | Own sessions and recovery codes | CLOSED-EXISTING | `/auth/sessions`, `/auth/mfa/recovery-codes` |
| P20.4 | Health page, newsletter CSV | CLOSED-EXISTING | `/health*`, `/admin/reports/newsletter.csv` |
| P20.5 | SPA fallback, HTTPS, CSP | BLOCKED-EXTERNAL | frontend host and edge |
| P20.6 | Privacy procedure and legal retention checks | BLOCKED-DECISION | D4 |

## Phases 22-23 - partner foundation and authentication
| Id | Gap | Status | Evidence / reason |
|---|---|---|---|
| P22.1 | Partner roles/permissions in the contract | CLOSED-TESTED | `/auth/permissions` for partners; membership roles in the contract |
| P22.2 | Partner MFA policy; session timing | CLOSED-TESTED | MFA optional for partners (enforced once enabled, `test_mfa`); lifetimes in `/admin/security-policy` |
| P22.3 | Change password; persistence | CLOSED-TESTED / BLOCKED-DECISION | X11 / D1 |
| P22.4 | Unactivated vs suspended | CLOSED-TESTED / BLOCKED-DECISION | P1.5 |

## Phase 24 - invitation and activation
| Id | Gap | Status | Evidence / reason |
|---|---|---|---|
| P24.1 | Invitation state and delivery result | CLOSED-TESTED / NOT CLOSED | state done; delivery result is not linked on the account row |
| P24.2 | Resend/revoke with rate limit | CLOSED-TESTED | `test_invitation_actions_are_rate_limited` |
| P24.3 | Distinct expired/used/revoked codes | CLOSED-TESTED | `TOKEN_EXPIRED`, `TOKEN_ALREADY_USED`, `TOKEN_REVOKED`, `INVALID_OR_EXPIRED_TOKEN` |
| P24.4 | Password policy documented | CLOSED-TESTED | `/admin/security-policy`, contract |
| P24.5 | Link target | CLOSED-TESTED | `{PORTAL_BASE_URL}/activate?token=` (asserted); reset `/reset-password?token=` |
| P24.6 | Provisioning history action names | CLOSED-TESTED | `auth.invitation_issued`, `_resent`, `_revoked`, `auth.account_activated` in account activity |

## Phase 25 - partner dashboard
| Id | Gap | Status | Evidence / reason |
|---|---|---|---|
| P25.1 | In-app feed, read state, unread count | CLOSED-TESTED | `GET /partner/notifications`, `POST .../{id}/read`, `read-all` (`test_gap_lists`) |
| P25.2 | Typed notification and enquiry rows | CLOSED-TESTED | |
| P25.3 | Document-request resource | NOT CLOSED | information requests exist; a separate resource with deadlines is not built (D10) |
| P25.4 | Account status on `/auth/me` | NOT CLOSED | |

## Phase 26 - company profile
| Id | Gap | Status | Evidence / reason |
|---|---|---|---|
| P26.1 | Missing profile fields | BLOCKED-DECISION | D20 (not in PRD s.12 field list) |
| P26.2 | Editable vs approval-required metadata | NOT CLOSED | rules exist in code; not exposed or documented as an endpoint |
| P26.3 | Previous/new values in revisions | NOT CLOSED | |
| P26.4 | Null-clearing semantics | NOT CLOSED | |

## Phase 27 - partner documents
| Id | Gap | Status | Evidence / reason |
|---|---|---|---|
| P27.1 | File size limit documented | CLOSED-TESTED | `max_upload_bytes`, types, in `/admin/security-policy` and the contract |
| P27.2 | Scanning / retention | N/A-JUSTIFIED / BLOCKED-DECISION | X12 / X13 |
| P27.3 | Additional-document request resource | NOT CLOSED | see P25.3 |
| P27.4 | Per-document lock/permission flags | NOT CLOSED | |
| P27.5 | Multiple documents per category | CLOSED-EXISTING | several logical documents per category; each has versions |

## Phases 28-29 - application tracking and onboarding
| Id | Gap | Status | Evidence / reason |
|---|---|---|---|
| P28.1 | Partner-visible eligibility outcome | BLOCKED-DECISION | D27 |
| P28.2 | Decision date/reason as fields | NOT CLOSED | `decided_at` on reviewer rows; partner payload not extended |
| P28.3 | Information-request due date/status/link | NOT CLOSED | |
| P28.4 | Provisioning timestamps | NOT CLOSED | |
| P28.5 | `last_updated` on partner `ApplicationOut` | NOT CLOSED | |
| P29.1 | Onboarding record, checklist/tasks, history, due dates, documents | BLOCKED-DECISION | D10 |

## M - addendum
| Id | Gap | Status | Evidence / reason |
|---|---|---|---|
| M1 | Assignee picker for non-super roles | CLOSED-TESTED | `GET /admin/assignees` |
| M2 | Six allocation stages | CLOSED-EXISTING | 1:1 mapping, tested by `test_transitions`/`test_reviewer`: expression of interest = `submitted`; `eligibility_verification`; `capability_review`; `commercial_legal_review`; `pilot_onboarding`; `scale_up`. Timestamps/owners/notes via status history |
| M3 | Discussion thread per record | CLOSED-TESTED | internal notes and logged communications; external replies D15 |
| M4 | Typed launch readiness | CLOSED-TESTED | `LaunchReadinessOut` incl. `pending_items` |
| M5 | Typed org detail with role-limited financial fields | NOT CLOSED | |
| M6 | Profile-change before/after | NOT CLOSED | |
| M7 | Criteria exceptions workflow | BLOCKED-DECISION | D5 |
| M8 | Strategic queue/owner/target | CLOSED-EXISTING | P9.7 |
| M9 | Mandatory categories per pathway | BLOCKED-DECISION | D6 (single list today) |
| M10 | CMS attachment limits | CLOSED-TESTED | policy endpoint |
| M11 | Meeting calendar/notification | BLOCKED-DECISION / BLOCKED-EXTERNAL | D16 |
| M12 | Privacy access/correction completion and legal checks | BLOCKED-DECISION | D4 |

## 26.2 - auth/session details
| Item | Status | Evidence |
|---|---|---|
| Reset link format | CLOSED-TESTED | `/reset-password?token=` |
| Refresh keeps MFA state | CLOSED-EXISTING | `test_mfa` ("refresh keeps the verified state") |
| Password policy | CLOSED-TESTED | policy endpoint |
| Staff invitation accept + link | CLOSED-TESTED | `/activate?token=`, `POST /auth/invitations/accept` |
| Token/session lifetimes | CLOSED-TESTED | policy endpoint |
| Partner MFA | CLOSED-TESTED | optional |

## 26.3 - behaviour to verify
| Item | Status | Evidence |
|---|---|---|
| meta keys on every list | CLOSED-TESTED | X1 |
| Per-role 403 matrix | CLOSED-TESTED | X8 |
| Self-change 409; last super admin | CLOSED-TESTED | `SELF_CHANGE` (`test_gap_accounts`); the last-super-administrator guard exists but cannot be reached through the API because the acting super administrator always remains |
| CSV exports | CLOSED-TESTED | strategic exclusion; 10,000-row cap checked with a lowered cap (`test_content_list_sort_date_and_csv_cap`) |
| Audit values/filters | NOT CLOSED | filters partial match on action and record type (documented); no event catalogue |
| Outbox field names | CLOSED-TESTED | typed |
| Settings shape | CLOSED-TESTED | typed |
| Partner row field names | CLOSED-TESTED | typed |
| Enquiry document keys; reopen semantics | NOT CLOSED | X3 / D8 |
| Profile fields direct vs change request | NOT CLOSED | P26.2 |
| Strategic access matrix | CLOSED-TESTED | X7 |
| Meeting end to end | CLOSED-EXISTING | local only |
| Partner isolation | CLOSED-EXISTING | `test_security_p2` |
| Attachment download headers | CLOSED-EXISTING | `attachment`, `Cache-Control: private, no-store` |
| Invitation email delivery; mfa-reset | BLOCKED-EXTERNAL / CLOSED-EXISTING | delivery needs a real provider; reset tested in `test_ops` |
| Draft/publish on the public site | CLOSED-EXISTING | `test_content_engagement` |

## 26.4 - operations
All BLOCKED-EXTERNAL or BLOCKED-DECISION: email provider and delivery confirmation, private storage evidence, monitoring, backups, incident response, rollback evidence, CRM/calendar/analytics/ticketing, SPA fallback/HTTPS/CSP, named queue owners and targets. `openapi.json` must be re-published after endpoint changes (it is generated by the app; see the contract).

## Counts
Rows classified: see `backend-gap-implementation-report.md` for the tally. Items needing no further code that the owner or an operator must still supply are listed in `business-decisions-required.md` and `production-readiness-report.md`.
