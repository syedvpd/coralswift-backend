# Backend Requirements Traceability (PRD v2.0 -> backend)

Source of truth: Coral Swift PRD v2.0 (30 sections). Frontend-only items are listed as `FE` and excluded from backend scope.
The original planning tables below retain their historical labels for context. The evidence-based Phase 1 verification status as of 2026-11-09, using the required audit status vocabulary, is in section F. `OWN` indicates a business-owner dependency; `ADD` indicates an optional add-on.

## A. Requirement register

| ID | PRD § | Requirement | Ph | Flags | Module / API | Tests | Dependency |
|---|---|---|---|---|---|---|---|
| R-001 | 1,16 | FastAPI/PostgreSQL REST backend, documented APIs (OpenAPI) | 0 | | app core, /docs | api/test_app | - |
| R-002 | 16,17 | Env separation dev/staging/prod, secrets not in code, prod config validation | 0 | | core.config | unit/test_config | OWN hosting choice |
| R-003 | 16,19 | HTTPS-ready, secure headers, CORS, trusted hosts | 0 | | core.security | api/test_app | TLS at proxy |
| R-004 | 16,17 | Monitoring/logging, request IDs, no PII/secrets in logs | 0 | | core.logging | unit/test_logging | OWN error-monitoring vendor |
| R-005 | 17 | Health/readiness | 0 | | /health* | api/test_health | - |
| R-006 | 17,22 | Migrations, CI/CD, staging/prod separation | 0 | | alembic, Docker | integration/test_database | OWN CI vendor |
| R-010 | 12,16 | Server-side validation of all public forms | 1 | | pydantic schemas | api/test_*_validation | - |
| R-011 | 12 | Country-aware phone + business email validation | 1 | | common.validation | unit/test_validation | OWN: free-email policy |
| R-012 | 12,28 | Privacy notice + explicit consent captured and stored with timestamp/version | 1 | OWN | contacts.consent_* | api/test_contact | Legal-approved notice text |
| R-013 | 12,16 | Submission reference number + confirmation response | 1 | | enquiries.reference_number, sequence | api/test_contact, integration/test_reference | - |
| R-014 | 12 | Rate limiting, bot/spam protection, duplicate-submission handling | 1 | OWN | core.protection, idempotency | api/test_security_p1, test_idempotency | OWN CAPTCHA vendor |
| R-015 | 12,28 | Form failure handling: no silent failure, retry guidance, admin alert on notification failure | 1 | | notifications outbox, logs | unit/test_notifications | Admin alert UI = Phase 3 |
| R-016 | 12,28 | File type/size restrictions, secure upload | 1 | | documents | unit/test_files, api/test_documents | - |
| R-020 | 12 | General contact form (name, company, email, phone, country, type, message, consent) | 1 | | POST /enquiries/contact | api/test_contact | - |
| R-021 | 9,12 | Project enquiry form, IT/Non-IT categories, scope, timeline, volume, geography, security constraints, optional docs | 1 | | POST /enquiries/project | api/test_project | - |
| R-022 | 9 | Categories are illustrative, never live contracts | 1 | | enums + docs | api/test_project | FE label |
| R-023 | 8,12 | Partner application form incl. company profile, workforce, turnover, services, experience, infrastructure, pathway | 1 | | POST /enquiries/partner | api/test_partner | - |
| R-024 | 8,28 | Capture 8 initial submission items (registration, 3-yr history, employees, financials, portfolio, infrastructure, 2 client references, authorized contact) | 1 | | documents.category, client_references, contact | api/test_partner | OWN: which are mandatory at submit (assumed: references mandatory, documents optional) |
| R-025 | 8,28 | Proposed thresholds (3 yr, 50 staff, INR 2 cr) recorded, conditional by pathway, never auto-approve/reject | 1 | OWN | partner_applications (bands only) | api/test_partner | OWN: applicability per pathway; band edges assumed |
| R-026 | 8 | Thresholds shown as proposed, not guarantee | FE | | response text only | - | FE copy |
| R-027 | 12 | Strategic discussion form, confidential record | 1 | | POST /enquiries/strategic | api/test_strategic | OWN: designated owner |
| R-028 | 11,28 | Strategic/financial data access-restricted, excluded from public search/listing | 1 | | access_classification, no list/read endpoints | api/test_strategic | RBAC = Phase 3 |
| R-029 | 12,19 | Private document storage, signed/controlled access, no public URLs | 1 | | storage adapter, documents | api/test_documents | OWN storage vendor (S3 chosen, creds pending) |
| R-030 | 19,13 | Malware scanning where available; retention + secure deletion | 1/2 | OWN | upload_status=quarantined, documents.retention_date | unit/test_files | OWN scanner + retention policy |
| R-031 | 15B,11 | Routing to correct queue per type, ack email, internal notification | 1 | OWN | notify_*_emails settings, notifications | unit/test_notifications | OWN queue owners/addresses |
| R-032 | 11,15F | Transactional email with provider, SPF/DKIM/DMARC | 1 | OWN | integrations.email (Brevo) | unit/test_notifications | Brevo key (pending), DNS auth |
| R-033 | 28 | Do not promise response times until SLAs approved | 1 | OWN | email templates | unit/test_notifications | OWN SLA |
| R-034 | 28 | Data minimisation: no patient/banking/account data fields | 1 | | schemas have no such fields | api/test_project | - |
| R-035 | 18,20 | Activity/audit record for submissions & notification outcomes | 1 | | activities | integration/test_activity | - |
| R-036 | 12 | Secure public status lookup (unguessable) | 1 | | GET /enquiries/{ref}/status | api/test_status | - |
| R-037 | 5,25 | Hyderabad/US claims, partner names not published | FE/OWN | OWN | none (no partner-name endpoint) | - | Verification register |
| R-040 | 13 | Partner secure sign-in, MFA, profile, dashboard, doc requests | 2 | | - | - | - |
| R-041 | 11,28 | Six-stage evaluation workflow & reviewer checklist, eligibility rules engine | 2/3 | | - | - | OWN thresholds |
| R-042 | 13 | Partner document management, audit of downloads | 2 | | - | - | - |
| R-050 | 14 | Admin console, roles (SuperAdmin, BDM, Reviewer, Content Admin), RBAC | 3 | | - | - | - |
| R-051 | 14,20 | Lead assignment, follow-ups, reports, CSV export, audit-log UI | 3 | | enquiries.assigned_owner reserved | - | - |
| R-052 | 14,28 | Content approval workflow, content register, last-reviewed dates | 3 | | - | - | OWN content owners |
| R-053 | 15H | Retention/deletion controls, backup restore tests, incident process | 3 | OWN | - | - | OWN policy |
| R-054 | 28 | Operational SLAs, escalation, out-of-office | 3 | OWN | - | - | OWN |
| R-060 | 12,15D | Meeting request: preferred times/TZ, confirm only after real calendar booking | 4 | ADD,OWN | NOT built | - | Calendar provider + availability API |
| R-061 | 15F | CRM sync, calendar, analytics, ticket integrations | 4 | ADD,OWN | integrations/ placeholders only | - | Vendor choice |
| R-062 | 15I | Partner directory, capability filters, scorecards, automation | 4 | ADD | - | - | Approved partners |
| R-063 | 15C,E | FAQ/knowledge base, resource centre/insights CMS, newsletter opt-in | 3/4 | ADD | - | - | Content |
| R-064 | 15A | Trust centre, case studies, credentials (evidence-gated) | FE/3 | ADD,OWN | - | - | Verified claims |
| R-065 | 15G | Multilingual, USD/INR display | 4 | ADD | - | - | Demand |
| R-070 | 20 | Analytics events & KPIs | FE/4 | OWN | none in Phase 1 (consent-gated, client side) | - | Consent banner |
| R-071 | 20 | SEO (sitemap, metadata) | FE | | - | - | - |
| R-072 | 16 | Accessibility WCAG 2.2, responsive, Core Web Vitals | FE | | - | - | - |
| R-073 | 23 | Out of scope: payments, e-sign, marketplace, auto partner decisions, public partner docs | - | | enforced by absence | - | - |
| R-074 | 4,6,7,10 | Branding, copy, page content, logo | FE | | - | - | - |
| R-075 | 25,29 | Open decisions (legal name, domain, contacts, hosting, vendors, launch) | - | OWN | tracked below | - | Business owner |

