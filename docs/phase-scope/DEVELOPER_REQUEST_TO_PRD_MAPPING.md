# Developer Request -> PRD Phase 1-3 Mapping (2026-11-10)

## Verification update (2026-11-11)

Earlier status entries below are historical. The authoritative current statuses are in `REQUIREMENT_AUDIT_PHASES_1_3.md`; full local suite: 280 passed; development Alembic revision: `0015`; OpenAPI: 162 paths / 291 schemas. Supported integration details are in `frontend-backend-contract.md`. No test accounts were provisioned because approved account identifiers and secure credential delivery are not yet available. Frontend recommendations remain unapproved until the owner confirms them.

Source: "Coral Swift - Backend Requests" (frontend, 2026-11-10). `BACKEND_GAPS.md` and `BACKEND_DEPENDENCY_REGISTER.md` are **not in this repository**; the gap register was used through `docs/backend-gap-audit.md` (item ids X, Phase, M). The developer's "Phase 4-37" labels are not PRD phases: scope is decided by the PRD s.23 release definitions only.

**Evidence rules.** "Verified" means present in commit `15ebe59` and covered by tests that were executed (254 passed on 2026-11-10). The working tree also holds **uncommitted changes from another agent** (34 modified files, migration `0012`, `docs/handoff/*`) that this document did not verify; where they touch an item it is marked `uncommitted work present, unverified`. Nothing was committed, pushed or deployed for this document.

**Statuses:** `IMPLEMENTED_AND_TESTED`, `EXISTING_IMPLEMENTATION_VERIFIED`, `BUSINESS_DECISION_BLOCKED`, `EXTERNAL_CONFIGURATION_BLOCKED`, `OUT_OF_SCOPE_PHASE_4_OR_LATER`, `NOT_APPLICABLE_WITH_JUSTIFICATION`, and `IN_SCOPE_PHASE_n` = in scope, **remaining work** (not yet delivered). Decision ids D1-D27: `docs/business-decisions-required.md`.

## A. Go-live items (all portals)
| ID | Requirement | PRD phase | Status | Evidence | Remaining / dependency |
|---|---|---|---|---|---|
| A1 | CORS for deployed origins | 1-3 | EXTERNAL_CONFIGURATION_BLOCKED | `test_app` preflight tests; value is env `CORS_ALLOWED_ORIGINS` | frontend origins + Render env value |
| A2 | Live test accounts (4 staff roles + MFA, 1 partner) | 2,3 | EXTERNAL_CONFIGURATION_BLOCKED | `scripts/create_staff_user.py` | authorised access to the deployed service |
| A3 | Strategic/M&A authorization everywhere | 3 | IMPLEMENTED_AND_TESTED | `test_strategic_confidentiality.py` (3), `test_admin`, `test_project_partner_strategic` | live re-check with real accounts (A2) |
| A4 | Per-role 403 matrix | 3 | IMPLEMENTED_AND_TESTED | `GET /auth/permissions`; `test_permission_matrix_matches_real_enforcement` | none |
| A5 | Pagination meta on every list | 1-3 | IMPLEMENTED_AND_TESTED | key names `page,page_size,total,pages`; `test_gap_lists` sweep | none |
| A6 | Typed schemas (overview, KPIs, settings, org detail, launch readiness, outbox, partner rows, enquiry detail) | 3 | IN_SCOPE_PHASE_3 (partly done) | typed: settings, launch readiness, outbox, partner notifications/enquiries | typed overview, KPIs, org detail, enquiry detail objects |
| A7 | Strategic flag on audit/outbox/notification rows | 3 | IMPLEMENTED_AND_TESTED | `is_strategic`; `test_gap_phase_a` | none |
| A8 | Session persistence (HttpOnly cookie) / refresh keeps MFA | 2,3 | BUSINESS_DECISION_BLOCKED (D1) | refresh keeps MFA: `test_mfa` (existing, verified) | D1 |
| A9 | Upload safety: scanning | 1-3 | NOT_APPLICABLE_WITH_JUSTIFICATION | owner accepted quarantine-only 2026-11-10; files stay `quarantined` | revisit only if owner reverses |
| A9 | Upload limits documented | 1-3 | IMPLEMENTED_AND_TESTED | `GET /admin/security-policy` | none |
| A9 | Retention dates, secure deletion | 2 | BUSINESS_DECISION_BLOCKED (D4) | purge job tested with fake storage | retention periods and legal checks |
| A10 | Auth details documented | 2 | IMPLEMENTED_AND_TESTED / BUSINESS_DECISION_BLOCKED | link formats `/activate?token=`, `/reset-password?token=`, policy and lifetimes in `/admin/security-policy`; partner MFA currently optional | owner must confirm the partner MFA policy (not invented) |
| A11 | Distinct login errors | 2,3 | IMPLEMENTED_AND_TESTED / BUSINESS_DECISION_BLOCKED (D2) | `ACCOUNT_DEACTIVATED`, `TOKEN_EXPIRED/ALREADY_USED/REVOKED` tested; "not activated" and "locked" stay generic to avoid revealing accounts | D2 |

