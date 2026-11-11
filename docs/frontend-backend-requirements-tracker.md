# Frontend -> Backend Requirements Tracker (2026-11-11)

Source: frontend email "CoralSwift frontend - backend requirements" (P1 / P2 / P3 / decisions), received 2026-11-11. Baseline: branch `claude/coralswift-backend-requirements-26403a`, HEAD `6ad57a7`, working tree clean at start. Migration head in the repo is `0015` (`20261110_0015_staff_notification_feed.py`); the claim "development DB at 0015" comes from `docs/handoff/SUPABASE_MIGRATION_PLAN.md` and was **not re-checked against the remote DB in this session**. No remote DB, deploy, commit, push or backup action was taken.

## How to read this file

Status values: **DONE** (code + passing test cited), **PARTIAL** (some of the item is done; missing part named), **MISSING** (approved scope, not built), **BLOCKED** (needs external input/credentials/hosting), **DECISION REQUIRED** (owner decision in `docs/business-decisions-required.md`, ids D1-D39), **OUT OF APPROVED SCOPE** (no longer used: on 2026-11-11 the owner authorised every requested feature, so former exclusions were built).

Evidence rules: "Test" names a file under `tests/`. Full-suite evidence for this session: baseline `333 passed` before changes; final run recorded at the bottom (section "Test evidence"). A DONE row whose test was written in earlier sessions was not re-reviewed line by line in this session; it is covered by the full-suite run. OpenAPI column: `yes` = present in `docs/api/openapi.json` (165 paths / 297 schemas, regenerated from `create_app()` on 2026-11-11 after this session's changes); `n/a` = no API surface. **No live deployed OpenAPI was republished or checked; local generation only.**

Gap-closure pass 2 (2026-11-11, owner authorisation): projects, org inbox, discussions/meetings/follow-ups, team management, notification preferences, account closure request, onboarding, review checklist/exceptions/stage owners/reopen, assessment outcomes, enquiry reply, staff document upload/replace, replacement_requested, template versions, CMS blocks + media, audit origin/outcome, KPI filters + turnaround, bounce webhook, purge endpoint, extended profile, performance foundation. Migrations 0016-0023. Rows below reflect this; rows for items built in pass 1 follow.

Changes made in pass 1 (all local, uncommitted): `GET/PATCH /admin/users/{id}`, `GET /admin/users/{id}/activity`, `GET /reviewer/workload`, `ACCOUNT_LOCKED` (423) login error, `scan_status` field on document payloads, regenerated OpenAPI, generated `docs/api/role-permission-matrix.md`, tests `tests/api/test_requirements_batch.py`, this tracker, decisions D30-D39.

---

## P1 - Go-live blockers

| ID | Requirement | Status | Implementation / endpoint / file | Missing / blocker (owner) | Test evidence | OpenAPI |
|---|---|---|---|---|---|---|
| P1-01a | CORS: allow deployed admin, partner, public origins + `http://localhost:5173` | BLOCKED | `CORS_ALLOWED_ORIGINS` env on Render. **Live preflight 2026-11-11** to `/api/v1/auth/login`: `Origin: https://coralswift.com` -> 200; `Origin: http://localhost:5173` -> **400**. `.env.render` lists only `https://coralswift-ochre.vercel.app`; dashboard values may differ | Update the Render env var (no Render API key or dashboard access from here); exact admin/partner production origins not supplied | `test_app.py` (local); live curl above | n/a |
| P1-01b | Preflight for `/auth/login`: methods, headers, credentials | DONE (local) | Allowed methods `GET POST PUT PATCH DELETE OPTIONS`; headers `Authorization, Content-Type, Idempotency-Key, X-Bot-Token, X-Lookup-Token, X-Request-ID`; credentials true; exposed `X-Request-ID, Idempotent-Replay, Retry-After` | Not live-verified against the deployed host | `test_app.py` preflight cases | n/a |
| P1-02 | Test environment: 4 staff roles with MFA, 2 partner orgs, 1 invited-inactive partner, test mailbox, privacy token | BLOCKED | Nothing provisioned. No approved test identities (emails) or secure credential channel were supplied; the dev database holds 5 users and 2 organisations of unknown origin that were not touched | Owner: email aliases + delivery channel (`docs/EXTERNAL-CONFIGURATION-CHECKLIST.md` item 2) | local fixtures only | n/a |
| P1-03a | Strategic/M&A visible only to permitted staff on list, detail, search, CSV, documents, outbox, audit, overview/KPIs, notifications | DONE (local) | `admin/service.py::visible_types`; strategic = **super administrator only** (BDM, reviewer, content admin excluded; D12 default) | Permitted-role set is a policy (D12); live check blocked on P1-02 | `test_strategic_confidentiality.py` (3 tests: every admin GET, exports/search/detail, aggregates), `test_project_partner_strategic` | yes |
| P1-03b | Strategic never in partner payloads | DONE (local) | partner routers query partner-owned rows only | none | `test_security_p2.py`, `test_project_partner_strategic` | yes |
| P1-03c | `strategic` flag on audit, outbox, notification rows | DONE | `is_strategic` on `AuditRow`, `NotificationRow`, staff feed items | Name differs: field is `is_strategic` | `test_gap_phase_a.py` | yes |
| P1-03d | Remove regex-based hiding | DONE (backend side) | flag is server-computed; frontend must switch to `is_strategic` | frontend change | `test_gap_phase_a.py` | yes |
| P1-04 | Partner isolation: org from token only; cross-org 403/404 on applications, messages, notifications, documents, attachments, team/project | DONE | Org from the session on every `/partner/*` route; team, projects, inbox, discussions/meetings/follow-ups, onboarding, performance all return 404 for other organisations | Live check blocked on P1-02 | `test_security_p2.py`, `test_collaboration.py`, `test_team_prefs_onboarding.py`, `test_profile_performance.py` | yes |
| P1-05 | Per-role 403 matrix | DONE | Generated from route guards: `docs/api/role-permission-matrix.md` (112 staff rows, 48 non-staff rows); live via `GET /auth/permissions` | row-level limits (reviewer assigned orgs only, BDM no financial docs) are service-layer, noted in the matrix header | `test_gap_phase_a.py::test_permission_matrix_matches_real_enforcement` | yes |
| P1-06a | Upload size/type limits documented (staff, partner, public, CMS) | PARTIAL | `GET /admin/security-policy` (`max_upload_bytes` 10 MiB default, `allowed_upload_types` pdf/png/jpg/docx/xlsx, `max_documents_per_enquiry`); request body cap `MAX_REQUEST_BODY_BYTES`; explicit 413/415 | CMS attachment limits not separately documented; no staff upload exists (D17) | `test_public_website_readiness.py`, `test_partner_documents.py` | yes |
| P1-06b | `scan_status` on documents | DONE (honest foundation) | `app/modules/documents/scan.py`: computed field returns `not_scanned` on partner version, admin queue, enquiry attachment and public upload payloads. Never returns `clean`. Existing `upload_status=quarantined` unchanged | none | `test_requirements_batch.py::test_documents_report_not_scanned_never_clean` | yes |
| P1-06c | Block download/review until clean | DECISION REQUIRED | Owner accepted quarantine-only 2026-11-10, so downloads by authorised staff/owner are allowed while quarantined and every download is audited. Active scanning requested again by the frontend: **D33**. Not enabled, no provider chosen, no file is ever labelled clean | D33 (owner): provider (e.g. ClamAV container vs managed service) and whether download/review must wait for `clean` | n/a | n/a |
| P1-06d | `retention_until` and auditable hard delete | DONE (mechanism, blocked by policy) | `retention_until` on admin document rows; `POST /admin/documents/{id}/purge` answers 409 `RETENTION_POLICY_NOT_APPROVED` until `retention.partner_document_days` is set after legal sign-off, then also requires removed + retention ended; audited | Retention periods and legal procedure D4 | `test_cms_audit_batch.py` | yes |
| P1-07 | Private storage, authenticated access, audited downloads | PARTIAL | Code path: authenticated streaming downloads, audited (allowed). Denied downloads return 404/403 and are not individually audited. Bucket public-access settings **not inspected** (no provider access): `.env.render` shows `STORAGE_BACKEND=s3` with an endpoint, two buckets named by `S3_BUCKET`, `S3_PARTNER_BUCKET` | Provider evidence of block-public-access (DevOps); audit of denied downloads not built | `test_partner_documents.py`, `test_security_p2.py` | yes |
| P1-08a | Distinct login errors: deactivated/suspended | DONE | 403 `ACCOUNT_DEACTIVATED` only after the correct password (suspend = deactivated status) | wording "suspended" = same code | `test_auth.py`, `test_gap_accounts.py` | yes |
| P1-08b | Distinct login error: locked | DONE (changed this session) | 423 `ACCOUNT_LOCKED` only when the correct password is presented while locked; wrong password still generic 401 | Conflicts with the recommendation in D2 (keep generic); owner to confirm (D37) | `test_auth.py::test_lockout_after_repeated_failures_even_with_correct_password` (updated) | yes (error codes are not in the schema) |
| P1-08c | Distinct login error: not activated (invited) | DECISION REQUIRED | Generic 401 (invited users have no password, so there is nothing to prove; a distinct error would reveal which emails are invited) | D2 / D37 | `test_auth.py` | n/a |
| P1-08d | Distinct invitation errors expired / used / revoked | DONE | 400 `TOKEN_EXPIRED`, `TOKEN_ALREADY_USED`, `TOKEN_REVOKED`, `INVALID_OR_EXPIRED_TOKEN` on `/auth/invitations/accept` and `/auth/password-reset/confirm` | none | `test_gap_accounts.py` | yes |
| P1-09a | Reset link format | DONE (documented) | `{PORTAL_BASE_URL}/reset-password?token=` (matches frontend assumption) | none | `test_auth.py` | n/a |
| P1-09b | Activation link format | DONE (documented) - **mismatch** | Actual: `{PORTAL_BASE_URL}/activate?token=`. Frontend assumed `/partner/activate?token=` | Frontend must change, or owner chooses a path (D38) | `test_auth.py` | n/a |
| P1-09c | Password policy | DONE (documented) - **mismatch** | Default `PASSWORD_MIN_LENGTH=12` (config floor 8), not 8; policy also rejects weak/email-containing passwords (`WEAK_PASSWORD` 422). Live values: `GET /admin/security-policy` | Frontend assumed 8 | `test_auth.py` | yes |
| P1-09d | Access / refresh lifetimes, staff and partner | DONE (documented) | Access 30 min, refresh 10080 min (7 days), identical for staff and partner; reset 60 min; invitation 168 h; lockout after 5 failures for 15 min | Values are env-configurable; deployed values not inspected | `test_auth.py` | yes |
| P1-09e | Partner MFA policy | DECISION REQUIRED | Partner MFA optional; staff MFA required by default (`STAFF_MFA_REQUIRED=true`) | D28 | `test_mfa.py` | n/a |
| P1-09f | `/auth/refresh` keeps MFA-verified state | DONE | session carries `mfa_verified`; rotation preserves it, reuse of an old refresh token revokes the session | none | `test_mfa.py` | yes |
| P1-10a | Public form protection: how `X-Bot-Token` is obtained | DONE (documented) | Cloudflare Turnstile widget token generated client-side; no backend endpoint issues tokens; verified server-side against Cloudflare `siteverify`, single use, hostname allowlist `TURNSTILE_ALLOWED_HOSTNAMES` in hardened envs | Live verification blocked: Turnstile dev keys held only in git-ignored `.env.render`, `CAPTCHA_ENABLED=false` until frontend sends the header; secret was pasted in chat and must be rotated before staging | `test_botcheck` (app/config/botcheck focused suite), `test_public_website_readiness.py` | yes |
| P1-10b | Rate limits + duplicate handling documented | DONE (documented) | `rate_limit("submit")` on the four enquiry endpoints, meetings, privacy, newsletter; `upload` limit 2; global `RATE_LIMIT_PER_MINUTE` default 10 per client per bucket; duplicates handled by `Idempotency-Key` (24 h, replay header `Idempotent-Replay`) on `POST /enquiries/*` and `/meetings`; 429 `TOO_MANY_REQUESTS` | exact deployed rate values are env-driven | `test_public_website_readiness.py` | yes |
| P1-11 | Public privacy requests: email verification + rate limit, lifecycle, SLA | DONE (mechanism); DECISION REQUIRED (legal SLA) | Verification link single-use; TTL from `privacy.verification_hours` (default 72 h provisional); `privacy.completion_days` (unset by default) drives `completion_due_at` and `is_overdue` on admin rows; unverified requests cannot be progressed. No legal compliance is claimed | Legal confirmation and owner of requests (D34) | `test_phase1_seo_privacy.py`, `test_final_decisions.py::test_privacy_sla_is_configurable_and_never_claims_legal_compliance` | yes |

---

## P2 - Partner portal

### Projects and engagements

| ID | Requirement | Status | Existing / missing | Test | OpenAPI |
|---|---|---|---|---|---|
| P2-01a | `GET /partner/projects[/{id}]` shared-only, reference/title/category/status+label/milestones/contact | DONE | `app/modules/collaboration`; `status_label` partner wording; unshared = 404 | none | `test_collaboration.py` | yes |
| P2-01b | Acknowledge / confirm / respond / submit-information | DONE | `POST /partner/projects/{id}/{acknowledge,confirm,respond,submit-information}`; closed projects 409 `PROJECT_CLOSED`; documents must be the organisation's own | none | `test_collaboration.py` | yes |
| P2-01c | Admin share/unshare; links to documents and messages | DONE | `/reviewer/projects` CRUD, `/share`, `/unshare`, milestones, `/documents` link; messages link via `project_id` | none | `test_collaboration.py` | yes |

### Onboarding

| ID | Requirement | Status | Existing / missing | Test | OpenAPI |
|---|---|---|---|---|---|
| P2-02a | Onboarding record with reference, stages, timestamps | DONE | Staff configure tasks per organisation; no stage names or deadlines are invented (D10 owner confirmation of initial stages pending) | D10 initial stage list | `test_team_prefs_onboarding.py` | yes |
| P2-02b | Partner-visible checklist | DONE | tasks: name, status, required_action, due_date, completed_at, document_category, `is_overdue`, `partner_visible` | none | `test_team_prefs_onboarding.py` | yes |
| P2-02c | Provisioning and activation dates | DONE | `provisioned_at` (record created), `first_login_at` (first partner session) | exact meaning of activation date to be confirmed | `test_team_prefs_onboarding.py` | yes |

### Document requests

| ID | Requirement | Status | Existing / missing | Test | OpenAPI |
|---|---|---|---|---|---|
| P2-03a | Document request resource with deadline, status, linked document | DONE | `GET /partner/document-requests[/{id}]` (`meta.open`), reviewer `POST/GET /reviewer/applications/{id}/document-requests`, cancel; upload with `request_id` fulfils it (`REQUEST_CLOSED`, `CATEGORY_MISMATCH`, 404 for other org) | `test_phase2_document_requests.py` | yes |
| P2-03b | Mandatory document categories per pathway | DECISION REQUIRED | One list of seven in `/readiness`; per-pathway list = D6 | `test_applications.py` | yes |

### Applications

| ID | Requirement | Status | Existing / missing | Test | OpenAPI |
|---|---|---|---|---|---|
| P2-04a | `last_updated`, decision date | DONE | `last_updated`, `decided_at` on partner application payload | `test_gap_applications.py`, `test_applications.py` | yes |
| P2-04b | Partner-visible eligibility outcome, decision reason | DONE | `decided_at`, `status_label` and `decision_explanation` (latest reviewer-written partner note on a decision; internal `reason` never returned) per D27. No thresholds are evaluated (D6) | Pathway thresholds D6 remain pending | `test_final_decisions.py::test_information_request_due_date_and_decision_explanation` | yes |
| P2-04c | Information requests with due date, status, document link | DONE | `due_date`, `is_overdue`, `status` (open/answered), `requested_categories`; `next_information_due` on the application; documents upload against document requests | none | `test_final_decisions.py` | yes |
| P2-04d | Typed message `kind` enum | DONE | `MessageKind` enum in applications/constants, in OpenAPI | `test_gap_lists.py` | yes |

### Notifications

| ID | Requirement | Status | Existing / missing | Test | OpenAPI |
|---|---|---|---|---|---|
| P2-05a | Typed rows: category, title, description, related record, link | DONE | `description` (fixed text per template), `related_record {type, reference}`, `link` (assumed portal route `/applications?reference=`; frontend to confirm) | Frontend route confirmation | `test_final_decisions.py::test_notification_description_related_record_and_link` | yes |
| P2-05b | Documented category enum | DONE | enum in `PartnerNotificationOut.category`; listed in `docs/frontend-backend-contract.md` | `test_gap_lists.py` | yes |
| P2-05c | `meta.total` | DONE | list meta has `page, page_size, total, pages` plus `unread` | `test_gap_lists.py` pagination sweep | yes |
| P2-05d | GET/PUT `/partner/notification-preferences`; mandatory notices fixed | DONE | mandatory: `account`, `application` (D42); optional: `acknowledgement` | none | `test_team_prefs_onboarding.py` | yes |

### Messages

| ID | Requirement | Status | Existing / missing | Test | OpenAPI |
|---|---|---|---|---|---|
| P2-06a | Org-wide inbox list/detail, read state, attachments | DONE | `GET /partner/messages[/{id}]`, `/read`, `/unread`, `meta.unread`; attachments are the organisation's documents | none | `test_collaboration.py` | yes |
| P2-06b | Partner-initiated messages | DONE | `POST /partner/messages` (optional `project_id`, `document_ids`) | none | `test_collaboration.py` | yes |
| P2-06c | Approved sender label | DECISION REQUIRED | Staff messages carry the constant label `CoralSwift Team`; staff names never reach partners. A list of approved labels needs your answer | D30 | `test_collaboration.py` | yes |
| P2-06d | Admin send partner-visible message with `partner_visible` | DONE | `POST /reviewer/partner-messages {partner_visible}`; false = staff-only note | none | `test_collaboration.py` | yes |

### Discussions, meetings, follow-ups

| ID | Requirement | Status | Existing / missing | Test | OpenAPI |
|---|---|---|---|---|---|
| P2-07a | `/partner/discussions` list/detail/respond | DONE | respond actions: reply | none | `test_collaboration.py` | yes |
| P2-07b | `/partner/meetings` list/detail/respond | DONE | respond: reply, accept, decline; no calendar integration (D16) | calendar provider D16 | `test_collaboration.py` | yes |
| P2-07c | `/partner/follow-ups` list/detail/respond | DONE | respond: reply, complete | none | `test_collaboration.py` | yes |
| P2-07d | Admin visibility of partner responses | DONE | `GET /reviewer/collaboration[/{id}]`, `has_partner_response` filter, `response_count` | none | `test_collaboration.py` | yes |

### Team management

| ID | Requirement | Status | Existing / missing | Test | OpenAPI |
|---|---|---|---|---|---|
| P2-08a | `GET /partner/team[/{id}]` | DONE | paginated, includes invited members | none | `test_team_prefs_onboarding.py` | yes |
| P2-08b | Partner roles/permissions; `MeOut` role + permissions | DONE | Roles stay Owner and Member (D22); `MeOut.permissions` owner: `team.manage`, member: none | none | `test_team_prefs_onboarding.py` | yes |
| P2-08c | Invite, resend, cancel, role change, activate/deactivate, remove | DONE | `/partner/team/invitations`, `/{id}/resend`, `/cancel`, `PATCH /{id}/role`, `/deactivate`, `/activate`, `DELETE /{id}`; owners only | none | `test_team_prefs_onboarding.py` | yes |
| P2-08d | Last-admin, self-elevation, cross-org protection | DONE | 409 `LAST_OWNER`, 409 `SELF_CHANGE`, 403 for members, 404 across organisations; sessions revoked on role change/deactivate/remove | none | `test_team_prefs_onboarding.py` | yes |
| P2-08e | Ownership transfer, audit, admin visibility | DONE | `POST /partner/team/transfer-ownership`, audit with `organization_id`, staff read-only list `GET /reviewer/organizations/{id}/team` (super admin; reviewer assigned orgs; BDM assigned orgs) | none | `test_final_decisions.py::test_staff_team_list_for_admins_and_reviewer_scope`, `test_team_prefs_onboarding.py` | yes |

### Settings and security

| ID | Requirement | Status | Existing / missing | Test | OpenAPI |
|---|---|---|---|---|---|
| P2-09a | `PATCH /auth/me` name + phone | DONE | E.164 phone, null clears, audited by field name | `test_phase2_account.py` | yes |
| P2-09b | `MeOut`: status, phone, MFA enabled/required, last login | DONE | all five fields | `test_phase2_account.py` | yes |
| P2-09c | MFA status/disable; second enrollment | DONE | `POST /auth/mfa/disable` (partners; password+code), staff 403 `MFA_REQUIRED_FOR_STAFF`; second enroll 409 `MFA_ALREADY_ENABLED` | `test_phase2_account.py`, `test_mfa.py` | yes |
| P2-09d | Session `expires_at`; `DELETE /auth/sessions` | DONE | | `test_phase2_account.py` | yes |
| P2-09e | Revoke sessions on password change and deactivation | DONE | change-password signs out other sessions; deactivate/role change revoke all | `test_auth.py`, `test_gap_accounts.py` | yes |
| P2-09f | Authenticated partner privacy requests | DONE | `POST/GET /partner/privacy-requests`, identity from token | `test_phase2_privacy.py` | yes |
| P2-09g | Account closure with retention check | DONE (request); DECISION REQUIRED (execution rules) | `GET /partner/account-closure/preview`, `POST /partner/account-closure` (owner, password re-entry; blockers: open applications, other members, open document requests) records a deletion privacy request; nothing is deleted | Retention/deletion rules D4 | `test_team_prefs_onboarding.py` | yes |

### Partner profile

| ID | Requirement | Status | Existing / missing | Test | OpenAPI |
|---|---|---|---|---|---|
| P2-10a | Extra profile fields | DONE | 13 fields; `company_type` and `operating_model` are enforced enums (D44); `additional_contacts` visible to super admin only | none | `test_profile_performance.py`, `test_d39_d45.py::test_d44_enumerations_are_enforced_by_api` | yes |
| P2-10b | Direct edit vs change request marking | DONE | D19: `GET /partner/organization/editable-fields` -> `direct_update` (fill a still-empty field) and `approval_required` (changing/clearing an existing value). `PUT /partner/organization` answers 409 `CHANGE_REQUEST_REQUIRED` for any existing value; `legal_name` is change-request only | none | `test_organizations.py`, `test_phase3_org_history.py`, `test_profile_performance.py` | yes |
| P2-10c | Null-clearing | DONE | Explicit `null` in a change request clears the field when approved (legal_name cannot be cleared: 422). Direct null on an existing value -> 409 | none | `test_profile_performance.py` | yes |
| P2-10d | Before/after in revisions | DONE | `GET /partner/organization/history` `{old,new}` | `test_organizations.py` | yes |

### Performance

| ID | Requirement | Status | Existing / missing | Test | OpenAPI |
|---|---|---|---|---|---|
| P2-11 | Performance summary, indicators, scorecards, feedback, publish control, trends, export | DONE | Only `application_turnaround_days` and `document_completeness_percentage` (D44/D39). `POST /reviewer/organizations/{id}/performance/compute {period}` calculates both as **unpublished** entries using the documented definitions; staff publish explicitly. Partner `GET /partner/performance/summary` returns both keys with `state: published|unavailable` (unpublished is never revealed). Completeness stays `unavailable` until `required_documents.<pathway>` is defined (D6) | D6 required categories | `test_d39_d45.py::test_indicator_definitions_states_publish_and_isolation`, `test_profile_performance.py` | yes |

---

## P2 - Admin console

### Review workflow and allocation

| ID | Requirement | Status | Existing / missing | Test | OpenAPI |
|---|---|---|---|---|---|
| A-01a | Checklist and scoring storage | DONE (checklist); scoring not offered | D9: pass / fail / not_applicable / pending + note (fail needs a note). Numerical scores are rejected with 422; legacy columns unused. Migration 0024 converted yes/no to pass/fail | Final checklist items and approval responsibilities D9 | `test_review_workflow.py` | yes |
| A-01b | Exception record with approver and reason | DONE | `POST .../exceptions` (super admin = approver) | who may approve is a recommendation (D5) | `test_review_workflow.py` | yes |
| A-01c | Per-stage owner and notes | DONE | `PUT .../stage-owners/{stage}` | none | `test_review_workflow.py` | yes |
| A-01d | Reversal / reconsideration | DONE | `POST .../reopen` (super admin; rejected/withdrawn -> a stage; history written, partner notified) | recommendation D11 applied | `test_review_workflow.py` | yes |
| A-01e | Approved state or documented mapping | DECISION REQUIRED | Mapping documented (`pilot_onboarding` = approval point, recommended); D7 | `test_transitions.py` | yes |
| A-02a | Six allocation stages mapped to statuses | DONE (documented mapping; owner to confirm) | `submitted, eligibility_verification, capability_review, commercial_legal_review, pilot_onboarding, scale_up`, see `docs/frontend-backend-contract.md` | `test_transitions.py` | yes |
| A-02b | Clear reviewer assignment | DONE | `POST /reviewer/applications/{id}/assign` with `reviewer_id: null` | `test_gap_applications.py` | yes |

### Typed schemas

| ID | Endpoint | Status | Test | OpenAPI |
|---|---|---|---|---|
| A-03a | `/admin/overview` | DONE (`OverviewOut`) | `test_admin.py` | yes |
| A-03b | `/admin/reports/kpis` | DONE (`KpisOut`) | `test_admin.py` | yes |
| A-03c | `/admin/settings` | DONE (`values, allowed_keys, definitions`) | `test_ops.py` | yes |
| A-03d | `/admin/organizations/{id}` | DONE (`OrganizationDetailOut`) | `test_review_inherited.py` | yes |
| A-03e | `/auth/permissions` | DONE | `test_gap_phase_a.py` | yes |
| A-03f | `/reviewer/transitions` | DONE (`TransitionRule`) | `test_transitions.py` | yes |
| A-03g | `/admin/launch-readiness` | DONE | `test_ops.py` | yes |
| A-03h | Outbox and notification rows | DONE (`NotificationRow` with `is_strategic`) | `test_gap_phase_a.py` | yes |
| A-03i | Enquiry contact/company/details/documents | DONE (`EnquiryDetail`, `EnquiryDocumentOut`) | `test_review_inherited.py` | yes |

### Pagination

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| A-04 | `meta.total` + page count on every list; confirm key names | DONE | Keys are **`page`, `page_size`, `total`, `pages`** (not `total_count`). Fixed small lists unpaginated (listed in contract doc). Sweep: `test_gap_lists.py` |

### Strategic enquiries

| ID | Requirement | Status | Existing / missing | Test | OpenAPI |
|---|---|---|---|---|---|
| A-05a | Document permitted staff access | DONE | Super administrator only (`visible_types`); matrix in `docs/api/role-permission-matrix.md` | `test_strategic_confidentiality.py` | yes |
| A-05b | `discussion_type` field + filter | DONE | `GET /admin/enquiries?discussion_type=` | `test_review_inherited.py` | yes |
| A-05c | Assessment-outcome endpoint | DONE | Enum `approved, rejected, needs_clarification, pending` (D44), history kept, strategic only for super admin | none | `test_review_workflow.py` | yes |
| A-05d | Dedicated queue, owner, response target | DECISION REQUIRED | settings keys `route.owner.strategic`, `sla.strategic` exist; values = D3 | `test_section28.py` | yes |

### Enquiry detail

| ID | Requirement | Status | Existing / missing | Test | OpenAPI |
|---|---|---|---|---|---|
| A-06a | Assignment history | DONE | `GET /admin/enquiries/{id}/activity` | `test_gap_enquiries.py` | yes |
| A-06b | Separate note types | DONE | follow-up `kind`: `note, follow_up, communication` | `test_gap_enquiries.py` | yes |
| A-06c | Reply / external message endpoint | DECISION REQUIRED (deferred by D15) | Endpoint exists but answers 409 `FEATURE_DISABLED` unless `ENQUIRY_REPLY_ENABLED=true`; enable only with approved templates and a live provider | D15 | `test_review_workflow.py` | yes |

### Documents

| ID | Requirement | Status | Existing / missing | Test | OpenAPI |
|---|---|---|---|---|---|
| A-07a | Admin upload and replace | DONE | `POST /reviewer/organizations/{org}/documents`, `.../{doc}/versions` (reviewers: assigned organisations; quarantined; audited as staff) | none | `test_review_workflow.py` | yes |
| A-07b | Staff review history | DONE | `GET /admin/documents/{id}/history` (SA + reviewer assigned to the org) | `test_review_inherited.py` | yes |
| A-07c | "Replacement requested" status | DONE | review status `replacement_requested` (comment required; does not count as a satisfied required document) | none | `test_review_workflow.py` | yes |

### Communications

| ID | Requirement | Status | Existing / missing | Test | OpenAPI |
|---|---|---|---|---|---|
| A-08a | Template create/activate/version history | DONE | every save is versioned; `GET /admin/notification-templates/{key}/versions`, `POST .../versions/{n}/activate`. Keys are fixed by the built-in set, so "create" is the first PUT | none | `test_review_workflow.py` | yes |
| A-08b | Delivery status incl. bounces | DONE (code); BLOCKED (live) | `bounced` status; `POST /webhooks/email` with `X-Webhook-Secret` (404 until `EMAIL_WEBHOOK_SECRET` is set). Payload shape not verified against a live provider | Brevo account + webhook registration (external) | `test_cms_audit_batch.py` | yes |
| A-08c | SPF/DKIM/DMARC evidence | BLOCKED | No sending domain exists; cannot be inspected (external) | none | n/a |

### Partner management

| ID | Requirement | Status | Existing / missing | Test | OpenAPI |
|---|---|---|---|---|---|
| A-09a | Organisation category, contact person, email, phone | PARTIAL | `primary_contact` plus `company_type`/`primary_industry` on the profile | Fixed category list = owner | `test_gap_lists.py`, `test_profile_performance.py` | yes |
| A-09b | Staff profile editing | DECISION REQUIRED | D19 (recommended: no). Note: staff **user** profile edit is now done, see A-12b | none | no |
| A-09c | Before/after diffs on change requests | DONE | `before` on pending rows, `GET /admin/organizations/{id}/revisions` | `test_organizations.py`, `test_ops.py` | yes |

### Accounts

| ID | Requirement | Status | Existing / missing | Test | OpenAPI |
|---|---|---|---|---|---|
| A-10a | Account detail | DONE | `GET /admin/accounts/{id}` | `test_gap_accounts.py` | yes |
| A-10b | Admin-initiated password reset (secure token) | DONE | `POST /admin/accounts/{id}/password-reset` (token emailed, never returned, rate limited) | `test_gap_accounts.py` | yes |

### CMS

| ID | Requirement | Status | Existing / missing | Test | OpenAPI |
|---|---|---|---|---|---|
| A-11a | Homepage/hero, services, industries, navigation | DONE | content types `hero`, `service`, `industry`, `navigation` with structured `data`; navigation validated (https or site-relative links only) | Field schema of hero/service blocks is free JSON <= 20 KB | `test_cms_audit_batch.py` | yes |
| A-11b | Media library + image upload | DONE | `POST/GET /admin/media`, preview, publish/unpublish/archive, public `GET /media/{id}/file` only when published; png/jpg only | Public CDN/bucket D29 (files served through the API today) | `test_cms_audit_batch.py` | yes |
| A-11c | SEO title, description, canonical, OG | DONE | 8 SEO/image fields, https only | `test_phase1_seo_privacy.py` | yes |
| A-11d | Scheduled publishing + audit history | DONE | `POST/DELETE /admin/content/{id}/schedule`; versions; needs `scripts/run_maintenance.py` scheduled (external cron) | `test_review_inherited.py` | yes |
| A-11e | `updated_at`/`updated_by` | DONE | on `AdminContent` | none | `test_cms_audit_batch.py` | yes |
| A-11f | Rich-text body | DONE | `body_format` plain or markdown; raw HTML rejected (stored-XSS risk) | frontend must sanitise markdown rendering | `test_cms_audit_batch.py` | yes |

### Settings

| ID | Requirement | Status | Existing / missing | Test | OpenAPI |
|---|---|---|---|---|---|
| A-12a | Typed settings schema | DONE | `definitions[{key, group, value_kind, unit}]` | `test_ops.py` | yes |
| A-12b | Secrets API | DECISION REQUIRED | Secrets stay in host environment variables and are never returned by any endpoint. A write-only secrets API would need an encryption key and rotation design | D40 | none | no |
| A-12c | Security-policy write | DECISION REQUIRED | `GET /admin/security-policy` read-only: lifetimes and password rules are env values; runtime write needs D36 | none | yes |

### Audit

| ID | Requirement | Status | Existing / missing | Test | OpenAPI |
|---|---|---|---|---|---|
| A-13a | Export | DONE | `GET /admin/audit.csv` (formula-safe, 10,000 cap, audited) | `test_review_inherited.py` | yes |
| A-13b | Get by id | DONE | `GET /admin/audit/{id}` | `test_review_inherited.py` | yes |
| A-13c | Text search | DONE | `q` | `test_gap_phase_a.py` | yes |
| A-13d | Event-type catalogue | DONE | `GET /admin/audit/actions` | `test_review_inherited.py` | yes |
| A-13e | IP/device, outcome, before/after values | DONE | `ip_address`, `user_agent`, `outcome` on audit rows and CSV (super admin only); `log_activity(changes=...)` stores before/after under `meta.changes` for non-personal fields | Retention of IP/UA = D36/D4; not every caller passes `changes` yet | `test_cms_audit_batch.py` | yes |

### Reports

| ID | Requirement | Status | Existing / missing | Test | OpenAPI |
|---|---|---|---|---|---|
| A-14a | Date filters | DONE | `created_from/to` on kpis and reports | `test_admin.py` | yes |
| A-14b | Assignee and category filters | DONE | `assignee_id`, `category` on `/admin/reports/kpis` | none | `test_final_decisions.py::test_kpi_filters_by_assignee_category_and_dates` | yes |
| A-14c | Turnaround and onboarding-duration metrics | DONE (turnaround); PARTIAL (onboarding duration) | `application_decision_turnaround_hours_avg` verified with seeded 10 h and 30 h applications; onboarding duration is computed but has no dedicated value test | Onboarding duration test | `test_final_decisions.py::test_application_turnaround_and_onboarding_duration_metrics` | yes |
| A-14d | PDF/Excel export | DECISION REQUIRED | CSV exports exist and open in Excel. Native .xlsx/PDF needs a new dependency (e.g. openpyxl, reportlab); adding dependencies needs your approval | D41 | none | no |
| A-14e | Totals not page-limited | DONE | KPIs computed in SQL; CSV capped at 10,000 rows by design | `test_admin.py` | yes |

---

## P3 - Quality

| ID | Requirement | Status | Existing / missing | Test | OpenAPI |
|---|---|---|---|---|---|
| Q-01 | Server `q`, sort, date filters on applications, organisations, users, notifications, content, audit | DONE | | `test_gap_lists.py`, `test_gap_applications.py`, `test_gap_phase_a.py` | yes |
| Q-02 | `updated_at` and actor names | DONE | applications, enquiries, history, notes, audit | `test_gap_phase_a.py` | yes |
| Q-03 | Applicant name/email/phone on application rows | DONE | `primary_contact` | `test_gap_applications.py` | yes |
| Q-04 | Application-per-reviewer workload endpoint | DONE (this session) | `GET /reviewer/workload` (counts open applications by reviewer and status; reviewers see only their own row; super admin sees all incl. unassigned) | `test_requirements_batch.py::test_application_workload_per_reviewer` | yes |
| Q-05a | Admin user get-by-id | DONE (this session) | `GET /admin/users/{id}` | `test_requirements_batch.py` | yes |
| Q-05b | User search, pagination | DONE | `GET /admin/users?q=&role=&status=&sort=` | `test_gap_lists.py` | yes |
| Q-05c | Profile update | DONE (this session) | `PATCH /admin/users/{id}` `{full_name}` only; role and status keep their own endpoints; audited | `test_requirements_batch.py` | yes |
| Q-05d | Per-user activity | DONE (this session) | `GET /admin/users/{id}/activity` (paginated), `recent_activity` on account detail | `test_requirements_batch.py` | yes |
| Q-05e | Typed status enum | DONE | `StaffOut.status` is `UserStatus` | none | `test_gap_lists.py` | yes |
| Q-06 | `partner_reviewer` and `content_administrator` implemented | DONE | `StaffRole` has four roles, guards in matrix | `test_gap_phase_a.py` | yes |
| Q-07 | 409 on self-change and last Super Administrator | DONE | `SELF_CHANGE`, `LAST_SUPER_ADMIN` | `test_gap_lists.py`, `test_admin.py` | yes |
| Q-08 | CSV: permissions, content visibility for non-super, strategic exclusion, 10,000-row cap | DONE | | `test_strategic_confidentiality.py`, `test_review_inherited.py` (cap test per `backend-gap-test-report.md`) | yes |
| Q-09 | HttpOnly-cookie sessions: assess, document residual risk | DECISION REQUIRED | Not changed. Refresh tokens are returned in the body; XSS can read a token kept in `sessionStorage`. Rotation + reuse detection limit replay but not live theft. Recommendation (not applied): same-site custom domain, `HttpOnly; Secure; SameSite=Lax` refresh cookie, CSRF protection on `/auth/refresh`, access token in memory (D1) | `test_mfa.py` (rotation) | n/a |

---

## Section 8 business decisions

Full register with affected code and recommended defaults: `docs/business-decisions-required.md` (D1-D29 earlier, D30-D39 added 2026-11-11). Mapping of your eleven questions: thresholds D6; retention D4; partner roles D22; performance indicators D39; strategic queue owner/target D3; providers D35; calendar scope D16; privacy SLA D34; exact CORS origins D32; malware scanner D33; conflicts with the PRD D30.

## Test evidence

See the "Verification (2026-11-11 requirements batch)" section appended to `docs/backend-gap-test-report.md`.


---

## Security verification evidence (local tests only; none is live verification)

| Control | Evidence |
|---|---|
| Strategic data never in partner payloads or non-super staff responses | `test_strategic_confidentiality.py` (3 tests), `test_review_workflow.py::test_assessment_outcome_and_reply_respect_strategic_visibility`, `test_final_decisions.py` (BDM assigned-org scope excludes strategic enquiries by construction) |
| BDM read-only, assigned organisations only | `test_final_decisions.py::test_bdm_read_only_access_limited_to_assigned_organisations` (10 forbidden writes/reads, cross-org 404) |
| Cross-organisation isolation | `test_security_p2.py`, `test_collaboration.py`, `test_team_prefs_onboarding.py`, `test_profile_performance.py` |
| Last owner / self-elevation | `test_team_prefs_onboarding.py::test_team_lifecycle_roles_and_protections` |
| Sessions revoked on password change and deactivation | `test_auth.py` (change password), `test_team_prefs_onboarding.py` (role change, deactivate), `test_gap_accounts.py` (suspend) |
| Private documents need authorisation; never `clean` | `test_partner_documents.py`, `test_security_p2.py`, `test_requirements_batch.py::test_documents_report_not_scanned_never_clean` |
| Audited sensitive changes | audit rows asserted in `test_cms_audit_batch.py`, `test_review_workflow.py`, `test_team_prefs_onboarding.py` |
| CSV permissions and strategic exclusion | `test_strategic_confidentiality.py`, `test_review_inherited.py` |
| Secrets not in responses | `GET /admin/settings` and security policy expose no secret values (`test_ops.py`); the webhook secret is `SecretStr`; not scanned in logs beyond the existing redaction filter |
| Verified privacy identity | `test_phase1_seo_privacy.py`, `test_phase2_privacy.py` |

## Owner decisions applied 2026-11-11 (final round)
D3 targets configurable (`sla.<queue>`, owners via settings; no names invented). D4 deletion blocked until policy. D6 untouched (no thresholds applied). D9 pass/fail/N-A, no scores. D10 staff-configured tasks. D33 quarantine-only (scan_status `not_scanned`). D34 configurable SLA. D42 mandatory `account`+`application`. D45 BDM read-only assigned orgs (assignment = originating partner enquiry assigned to the BDM). D15 reply gated off. D7 label "Approved - pilot".


---

## Environment and traceability (2026-11-11, final pass)

Repository: `C:\Users\ABC\Desktop\coralswift-backend` (primary checkout, branch `main`, HEAD `6ad57a7`, work uncommitted). The earlier worktree `.claude/worktrees/coralswift-backend-requirements-26403a` held the same changes; they were transferred to the primary checkout with `git apply` plus file copies and verified identical (ignoring line endings). The primary checkout's own two modified files (`docs/integration/FRONTEND_PUBLIC_WEBSITE_INTEGRATION_STATUS.md`, `tests/unit/test_config.py`) were not touched.

| Environment | State | Evidence |
|---|---|---|
| Local disposable DB | revision `0025`, `alembic check` clean | `scripts/alembic_test_db.py heads/check` |
| **Remote development Supabase** (project ref `zibfzlwzaecapfrgjret`, same target as `.env` and `.env.render`) | **revision `0025`** (was `0015`); 13 new tables, 11 new columns present; existing rows intact (2 organisations, 5 users); `alembic check` clean; in-process API smoke test against it: `/health/ready` 200, login unknown user 401 `INVALID_CREDENTIALS`, unauthenticated partner route 401 | `alembic current`, information_schema queries, smoke script |
| **Render live service** `https://coralswift-backend.onrender.com` | **NOT deployed with this work.** Live OpenAPI has 162 paths / 291 schemas (old version); `/partner/projects` absent. Health 200. Deploying needs a commit and push (not authorised) and Render access | `curl /openapi.json` |

| Feature group | Tables / migration | Verified at |
|---|---|---|
| Projects, inbox, discussions/meetings/follow-ups | `partner_projects`, `project_*`, `partner_messages*`, `collab_*` / 0016 | local tests; remote schema present; not live |
| Team, notification preferences, onboarding | `partner_notification_preferences`, `onboarding_*` / 0017 | local tests; remote schema |
| Review checklist, exceptions, stage owners, assessments, template versions | `review_checklist_items`, `application_exceptions`, `application_stage_owners`, `enquiry_assessments`, `notification_template_versions` / 0018, 0024 | local tests; remote schema |
| Audit origin/outcome | `activities.ip_address,user_agent,outcome` / 0019 | local tests; remote schema |
| CMS blocks, media | `media_assets`, `content_items.body_format,data,updated_by` / 0020 | local tests; remote schema |
| Extended profile | `partner_organizations` columns / 0021 | local tests; remote schema |
| Performance | `performance_entries`, `performance_feedback` / 0022 | local tests; remote schema |
| Bounced delivery status | check constraint / 0023 | local tests |
| Information-request due date | `application_messages.due_date` / 0024 | local tests |
| BDM assignment, D44 constraints | `organization_bdm_assignments`; NOT VALID checks / 0025 | local tests; remote schema |

Decisions applied in the final pass: D3 defaults (24 h first response, 48 h escalation constant and `sla_escalation.<queue>` setting; the 48 h value is exposed as a default only, the escalation job still fires at first-response breach: PARTIAL), D10 editable template (`/admin/onboarding-template`, empty until staff define it), D19 (change requests only for existing values), D34 (30 days default, `privacy.completion_days` overrides), D39, D44, D45.