## B. Phase 1 mapping (model / API / service / security / test)

| Req | Model | API | Service | Security control | Test file |
|---|---|---|---|---|---|
| R-020 | Company, Contact, Enquiry | POST /enquiries/contact | enquiries.service.create_contact | validation, rate limit, bot hook, idempotency | api/test_contact |
| R-021 | + ProjectEnquiry | POST /enquiries/project | projects.service | + doc ownership check | api/test_project |
| R-023/024/025 | + PartnerApplication, Document | POST /enquiries/partner | partners.service | no auto decision (CHECK enums only); restricted docs | api/test_partner |
| R-027/028 | + StrategicEnquiry (confidential) | POST /enquiries/strategic | strategic.service | confidential classification, no read API, no body in logs | api/test_strategic |
| R-016/029/030 | Document | POST /documents/upload | documents.service/files | allowlist+magic bytes, size cap, server keys, SHA-256, quarantine, private storage | unit/test_files, api/test_documents |
| R-013 | Enquiry + sequence | all submits | enquiries.service.next_reference | UNIQUE + DB sequence | integration/test_reference |
| R-031/032/033/015 | Notification | (background) | notifications.service | outbox after commit, dedupe_key, retry cap, no secrets/PII in logs | unit/test_notifications |
| R-014 | IdempotencyKey | Idempotency-Key header | common.idempotency | unique claim, payload hash, TTL | api/test_idempotency |
| R-036 | Enquiry | GET /enquiries/{ref}/status | enquiries.service | HMAC lookup token, identical 404, rate limit | api/test_status |
| R-035 | Activity | - | enquiries.service.log_activity | no PII in metadata | integration/test_activity |