## B. Admin console (PRD Phase 3)
| ID | Requirement | PRD phase | Status | Evidence | Remaining / dependency |
|---|---|---|---|---|---|
| B-X | Server search, sort, date filters on six lists | 3 | IMPLEMENTED_AND_TESTED | `test_gap_lists`, `test_gap_applications`, `test_gap_phase_a` | none |
| B-X | `updated_at` and actor names | 3 | IMPLEMENTED_AND_TESTED | enquiries, follow-ups, audit, applications | none |
| B-X | `/auth/me` account type | 2,3 | EXISTING_IMPLEMENTATION_VERIFIED | `user_type` returned (`test_auth`); `account_status` added in uncommitted work | verify the uncommitted change |
| B-X | Assignee picker for non-super roles | 3 | IMPLEMENTED_AND_TESTED | `GET /admin/assignees` | none |
| B4-6 | Pending/approved counts | 3 | BUSINESS_DECISION_BLOCKED (D7) | no approved status exists | D7 |
| B4-6 | Recent decisions with timestamp | 3 | IMPLEMENTED_AND_TESTED | `decided_at`, `-updated_at` sort | none |
| B4-6 | Recent onboarding activity feed | 3 | BUSINESS_DECISION_BLOCKED (D10) | - | onboarding model |
| B4-6 | Documents awaiting verification | 3 | IMPLEMENTED_AND_TESTED | `GET /admin/documents` | none |
| B4-6 | Application list rows (name, email, phone, last updated, date filter) | 3 | IMPLEMENTED_AND_TESTED | `primary_contact`, `updated_at`, filters | category = pathway |
| B4-6 | Checklist/scoring, recommend | 3 | BUSINESS_DECISION_BLOCKED (D9) | PRD forbids automated final decisions | D9 |
| B4-6 | Start-review/decision endpoints, valid transitions | 3 | EXISTING_IMPLEMENTATION_VERIFIED | `POST /reviewer/applications/{id}/transition`, `GET /reviewer/transitions`; `test_transitions` | none |
| B4-6 | Reversal/reconsideration; approved state; exceptions; thresholds | 3 | BUSINESS_DECISION_BLOCKED (D11, D7, D5, D6) | six stages map 1:1 to statuses (documented, tested) | D5-D7, D11 |
| B7 | Onboarding records, progress, completion | 2,3 | BUSINESS_DECISION_BLOCKED (D10) | `pilot_onboarding` status only | D10 |
| B7 | Mandatory document categories per pathway | 2,3 | BUSINESS_DECISION_BLOCKED (D6) | one list of seven (`/readiness`) | D6 |
| B13 | Org list contact, filters, sort | 3 | IMPLEMENTED_AND_TESTED | `primary_contact`, `country`, dates, `sort` | none |
| B13 | Org category/type | 3 | BUSINESS_DECISION_BLOCKED (D20) | no field in PRD s.12 | D20 |
| B13 | Org activity history | 3 | IN_SCOPE_PHASE_3 | - | build feed from `activities` |
| B13 | Agreements, relationship manager | later | OUT_OF_SCOPE_PHASE_4_OR_LATER | CRM-like (D21) | none |
| B13 | Staff edit of partner profile | 3 | BUSINESS_DECISION_BLOCKED (D19) | change-request flow exists | D19 |
| B13 | Staff view of change requests with before/after | 3 | IN_SCOPE_PHASE_3 | list/decide exist; diff data missing; uncommitted work present, unverified | build/verify |
| B14 | Partner accounts: list, detail, invitation status/resend/revoke, suspend/reactivate, admin reset, history | 3 | IMPLEMENTED_AND_TESTED | `test_gap_accounts.py` | none |
| B8-11 | Enquiry list fields, filters, sort | 3 | IMPLEMENTED_AND_TESTED | `test_gap_enquiries` | none |
| B8-11 | Activity/assignment history; note types | 3 | IMPLEMENTED_AND_TESTED | `/activity`, follow-up `kind` | none |
| B8-11 | Reply / external message to requester | 3 | BUSINESS_DECISION_BLOCKED (D15) | contact logged as `communication` | D15 |
| B8-11 | Strategic: staff access, queue/owner/target | 3 | EXISTING_IMPLEMENTATION_VERIFIED | `route.owner.strategic`, `sla.strategic` (`test_section28`) | values = D3 |
| B8-11 | Strategic `discussion_type` filter | 3 | IN_SCOPE_PHASE_3 | value shown as row `category` | add filter |
| B8-11 | Assessment outcome endpoint | 3 | BUSINESS_DECISION_BLOCKED (D8) | - | D8 |
| B8-11 | Workload aggregate | 3 | IN_SCOPE_PHASE_3 | - | counts per assignee (no capacity rules, D13) |
| B8-11 | Clear application assignee; six stages | 3 | IMPLEMENTED_AND_TESTED / EXISTING_IMPLEMENTATION_VERIFIED | `reviewer_id: null`; mapping documented | none |
| B8-11 | Follow-ups global list, edit, cancel, counts | 3 | IMPLEMENTED_AND_TESTED | `GET /admin/follow-ups` | none |
| B8-11 | Meeting/calendar integration; meeting assignment workflow | later / 3 | OUT_OF_SCOPE_PHASE_4_OR_LATER / BUSINESS_DECISION_BLOCKED (D14, D16) | staff-attested confirmation exists | D14, D16 |
| B12-16 | Admin document list/filter | 3 | IMPLEMENTED_AND_TESTED | `GET /admin/documents` | none |
| B12-16 | Staff review history; enquiry attachment list | 3 | IN_SCOPE_PHASE_3 | - | build both |
| B12-16 | Admin upload/replace | 3 | BUSINESS_DECISION_BLOCKED (D17) | - | D17 |
| B12-16 | "Replacement requested" status | 3 | BUSINESS_DECISION_BLOCKED (D18) | `clarification_needed` | D18 |
| B12-16 | Admin notification feed (list/read/archive) | 3 | IN_SCOPE_PHASE_3 | outbox only | model + endpoints |
| B12-16 | Ad-hoc email send | 3 | BUSINESS_DECISION_BLOCKED (D15) | - | D15 |
| B12-16 | Delivery status/receipts | 3 | EXTERNAL_CONFIGURATION_BLOCKED | outbox status exists | Brevo webhooks + verified domain |
| B12-16 | Templates: create/activate/placeholders; version history | 3 | IN_SCOPE_PHASE_3 (partly done) | overrides with allow-list (`test_ops`) | placeholder list; versions only if PRD requires |
| B12-16 | Typed outbox rows, date/type filters | 3 | IMPLEMENTED_AND_TESTED | `test_gap_phase_a` | none |
| B12-16 | CMS: homepage/hero/banners/services/industries/navigation | 1,3 | BUSINESS_DECISION_BLOCKED (D23) | pages/articles/resources exist | content model |
| B12-16 | CMS: media, SEO fields | 1,3 | IN_SCOPE_PHASE_1 / IN_SCOPE_PHASE_3 | single attachment only | build |
| B12-16 | CMS: scheduled publish | 3 | IN_SCOPE_PHASE_3 | migration `0012` and edits are uncommitted, unverified | verify/finish, only if approved |
| B12-16 | CMS: unpublish, audit history, sort | 3 | EXISTING_IMPLEMENTATION_VERIFIED / IMPLEMENTED_AND_TESTED | unpublish endpoint, versions, sort/dates | owner field |
| B17-19 | Users: get-by-id, search, pagination, suspend/reactivate, invitation list, per-user activity, four roles | 3 | IMPLEMENTED_AND_TESTED | `test_gap_lists`, `test_gap_accounts` | none |
| B17-19 | Users: profile update | 3 | IN_SCOPE_PHASE_3 | uncommitted `StaffProfileUpdateIn` present, unverified | verify |
| B17-19 | Permission matrix editing | later | OUT_OF_SCOPE_PHASE_4_OR_LATER | view exists; editing D25 | none |
| B17-19 | Reports: filters, aggregates not page-limited | 3 | EXISTING_IMPLEMENTATION_VERIFIED | KPIs computed in SQL | typed KPIs (A6) |
| B17-19 | Reports: review turnaround, partner-account metrics | 3 | IN_SCOPE_PHASE_3 | document turnaround + `portal_adoption` exist | extend |
| B17-19 | PDF/Excel export, advanced analytics | later | OUT_OF_SCOPE_PHASE_4_OR_LATER | CSV exists | none |
| B17-19 | Audit: get-by-id, event catalogue, export | 3 | IN_SCOPE_PHASE_3 | list/search/sort/names done | build |
| B17-19 | Audit: IP/device, before/after values | 3 | BUSINESS_DECISION_BLOCKED | audit `meta` avoids PII by design | privacy decision (D4) |
| B17-19 | Settings typed; security policy; secrets API | 3 | IMPLEMENTED_AND_TESTED / NOT_APPLICABLE_WITH_JUSTIFICATION | secrets never exposed | none |
| B17-19 | 409 on self-change; CSV rules and cap | 3 | IMPLEMENTED_AND_TESTED | `SELF_CHANGE`, CSV cap test | none |
| B-ops | Email provider, storage, monitoring, backups, incident, rollback | 1-3 | EXTERNAL_CONFIGURATION_BLOCKED | `docs/production-readiness-report.md` | operator |
| B-ops | Retention, queue owners, privacy procedure | 2,3 | BUSINESS_DECISION_BLOCKED (D3, D4) | | owner |