## C. Gap analysis (before proceeding)

Found while comparing the plan/schema with the PRD:

1. **Document retention date** (PRD s.18 Document entity) missing from migration 0002 -> add additive migration **0003** (`documents.retention_date`, nullable; value stays null until retention policy is approved).
2. **Meeting request** (s.12/15D) -> intentionally **not built**: add-on, needs real calendar availability. No endpoint, no fake confirmations.
3. **Eligibility thresholds** -> only banded values recorded. Band edges (e.g. 50-100, INR 2-10 crore) and per-pathway applicability are assumptions; flagged OWN.
4. **Admin alert on notification failure** (s.28) -> Phase 1 records `failed` status + ERROR log; alert UI/queue is Phase 3.
5. **Data minimisation** -> no free-text field is validated for health/bank data; only guidance. Content scanning would be an invented rule; left to the business owner.
6. **Internal notification routing** -> four env-configurable recipient lists; empty until owners named (s.25). No internal mail is sent otherwise.
7. **Free-email-domain rejection** ("business email") -> not implemented (policy decision).
8. **Content governance, analytics, CRM/calendar, directory, scorecards** -> deferred (R-052, R-061..R-070).
9. **Privacy notice text/version** -> setting `PRIVACY_NOTICE_VERSION=draft-unapproved` stored with each consent until legal approves.
10. **Environment**: S3 and Brevo credentials not yet supplied; real delivery/storage not verified (adapters tested with fakes/stubs only).

No requirement was dropped silently; items not built are listed above or in the register.

## D. Migration 0002 review

Reviewed before relying on it: UUID PKs, UTC `timestamptz`, FKs `RESTRICT` (no cascading deletes; notifications `SET NULL`), unique reference/storage key/dedupe/idempotency scope, CHECKs (enum values, ISO-2 country, E.164 phone, lowercase email, positive size, 64-char checksum, owner consistency, >=1 service category, >=2 client references), indexes on FKs and on (type,status,created_at). All DDL is additive (creates only; downgrade drops only objects created by 0002). **Note:** it was applied to the local Docker dev database (`localhost:5433/coralswift`, empty at the time) before this review was complete; nothing was applied to any remote database.