## C. Partner portal (PRD Phase 2)
| ID | Requirement | PRD phase | Status | Evidence | Remaining / dependency |
|---|---|---|---|---|---|
| C-acct | Partner roles/permissions model | 2 | BUSINESS_DECISION_BLOCKED (D22) | owner/member membership roles; module list in `/auth/permissions` | D22 |
| C-acct | `MeOut`: role, status, phone, mfa flags, last login | 2 | IN_SCOPE_PHASE_2 | `user_type`, `organization` exist; `account_status` in uncommitted work | add the rest, verify |
| C-acct | Invitations: status, expiry, resend/revoke, rate limit, distinct errors | 2 | IMPLEMENTED_AND_TESTED | `test_gap_accounts` | none |
| C-acct | `PATCH /auth/me` (name, phone) | 2 | IN_SCOPE_PHASE_2 | - | build with audit |
| C-acct | MFA lifecycle: status, disable, re-enroll behaviour | 2 | IN_SCOPE_PHASE_2 | enroll/confirm/verify exist | disable + guard against silent replace |
| C-acct | Sessions: `expires_at`, sign out others; revoke on password change | 2 | IN_SCOPE_PHASE_2 (part done) | revoke on change done; own sessions tested | `expires_at`, `DELETE /auth/sessions` |
| C-acct | Authenticated partner privacy requests | 2 | IN_SCOPE_PHASE_2 | - | `POST/GET /partner/privacy-requests` |
| C-acct | Account closure workflow | 2 | BUSINESS_DECISION_BLOCKED (D4) | | D4 |
| C-acct | VERIFY: own sessions only, revoke invalidates refresh, no secrets in responses | 2 | EXISTING_IMPLEMENTATION_VERIFIED | `test_auth`, `test_security_p2` | `/mfa/enroll` replace-guard check |
| C25-29 | Profile fields beyond PRD s.12 | 2 | BUSINESS_DECISION_BLOCKED (D20) | | D20 |
| C25-29 | Direct vs approval-required field metadata; null-clearing; revisions old/new | 2 | IN_SCOPE_PHASE_2 | history and change requests exist; uncommitted work present, unverified | build/verify |
| C25-29 | Documents: size limit; multiple per category | 2 | IMPLEMENTED_AND_TESTED / EXISTING_IMPLEMENTATION_VERIFIED | policy endpoint; several documents per category | none |
| C25-29 | Document-request resource (deadline, status, link) | 2 | IN_SCOPE_PHASE_2 | information requests exist (`messaging`) | add deadline/status/link |
| C25-29 | Document lock flags | 2 | NOT_APPLICABLE_WITH_JUSTIFICATION | derivable from `review_status`; frontend assumption | none |
| C25-29 | Application status: decision date/reason, `last_updated`, info-request fields, activation timestamps | 2 | IN_SCOPE_PHASE_2 | `decided_at` on reviewer side only | partner payload fields |
| C25-29 | Partner-visible eligibility outcome | 2 | BUSINESS_DECISION_BLOCKED (D27) | | D27 |
| C25-29 | Onboarding record, checklist, history | 2 | BUSINESS_DECISION_BLOCKED (D10) | status `pilot_onboarding` shown | D10 |
| C-notif | Typed feed with read state, unread count, filters | 2 | IMPLEMENTED_AND_TESTED (part) | id, template, status, `read_at`, `meta.unread`, read/read-all | category/title/related record, mark unread |
| C-notif | Notification preferences | later | OUT_OF_SCOPE_PHASE_4_OR_LATER | add-on | none |
| C-notif | Org-wide inbox, attachments, partner-initiated messages | later | OUT_OF_SCOPE_PHASE_4_OR_LATER | per-application reviewer messages exist | none |
| C-notif | Partner discussions, meetings, follow-ups | later | OUT_OF_SCOPE_PHASE_4_OR_LATER | collaboration platform (dev Phases 31-32) | none |
| C30-34 | Projects, team platform, performance scorecards | later | OUT_OF_SCOPE_PHASE_4_OR_LATER | PRD excludes them (s.23) | none |
| C-verify | Cross-partner access blocked everywhere; no strategic/internal content in partner payloads | 2 | IMPLEMENTED_AND_TESTED | `test_security_p2`, `test_gap_lists` inbox | none |