## E. Open business decisions (from PRD s.25) affecting the backend

Legal/brand name; US entity; contact details; queue owners & addresses; SLA wording; privacy/retention policy; threshold applicability by pathway; CAPTCHA, malware scanner, email DNS, storage and hosting vendors; partner-name publication gate; launch date.


## F. Phase 1 verification status (2026-11-09)

No row is VERIFIED: the configured disposable test DB could not be reached, so no pytest run completed. File and code inspection establish implementation locations only; see [phase-1-verification-report.md](../qa/phase-1-verification-report.md) for command results and limitations.

| Requirement ID | PRD section | Implementation location | API/model/service references | Test references | Status | Verification result | Outstanding dependency |
|---|---|---|---|---|---|---|---|
| R-010 | 12,16 | `app/modules/*/schemas.py`, `app/common/validation.py` | four submission schemas | `tests/api/test_contact.py`, `test_project_partner_strategic.py` | IMPLEMENTED | Validation code inspected; tests not run | Run test DB suite |
| R-011 | 12 | `app/common/validation.py` | email and phone validators | `tests/api/test_contact.py` (invalid email and phone cases) | IMPLEMENTED | Validators exist; tests not run | Free-email rejection policy undecided |
| R-012 | 12,28 | `app/modules/enquiries/models.py`, settings | consent fields and notice version | `tests/api/test_contact.py` | BLOCKED | Consent capture code inspected; legal text remains draft | Legal-approved notice/version |
| R-013 | 12 | `migrations/versions/20261109_0002_phase_1_public_submissions.py`, enquiry service | unique reference and DB sequence | `tests/api/test_idempotency.py` | IMPLEMENTED | Migration/service inspected; DB behavior not tested | Run integration suite |
| R-014 | 12,16 | `app/core/protection.py`, `app/common/idempotency.py` | rate limits, bot hook, idempotency | `tests/api/test_documents_status_security.py`, `test_idempotency.py` | IMPLEMENTED | Code inspected; bot verifier defaults to no-op; tests not run | Choose/configure CAPTCHA; verify proxy rate limit |
| R-015 | 12,28 | `app/modules/notifications/*` | outbox, delivery status, retry service | `tests/api/test_notifications.py` | IMPLEMENTED | Retry fix and outbox implementation not re-executed | Run regression suite; operational alert owner |
| R-016 | 12 | `app/modules/documents/*` | upload validation and storage service | `tests/unit/test_adapters.py`, `tests/api/test_documents_status_security.py` | IMPLEMENTED | Local adapter smoke passed; full validation tests not run | Run API tests |
| R-020 | 12 | `app/modules/enquiries/*` | contact route/schema/service | `tests/api/test_contact.py` | IMPLEMENTED | Implementation inspected; endpoint tests not run | Run API tests |
| R-021 | 9,12 | `app/modules/projects/*` | project route/schema/service | `tests/api/test_project_partner_strategic.py` | IMPLEMENTED | Implementation inspected; endpoint tests not run | Run API tests |
| R-022 | 9 | project enums and API contract | category enums; contract disclaimer | `tests/api/test_project_partner_strategic.py` | IMPLEMENTED | Contract/code inspected; test not run | Frontend must retain illustrative label |
| R-023 | 8,12 | `app/modules/partners/*` | partner route/schema/service | `tests/api/test_project_partner_strategic.py` | IMPLEMENTED | Implementation inspected; endpoint tests not run | Run API tests |
| R-024 | 8,28 | partner schemas/models/documents | checklist fields and references | `tests/api/test_project_partner_strategic.py` | IMPLEMENTED | Code inspected; mandatory document policy is assumed | Confirm submission checklist policy; run tests |
| R-025 | 8,28 | `app/modules/partners/*` | workforce/turnover bands; no auto-decision | `tests/api/test_project_partner_strategic.py` | BLOCKED | Banded capture inspected; pathway applicability/edges are assumptions | Business approval of bands and pathway applicability |
| R-027 | 12 | `app/modules/strategic/*` | strategic route/schema/service | `tests/api/test_project_partner_strategic.py` | IMPLEMENTED | Confidential submission implementation inspected; tests not run | Name authorized queue owner |
| R-028 | 11,28 | strategic model/service and public router inventory | confidential classification; no public listing route | `tests/api/test_project_partner_strategic.py` | IMPLEMENTED | No public listing route found; access tests not run | Verify role/object controls when staff access exists |
| R-029 | 12,19 | `app/integrations/storage.py`, document service | local/S3 adapters and storage key | `tests/unit/test_adapters.py`, document API tests | BLOCKED | Local adapter smoke passed; S3 operations/private policy unverified | Confirm both configured buckets are private |
| R-030 | 13,19 | document model and migration 0003 | nullable `retention_date`; quarantined upload state | `tests/unit/test_adapters.py` | NOT IMPLEMENTED | Retention date exists; malware scanning and retention/deletion jobs are absent | Approve retention policy and malware-scanner provider |
| R-031 | 15B,11 | settings and notification service | configurable queue recipients | `tests/api/test_notifications.py` | BLOCKED | Routing code inspected; real owners/addresses not configured | Business owners and recipient lists |
| R-032 | 15F | `app/integrations/email.py` | console/Brevo adapters | `tests/unit/test_adapters.py`, `tests/api/test_notifications.py` | BLOCKED | Adapter/mock test references inspected; no real Brevo test | Brevo credentials, sender, SPF/DKIM/DMARC |
| R-033 | 28 | `app/modules/notifications/templates.py` | email templates | `tests/api/test_notifications.py` | IMPLEMENTED | Templates inspected; delivery/render tests not run | SLA approval before promising response times |
| R-034 | 28 | submission schemas and strategic model | no dedicated patient/banking fields | project/strategic API tests | IMPLEMENTED | Schema/model inspection only; tests not run | Run negative/validation tests |
| R-035 | 18,20 | `app/modules/enquiries/activity.py`, models | submission/activity/outbox persistence | `tests/integration/test_database.py` | IMPLEMENTED | Code inspected; database persistence not tested | Run integration tests |
| R-036 | 12 | enquiry router/service and security helpers | HMAC lookup token; status endpoint | `tests/api/test_documents_status_security.py` | IMPLEMENTED | Route/control inspected; enumeration and token tests not run | Run API tests |
| R-060 | 12,15D | no implementation in Phase 1 | meeting request/calendar booking | none | NOT APPLICABLE | Explicitly excluded from Phase 1; optional Phase 4 add-on | Calendar availability/provider decision before Phase 4 |