## D. Public portal (PRD Phase 1)
| ID | Requirement | PRD phase | Status | Evidence | Remaining / dependency |
|---|---|---|---|---|---|
| D1 | CORS, HTTPS, SPA fallback, CSP | 1 | EXTERNAL_CONFIGURATION_BLOCKED | | frontend host / edge |
| D2 | CMS content endpoints: hero/banners/services/industries/navigation/media/SEO | 1 | BUSINESS_DECISION_BLOCKED (D23) / IN_SCOPE_PHASE_1 | published pages, articles, FAQs, resources, sitemap exist | D23, then build; draft/publish live check |
| D3 | Public forms: limits, scanning | 1 | IMPLEMENTED_AND_TESTED / NOT_APPLICABLE_WITH_JUSTIFICATION | limits tested; scanning declined | none |
| D3 | Meeting calendar check and notifications | later | OUT_OF_SCOPE_PHASE_4_OR_LATER | unapproved calendar integration | D16 |
| D4 | `POST /privacy/requests` unauthenticated | 1 | IN_SCOPE_PHASE_1 | rate limit + Turnstile exist; no email verification | add confirmation step (needs a token table: next migration) |
| D5 | Newsletter CSV | 3 | EXISTING_IMPLEMENTATION_VERIFIED | `/admin/reports/newsletter.csv` | none |
| D6 | Vendor/subcontracting enquiry as its own path | 1 | IN_SCOPE_PHASE_1 (verify) | partner endpoint has a `pathway` field | confirm a distinct route/classification is required by PRD s.28 |

## Counts of remaining in-scope code
Phase 1: privacy-request verification, SEO/media (after D23), vendor path check. Phase 2: partner `MeOut` fields, `PATCH /auth/me`, MFA disable and sessions, partner privacy requests, document-request resource, partner status fields, field metadata/revisions, notification feed fields. Phase 3: typed overview/KPIs/org detail/enquiry detail, `discussion_type` filter, workload counts, staff document history, attachment list, admin notification feed, template placeholders, audit detail/catalogue/export, report extensions, org activity history, change-request diff, CMS media/SEO (scheduled publish only if approved).

## Update 2026-11-10 (Claude Code continuation) - status changes
Verified 2026-11-10 (Claude Code): branch `main`, HEAD `15ebe59`; the working tree is uncommitted and holds the earlier agent's 34 modified files plus this session's changes. Supabase dev (`postgres.zibfzlwzaecapfrgjret`) is at `0012` with no drift (read-only check). **Migrations `0013`, `0014`, `0015` exist and are applied to local disposable databases only; they are NOT applied to Supabase** (needs a fresh approval, a backup and target confirmation).

Re-verified first: the earlier agent's uncommitted work had **7 failing tests** (typed responses emit `null` keys; a 500 in `GET /admin/reports/follow-ups` caused by a GROUP BY bind-parameter mismatch). Fixed; the full suite was green before new work (257 passed).