---

# Phase 2 - Partner Portal traceability (added 2026-11-09)

Phase 1 acceptance is unchanged (**FAIL - NOT ACCEPTED**, see `docs/qa/phase-1-verification-report.md`); Phase 2 was started on explicit user instruction.
Statuses: NOT STARTED, IN PROGRESS, IMPLEMENTED, VERIFIED, BLOCKED, BUSINESS DECISION REQUIRED. "Evidence" is filled only from runs recorded in
`docs/qa/phase-2-implementation-report.md`.

| ID | PRD § | Requirement | Module | Entities | API (under /api/v1) | Security control | Tests | Status | Evidence / dependency |
|---|---|---|---|---|---|---|---|---|---|
| P2-001 | 13,22,23 | Partner account access ("registration") | auth | users, auth_tokens, partner_memberships | POST /auth/invitations/accept, POST /reviewer/invitations | invitation-only, hashed single-use token | tests/api/test_auth.py | VERIFIED | BUSINESS DECISION REQUIRED: invitation vs self-registration |
| P2-002 | 13 | Secure sign-in, session expiry | auth | users, auth_sessions | POST /auth/login, GET /auth/me | Argon2id, generic errors, lockout, rate limit | test_auth.py | VERIFIED | |
| P2-003 | 13 | Logout / session revocation, token renewal | auth | auth_sessions | POST /auth/logout, /auth/refresh, GET/DELETE /auth/sessions | refresh rotation + replay revoke | test_auth.py | VERIFIED | |
| P2-004 | 13 | Password reset | auth | auth_tokens | POST /auth/password-reset/request, /confirm | no account enumeration, single-use, 1h TTL | test_auth.py | VERIFIED | |
| P2-005 | 13,19 | MFA for privileged users; consider for partners | auth | users.mfa_*, mfa_recovery_codes, auth_sessions.mfa_verified_at | POST /auth/mfa/enroll, /confirm, /verify | TOTP (RFC 6238), encrypted secret, replay-proof, hashed single-use recovery codes, lockout, staff sessions limited until verified | tests/api/test_mfa.py (written, NOT executed) | IMPLEMENTED | Migration 0007 not yet applied anywhere; tests pending; partners optional (PRD: consider) |
| P2-006 | 13,14 | Role-based access (reviewer, super admin) | auth | users.staff_role | dependencies | deny by default | test_authorization.py | VERIFIED | Full RBAC admin = Phase 3 |
| P2-007 | 13 | Account activation / deactivation | auth | users.status | (script / reviewer) | old tokens fail immediately | test_auth.py | VERIFIED | |
| P2-010 | 13 | Company profile + completion indicator | organizations | partner_organizations | GET/PUT /partner/organization, GET .../completion | org-scoped queries | test_organizations.py | VERIFIED | |
| P2-011 | 13 | Profile update / change history | organizations | partner_profile_revisions | GET /partner/organization/history | append-only revisions | test_organizations.py | VERIFIED | |
| P2-012 | 8,28 | Authorised contacts, client references, capabilities, turnover, staff, history | organizations | partner_organizations | PUT /partner/organization | validation | test_organizations.py | VERIFIED | |
| P2-013 | 28 | No uncontrolled org duplication / merging | organizations | partner_organizations | invitation targets org explicitly | no email-based merge | test_organizations.py | VERIFIED | |
| P2-020 | 8,13 | Private document upload, categories (7 + authorised contact) | partner_documents | partner_documents, versions | POST /partner/documents | allow-list, magic bytes, size, server keys | test_partner_documents.py | VERIFIED | |
| P2-021 | 13 | Versioning, replacement, history | partner_documents | versions | POST .../versions, GET .../history | immutable versions | test_partner_documents.py | VERIFIED | |
| P2-022 | 13,19 | Authorised download only, no public URLs | partner_documents | - | GET /partner/documents/{id}/download | ownership / assignment check, audit | test_partner_documents.py | VERIFIED | |
| P2-023 | 13 | Malware scanning where available | partner_documents | upload_status | - | quarantined state | - | BLOCKED | No scanner configured; not claimed |
| P2-024 | 13,19 | Retention + secure deletion | partner_documents | retention_date | DELETE /partner/documents/{id} (soft) | no data destroyed | test_partner_documents.py | BUSINESS DECISION REQUIRED | Retention period undefined |
| P2-025 | 13 | Document review status + comments | reviews | versions.review_* | POST /reviewer/documents/{vid}/review | assigned-reviewer check | test_reviewer.py | VERIFIED | |
| P2-026 | 13 | Expiry tracking | partner_documents | versions.expires_on | upload param | - | test_partner_documents.py | IMPLEMENTED | |
| P2-030 | 11,28 | Draft, validate, submit application | applications | portal_applications, submissions | POST/PATCH /partner/applications, POST .../submit | completeness gate, row lock | test_applications.py | VERIFIED | |
| P2-031 | 11,28 | Six evaluation stages as separate statuses with timestamps, owners, notes | applications | status_history | reviewer transition endpoint | central state machine | test_transitions.py | VERIFIED | Terminology: no "approved" in PRD |
| P2-032 | 13 | Status tracking + history for partner | applications | status_history | GET /partner/applications/{id}, /history | partner-safe schema | test_applications.py | VERIFIED | |
| P2-033 | 11 | Additional info request / response / resubmission | messaging | application_messages | POST .../information-requests, .../respond, .../resubmit | linked to application | test_messaging.py | VERIFIED | |
| P2-034 | 11 | Withdrawal | applications | - | POST .../withdraw | partner action only | test_applications.py | VERIFIED | Not named in PRD (proposed) |
| P2-035 | 28 | Prevent duplicate / concurrent submission | applications | partial unique index | submit | lock + unique | test_concurrency.py | VERIFIED | Business rule unconfirmed |
| P2-040 | 8,28 | Eligibility verification as human record (3y / 50 staff / INR 2cr proposed) | reviews | eligibility_verifications | POST /reviewer/applications/{id}/eligibility-verifications | no automatic outcome | test_reviewer.py | VERIFIED | Thresholds + per-pathway applicability: BUSINESS DECISION REQUIRED |
| P2-050 | 14,11 | Reviewer assignment, queue, details | reviews | portal_applications.assigned_reviewer_id | /reviewer/applications* | assigned-only access | test_reviewer.py | VERIFIED | Assigner = super admin (decision pending) |
| P2-051 | 14 | Internal notes separate from partner messages | reviews | reviewer_notes | POST/GET .../notes | never in partner schemas | test_security_p2.py | VERIFIED | |
| P2-052 | 14,11 | Decision recording with reason | applications | status_history | transition endpoint | reason required | test_transitions.py | VERIFIED | |
| P2-060 | 13 | Notifications (invite, reset, submitted, info request, response, status, decision) | notifications | notifications | outbox | dedupe key, scrubbed tokens | test_notifications_p2.py | IMPLEMENTED | Brevo untested; console only |
| P2-070 | 19,13 | Audit trail with actor, org, request id; immutable | audit | activities | GET .../history (reviewer) | DB trigger blocks UPDATE/DELETE | test_audit.py | VERIFIED | |
| P2-080 | 19 | Org isolation / IDOR / privilege escalation tests | all | - | all | 404 on foreign ids | test_security_p2.py | VERIFIED | |
| P2-081 | 21 | Concurrency (submit, decisions, replacement, notifications) | all | - | - | row locks, unique keys | test_concurrency.py | VERIFIED | |
| P2-082 | 21 | End-to-end partner journey | all | - | - | - | test_e2e_journey.py | VERIFIED | |

## Phase 2 items not in scope (accounted for)
Admin dashboard, global user admin, reporting, CSV (Phase 3: R-050..R-054); partner directory, scoring, automation (Phase 4: R-062); payments, e-signature, marketplace (PRD s.23 out of scope);
meeting requests / calendar (R-060, Phase 4, needs approved calendar); content governance (R-052). Phase 1 items in R-0xx remain as recorded above.


## Phase 2 verification evidence (2026-11-09)
Runs on the local Docker database `coralswift_p2_test` (never Supabase): `ruff check .` pass; `ruff format --check .` 151 files formatted; `mypy` no issues in 131 files;
`pytest -q` **176 passed, 0 failed**. Phase 2 test files: `tests/api/test_auth.py`, `test_organizations.py`, `test_partner_documents.py`, `test_applications.py`,
`test_reviewer.py`, `test_security_p2.py`, `test_audit_e2e.py`, `test_concurrency_p2.py`, `tests/unit/test_transitions.py` (these replace the planned names in the table above).
Not verified: real S3, real Brevo delivery, malware scanning, live-server sweep of Phase 2 routes, behaviour against the Supabase database (migrations applied, app not exercised).
P2-026: expiry date is stored and returned; no expiry enforcement or reminders. P2-060: outbox, templates, dedupe, retry verified with fakes; delivery unverified.
P2-005 (MFA) implemented after this evidence was collected (migration 0007 + tests/api/test_mfa.py, not yet run). P2-023 (malware scan) BLOCKED. P2-024 and the policy items remain BUSINESS DECISION REQUIRED.


## Phase 3 (admin)
Traceability: `docs/requirements/phase-3-traceability.md` (P3-001..P3-011). Status: implemented, nothing executed.