| Item | New status | Evidence |
|---|---|---|
| D4 privacy-request email verification (Phase 1) | IMPLEMENTED_AND_TESTED | `POST /privacy/requests/verify`; staff cannot progress/execute an unverified request (409 `EMAIL_NOT_VERIFIED`, rejection allowed); `tests/api/test_phase1_seo_privacy.py` |
| B12-16 / D2 SEO + cover-image fields (Phase 1/3) | IMPLEMENTED_AND_TESTED | 8 nullable fields, https-only, null clears; public only when published; `test_phase1_seo_privacy.py`. Media **library** (upload/manage) still not built (D23 for site structure) |
| C-acct `MeOut` role/status/phone/mfa/last login | IMPLEMENTED_AND_TESTED | `partner_role`, `phone`, `mfa_enabled`, `mfa_required`, `last_login_at`; `test_phase2_account.py` |
| C-acct `PATCH /auth/me` (name, phone) | IMPLEMENTED_AND_TESTED | staff and partners, audited by field name only |
| C-acct sessions `expires_at`, `DELETE /auth/sessions` | IMPLEMENTED_AND_TESTED | `test_phase2_account.py` |
| C-acct MFA disable | IMPLEMENTED_AND_TESTED | partners only, password + current code; staff 403 `MFA_REQUIRED_FOR_STAFF`; **follows the existing "partner MFA optional" behaviour - the owner still has to confirm that policy**; enroll never silently replaces an enabled secret (409 `MFA_ALREADY_ENABLED`) |
| C-acct partner privacy requests | IMPLEMENTED_AND_TESTED | `POST/GET /partner/privacy-requests`, identity from the session; `test_phase2_privacy.py` |
| C25-29 document-request resource | IMPLEMENTED_AND_TESTED | `POST/GET /reviewer/applications/<built-in function id>/document-requests`, `POST /reviewer/document-requests/<built-in function id>/cancel`, `GET /partner/document-requests[/<built-in function id>]`, upload with `request_id` fulfils it; `test_phase2_document_requests.py` |
| C25-29 profile field metadata, revisions old/new, null clearing | EXISTING_IMPLEMENTATION_VERIFIED | earlier agent's uncommitted work: `GET /partner/organization/editable-fields`, revisions carry `{old,new}`; covered by `test_organizations` (passing) |
| B12-16 admin notification feed | IMPLEMENTED_AND_TESTED | `GET /admin/feed`, `POST /admin/feed/<built-in function id>/read`, `/read-all`, `/archive`; own items only; events: reviewer assigned, enquiry assigned, follow-up assigned; `is_strategic` flag, titles carry reference numbers only; `test_phase3_feed.py` |
| B8-11 enquiry attachment list; staff document history; `discussion_type` filter; workload; audit detail/export/catalogue; typed overview/KPIs/org/enquiry detail; template placeholders | EXISTING_IMPLEMENTATION_VERIFIED (uncommitted, earlier agent) | routes present in OpenAPI and exercised by the passing suite; not individually re-reviewed by me |

Still open in scope: notification-feed fields for partners (category/title/related record, mark unread), partner-visible `decision_note` (blocked by D27), staff view of change requests with before/after (verify earlier agent's work), onboarding (D10). Decision-blocked items unchanged.

## Update 2026-11-10 (second pass)
Requirement-level audit with the seven required status labels and completion counts: `REQUIREMENT_AUDIT_PHASES_1_3.md` (139 rows: 89 implemented and tested, 12 implemented not fully verified, 23 decision-blocked, 9 external, 3 out of scope, 3 not applicable, 0 not implemented). Newly closed: partner message fields and unread controls, staff organisation revisions/activity, change-request before values.
