# Requirement Audit - PRD Phases 1-3 (2026-11-10)

Sources: PRD v2.0 s.8-14, 15 (B,C,E,H), 16-19, 21, 28; Frontend Backend Requests 2026-11-10; the owner's Phase 1-3 scope list. Local work only: no commit, push, deploy, backup or remote database operation. Last full local run: see `../backend-gap-test-report.md`.

`IMPLEMENTED_BUT_NOT_FULLY_VERIFIED` = code exists and its tests pass, but I did not independently review the logic (mostly work left in the tree by the earlier agent).

## Phase 1 - Public Website

| ID | Requirement | Status | Implementation / endpoints | Tests | Remaining | Dependency |
|---|---|---|---|---|---|---|
| P1-01 | Public pages: Home, About, Services, Partnerships, Project Opportunities, Strategic Discussions, Insights, Contact (delivery) | IMPLEMENTED_AND_TESTED | `GET /content`, `/content/{slug}` (types page/article/faq/resource); `content/router.py` | test_content_engagement | Page-specific structured sections: see P1-02 | - |
| P1-02 | Structured homepage sections: hero, banners, service/industry cards, navigation menus | BUSINESS_DECISION_BLOCKED | Not modelled; pages are a title, summary and plain body | - | Define the content model | D23 |
| P1-03 | Insights/articles with search, tags, category, related items | IMPLEMENTED_AND_TESTED | `GET /content?q&tag&category`, detail `related` | test_content_engagement | - | - |
| P1-04 | FAQ and downloadable resources with version label | IMPLEMENTED_AND_TESTED | content types `faq`, `resource`; `GET /content/{slug}/download` | test_content_attachment_download | - | - |
| P1-05 | Only published, approved content is public; drafts/unpublished hidden | IMPLEMENTED_AND_TESTED | `content/service.list_public`, `get_public` | test_content_workflow_and_public_visibility, test_phase1_seo_privacy | - | - |
| P1-06 | Scheduled publication behaviour | IMPLEMENTED_AND_TESTED | `POST/DELETE /admin/content/{id}/schedule`, maintenance job; migration 0012 (earlier agent) - independently reviewed 2026-11-10 | test_scheduled_publication_negative_cases, test_scheduled_content_contract_and_maintenance_publish | - | - |
| P1-07 | SEO metadata: title, description, canonical, Open Graph, cover image (https only) | IMPLEMENTED_AND_TESTED | 8 nullable fields on content, public and admin | test_phase1_seo_privacy (3) | - | - |
| P1-08 | XML sitemap data | IMPLEMENTED_AND_TESTED | `GET /content/sitemap` | test_content_engagement | robots.txt and HTML head are frontend | - |
| P1-09 | Media library (upload/manage site images) | EXTERNAL_CONFIGURATION_BLOCKED | Cover images are referenced by https URL; no upload store for public media | - | Needs a public media bucket/CDN choice | D23 + hosting |
| P1-10 | Analytics foundations | NOT_APPLICABLE_WITH_JUSTIFICATION | Page and CTA analytics are client-side events; the backend records enquiry/application/meeting events in the database | - | - | - |
| P1-11 | Privacy, terms, cookie pages through the approved-content workflow | IMPLEMENTED_AND_TESTED | page content + approval + claims gate | test_content_workflow_and_public_visibility | - | - |
| P1-12 | Approved legal text and privacy notice version | BUSINESS_DECISION_BLOCKED | `PRIVACY_NOTICE_VERSION` stores the consented version; text itself not supplied | - | Owner/legal approve text | D4 |
| P1-13 | Content claims register with publication gate | IMPLEMENTED_AND_TESTED | `/admin/content-claims`, publish gate | test_claims_gate_publication | - | - |
| P1-14 | General contact enquiry | IMPLEMENTED_AND_TESTED | `POST /enquiries/contact` | test_contact (5) | - | - |
| P1-15 | Project enquiry (IT / Non-IT, scope, volume, geography) | IMPLEMENTED_AND_TESTED | `POST /enquiries/project` | test_project_partner_strategic | - | - |
| P1-16 | Partner application incl. direct-project and vendor/subcontracting pathways | IMPLEMENTED_AND_TESTED | `POST /enquiries/partner` with `preferred_engagement_pathway` | test_partner_valid_application | - | - |
| P1-17 | Strategic merger/integration enquiry, confidential | IMPLEMENTED_AND_TESTED | `POST /enquiries/strategic`; staff access super admin only | test_strategic_*, test_strategic_confidentiality | - | - |
| P1-18 | Meeting request (staff-attested confirmation) | IMPLEMENTED_AND_TESTED | `POST /meetings`; DB check blocks confirm without calendar check | test_meeting_request_and_manual_confirmation | - | - |
| P1-19 | Real calendar availability check / scheduling integration | OUT_OF_SCOPE_PHASE_4_OR_LATER | Unapproved calendar integration | - | - | D16 |
| P1-20 | Server validation: required fields, email, phone (E.164), consent, unknown fields rejected | IMPLEMENTED_AND_TESTED | Pydantic schemas, `extra=forbid` | test_validation_errors, test_missing_consent_and_unknown_fields_rejected | - | - |
| P1-21 | Unique reference numbers | IMPLEMENTED_AND_TESTED | DB sequence `enquiry_reference_seq` | test_references_are_unique, test_reference_numbers_unique_under_concurrency | - | - |
| P1-22 | Classification and routing to queue, owner, backup owner, SLA due date, lead source | IMPLEMENTED_AND_TESTED | `enquiries/routing.py`, settings `route.*`, `sla.*` | test_routing_sla_backup_owner_and_ack_promise | - | - |
| P1-23 | Queue owner / SLA / escalation values | BUSINESS_DECISION_BLOCKED | Mechanism ready, values empty | - | Owner supplies values | D3 |
| P1-24 | Acknowledgement and internal notification (outbox, retry, dedupe) | IMPLEMENTED_AND_TESTED | `notifications/` | test_notifications (6) | - | - |
| P1-25 | Real email delivery and domain authentication | EXTERNAL_CONFIGURATION_BLOCKED | Brevo adapter written; key valid; sender is a Gmail address | unit/test_adapters (mock) | Verified sender domain, SPF/DKIM/DMARC, delivery evidence | Domain |
| P1-26 | Optional attachments: type, size, content checks, private storage, quarantine | IMPLEMENTED_AND_TESTED | `POST /documents/upload`, limits at `/admin/security-policy` | test_documents_status_security | - | - |
| P1-27 | Malware scanning | NOT_APPLICABLE_WITH_JUSTIFICATION | Owner formally accepted quarantine-only uploads (2026-11-10); nothing claims a scan | - | - | Owner decision recorded |
| P1-28 | Rate limiting, duplicate-submission handling and idempotency | IMPLEMENTED_AND_TESTED | `core/protection.py`, `common/idempotency.py` | test_rate_limit, test_idempotency (10) | - | - |
| P1-29 | Bot protection: server-side Turnstile validation, fails closed, required in staging/production | IMPLEMENTED_AND_TESTED | `integrations/botcheck.py`, explicit non-wildcard `TURNSTILE_ALLOWED_HOSTNAMES` required in hardened environments | unit/test_botcheck, public readiness tests (mock Cloudflare, hostname mismatch, API 403 cases) | Live real-token verification remains external (P1-29b) | - |
| P1-29b | Live Turnstile verification with a real token | EXTERNAL_CONFIGURATION_BLOCKED | Secret accepted by Cloudflare; a valid real token never observed | - | Add hostnames to the widget and test from the frontend | Cloudflare |
| P1-30 | Failure handling: no silent loss, admin visibility and retry of failed emails | IMPLEMENTED_AND_TESTED | `/admin/notifications`, retry; transactional submit | test_notification_failure_visibility_and_retry, test_db_failure_rolls_back_everything_and_sends_no_email | - | - |
| P1-31 | Submission status lookup by token | IMPLEMENTED_AND_TESTED | `GET /enquiries/{ref}/status` | test_status_with_token_returns_minimal_fields | - | - |
| P1-32 | Privacy requests with email-confirmation identity check | IMPLEMENTED_AND_TESTED | `POST /privacy/requests`, `/verify` | test_phase1_seo_privacy (2) | - | - |
| P1-33 | Data minimisation (no sensitive health/banking data requested) | IMPLEMENTED_AND_TESTED | forbid-extra schemas | test_missing_consent_and_unknown_fields_rejected | - | - |
| P1-34 | Newsletter opt-in | IMPLEMENTED_AND_TESTED | `/newsletter/subscribe`, `/unsubscribe` | test_newsletter_and_privacy_requests | - | - |
| P1-35 | Public contact details (confirmed values only) and launch gate | IMPLEMENTED_AND_TESTED | `GET /site/contact`, `/admin/launch-readiness` | test_launch_readiness_and_public_contact | Values are D3 | - |
| P1-36 | Project categories (illustrative) and partner criteria (proposed) catalogue | IMPLEMENTED_AND_TESTED | `/catalog/*` | test_catalog_is_illustrative_and_criteria_proposed | - | - |
| P1-37 | CORS for approved origins (code, preflight, custom headers) | IMPLEMENTED_AND_TESTED | `main.py` | test_cors_allowed_and_blocked_origin | - | - |
| P1-38 | Approved CORS origin values, HTTPS, CSP on the frontend host | EXTERNAL_CONFIGURATION_BLOCKED | `CORS_ALLOWED_ORIGINS` environment value | - | Set values on the host | Hosting |

## Phase 2 - Partner Portal

| ID | Requirement | Status | Implementation / endpoints | Tests | Remaining | Dependency |
|---|---|---|---|---|---|---|
| P2-01 | Partner invitation and activation | IMPLEMENTED_AND_TESTED | `/reviewer/invitations`, `/auth/invitations/accept` | test_auth, test_gap_accounts | - | - |
| P2-02 | Self-service partner registration | BUSINESS_DECISION_BLOCKED | Invitation-only by design | - | Decide invitation vs self-registration | Decision register #7 |
| P2-03 | Login, refresh rotation with replay detection, logout, lockout | IMPLEMENTED_AND_TESTED | `auth/service.py` | test_auth (16) | - | - |
| P2-04 | Password reset and change-password | IMPLEMENTED_AND_TESTED | `/auth/password-reset/*`, `/auth/change-password` | test_gap_phase_a | - | - |
| P2-05 | Distinct token errors and deactivated-login error | IMPLEMENTED_AND_TESTED | `TOKEN_*`, `ACCOUNT_DEACTIVATED` | test_gap_phase_a | - | - |
| P2-06 | Detailed login errors for not-activated / locked accounts | BUSINESS_DECISION_BLOCKED | Generic 401 to avoid revealing accounts | - | Decision | D2 |
| P2-07 | MFA (TOTP, recovery codes, replay protection); staff mandatory in production | IMPLEMENTED_AND_TESTED | `auth/mfa.py` | test_mfa (7), test_phase2_account | - | - |
| P2-08 | MFA disable for partners (password + code); no silent re-enrolment | IMPLEMENTED_AND_TESTED | `POST /auth/mfa/disable` | test_phase2_account | - | - |
| P2-09 | Approved partner MFA policy | BUSINESS_DECISION_BLOCKED | Implemented behaviour: optional, enforced once enabled | - | Owner confirms required/optional/off | Owner |
| P2-10 | Sessions: list, expiry, revoke one, sign out others | IMPLEMENTED_AND_TESTED | `/auth/sessions` | test_phase2_account, test_auth | - | - |
| P2-11 | Cookie (HttpOnly) session persistence | BUSINESS_DECISION_BLOCKED | Tokens in response body | - | Decision | D1 |
| P2-12 | Account response: type, status, role, phone, MFA flags, last login; self-edit of name/phone | IMPLEMENTED_AND_TESTED | `GET/PATCH /auth/me` | test_phase2_account | - | - |
| P2-13 | Partner roles (owner/member) and strict organisation scoping | IMPLEMENTED_AND_TESTED | memberships; org id from token only | test_security_p2, test_organizations | - | - |
| P2-14 | Role-specific partner permissions beyond owner/member | BUSINESS_DECISION_BLOCKED | Two roles | - | Decision | D22 |
| P2-15 | Company profile (PRD s.12 fields) with completion indicator | IMPLEMENTED_AND_TESTED | `/partner/organization`, `/completion` | test_profile_update_completion_and_history | - | - |
| P2-16 | Extra profile fields (trading name, industry, offices, ...) | BUSINESS_DECISION_BLOCKED | Not in the PRD field list | - | Decision | D20 |
| P2-17 | Editable-field metadata and null-clearing | IMPLEMENTED_AND_TESTED | `GET /partner/organization/editable-fields` (earlier agent) - independently reviewed 2026-11-10 | test_field_metadata_templates_and_typed_details_have_stable_contracts | - | - |
| P2-18 | Profile change requests with staff decision | IMPLEMENTED_AND_TESTED | `/partner/organization/change-requests`, `/admin/profile-change-requests` | test_profile_change_request_flow_and_partner_extras, test_phase3_org_history | - | - |
| P2-19 | Revision history with before/after values | IMPLEMENTED_AND_TESTED | `/partner/organization/history`, `/admin/organizations/{id}/revisions` | test_phase3_org_history | - | - |
| P2-20 | Application draft, readiness checklist, submit, withdraw, resubmit | IMPLEMENTED_AND_TESTED | `/partner/applications/*` | test_applications (5), test_audit_e2e | - | - |
| P2-21 | Partner-visible status, label, history and timestamps | IMPLEMENTED_AND_TESTED | `ApplicationOut`, `/history` | test_submit_snapshot_history_and_notifications | - | - |
| P2-22 | Information requests, reviewer messages and partner responses | IMPLEMENTED_AND_TESTED | `/partner/applications/{id}/messages` | test_information_request_response_resubmission | - | - |
| P2-23 | Partner-visible eligibility outcome and decision reason | BUSINESS_DECISION_BLOCKED | Reviewer-only today | - | Decide what partners may see | D27 |
| P2-24 | Partner-visible onboarding information and tasks | BUSINESS_DECISION_BLOCKED | Status `pilot_onboarding` only | - | Define onboarding | D10 |
| P2-25 | Private document upload, versions, replace, audited download, review status | IMPLEMENTED_AND_TESTED | `/partner/documents/*` | test_partner_documents (7) | - | - |
| P2-26 | Required-document rules (seven PRD categories) | IMPLEMENTED_AND_TESTED | `/readiness` | test_submit_requires_complete_profile_and_documents | - | - |
| P2-27 | Mandatory documents per pathway | BUSINESS_DECISION_BLOCKED | One list for all pathways | - | Decision | D6 |
| P2-28 | Additional-document requests: deadline, status, link to upload | IMPLEMENTED_AND_TESTED | `/reviewer/applications/{id}/document-requests`, `/partner/document-requests`, upload `request_id` | test_phase2_document_requests (2) | - | - |
| P2-29 | Retention metadata and secure deletion mechanism | IMPLEMENTED_AND_TESTED | retention date, purge job | test_retention_purge_and_expiry_reminders | - | - |
| P2-30 | Retention periods and account-closure workflow | BUSINESS_DECISION_BLOCKED | Inert until set | - | Decision | D4 |
| P2-31 | Document expiry tracking and reminders | IMPLEMENTED_AND_TESTED | maintenance job | test_retention_purge_and_expiry_reminders | - | - |
| P2-32 | Partner notifications with read/unread, unread count, title, category, reference | IMPLEMENTED_AND_TESTED | `/partner/notifications*` | test_gap_lists, test_phase3_org_history | - | - |
| P2-33 | Partner privacy requests (identity from session) | IMPLEMENTED_AND_TESTED | `/partner/privacy-requests` | test_phase2_privacy | - | - |
| P2-34 | Partner enquiry history | IMPLEMENTED_AND_TESTED | `GET /partner/enquiries` | test_profile_change_request_flow_and_partner_extras | - | - |
| P2-35 | Cross-organisation isolation on every partner endpoint; no staff-only data in partner payloads | IMPLEMENTED_AND_TESTED | org from token; 404 for foreign ids | test_security_p2 (IDOR matrix, anonymous sweep), test_phase2_* | - | - |
| P2-36 | Security audit of account events without secrets | IMPLEMENTED_AND_TESTED | `activities` append-only | test_audit_table_is_append_only, test_secrets_never_in_logs | - | - |
| P2-37 | Partner projects, team platform, performance scorecards, discussions, meetings, preferences | OUT_OF_SCOPE_PHASE_4_OR_LATER | PRD Phase 4+ | - | - | - |

## Phase 3 - Admin Platform

| ID | Requirement | Status | Implementation / endpoints | Tests | Remaining | Dependency |
|---|---|---|---|---|---|---|
| P3-01 | Four roles, backend-enforced permissions, permission matrix API | IMPLEMENTED_AND_TESTED | `require_staff`, `GET /auth/permissions` | test_permission_matrix_matches_real_enforcement | - | - |
| P3-02 | Self-modification and last-super-admin safeguards | IMPLEMENTED_AND_TESTED | `SELF_CHANGE`, `LAST_SUPER_ADMIN` | test_self_and_last_super_admin_protections_hold | - | - |
| P3-03 | Staff user list/detail/invite/role/activate and account administration | IMPLEMENTED_AND_TESTED | `/admin/users`, `/admin/accounts*` | test_gap_accounts, test_gap_lists | - | - |
| P3-04 | Assignee lookup for every staff role | IMPLEMENTED_AND_TESTED | `/admin/assignees` | test_assignee_picker_is_open_to_staff_and_exposes_names_only | - | - |
| P3-05 | Dashboard overview (typed) and KPIs (typed, aggregate in SQL) | IMPLEMENTED_AND_TESTED | `/admin/overview`, `/admin/reports/kpis` (typed by earlier agent) - independently reviewed 2026-11-10 | test_kpis, test_typed_aggregate_reports_and_role_scopes, test_review_inherited | - | - |
| P3-06 | Pending / approved application counts | BUSINESS_DECISION_BLOCKED | No approved status | - | Decision | D7 |
| P3-07 | Recent decisions with timestamps; documents awaiting verification | IMPLEMENTED_AND_TESTED | `decided_at`; `/admin/documents?review_status=pending` | test_gap_applications, test_gap_reference | - | - |
| P3-08 | Application list: search, filters, sort, pagination, contact, names | IMPLEMENTED_AND_TESTED | `/reviewer/applications` | test_gap_applications | - | - |
| P3-09 | Review workflow with valid transitions and mandatory reasons | IMPLEMENTED_AND_TESTED | `/transition`, `/reviewer/transitions` | test_transitions (9), test_reviewer (6) | - | - |
| P3-10 | Six allocation stages (documented 1:1 status mapping with timestamps, owners, notes) | IMPLEMENTED_AND_TESTED | status history; mapping in contract | test_transitions, test_reviewer | - | - |
| P3-11 | Human-only eligibility records (no auto decision) | IMPLEMENTED_AND_TESTED | `/eligibility-verifications` | test_partner_thresholds_never_decide | - | - |
| P3-12 | Checklist/scoring, recommendation step | BUSINESS_DECISION_BLOCKED | PRD forbids automated final decisions; items undefined | - | Decision | D9 |
| P3-13 | Reconsideration/reversal; eligibility exceptions; thresholds per pathway | BUSINESS_DECISION_BLOCKED | Terminal states; no policy | - | Decisions | D11, D5, D6 |
| P3-14 | Reviewer assignment, reassignment, clearing, notification | IMPLEMENTED_AND_TESTED | `/assign` | test_gap_applications, test_reviewer_assignment_sends_notification | - | - |
| P3-15 | Reviewer notes and activity history with actor names | IMPLEMENTED_AND_TESTED | `/notes`, `/history` | test_gap_applications, test_internal_notes_never_reach_partners | - | - |
| P3-16 | Enquiry list/detail with filters, IT/Non-IT, sort, names, assignment history | IMPLEMENTED_AND_TESTED | `/admin/enquiries*` | test_gap_enquiries (4) | - | - |
| P3-17 | Follow-ups: create/update/reschedule/reassign/cancel, kinds, global list and counts | IMPLEMENTED_AND_TESTED | `/admin/follow-ups` | test_gap_enquiries | - | - |
| P3-18 | Internal notes vs communication vs follow-up | IMPLEMENTED_AND_TESTED | follow-up `kind` | test_followup_kinds_owner_update_and_cancel | - | - |
| P3-19 | Reply / external message to requesters from the console | BUSINESS_DECISION_BLOCKED | Contact logged only | - | Decision | D15 |
| P3-20 | Enquiry status workflow and extra statuses | BUSINESS_DECISION_BLOCKED | Any status settable | - | Decision | D8 |
| P3-21 | Strategic confidentiality across list, detail, search, CSV, documents, audit, outbox, feed, KPIs | IMPLEMENTED_AND_TESTED | `visible_types`, query-level | test_strategic_confidentiality (3), test_phase3_feed, test_phase3_org_history | - | - |
| P3-22 | Strategic discussion-type classification and filter | IMPLEMENTED_AND_TESTED | `discussion_type` filter (earlier agent) - independently reviewed 2026-11-10 | test_discussion_type_filter_is_validated_and_confidential | - | - |
| P3-23 | Strategic queue/owner/response-target mechanism | IMPLEMENTED_AND_TESTED | settings keys for `strategic` | test_section28 | - | - |
| P3-24 | Strategic assessment outcome workflow; BDM access to strategic | BUSINESS_DECISION_BLOCKED | BDM none by default | - | Decisions | D8, D12 |
| P3-25 | Organisation list/detail with filters, sort, contact; typed detail | IMPLEMENTED_AND_TESTED | `/admin/organizations*` - independently reviewed 2026-11-10 | test_field_metadata_templates_and_typed_details_have_stable_contracts (financial fields null for BDM) | - | - |
| P3-26 | Organisation history: revisions and activity (strategic events excluded) | IMPLEMENTED_AND_TESTED | `/admin/organizations/{id}/revisions`, `/activity` | test_phase3_org_history (2) | - | - |
| P3-27 | Staff edit of a partner profile | BUSINESS_DECISION_BLOCKED | Change-request flow instead | - | Decision | D19 |
| P3-28 | Change-request review with before/after values | IMPLEMENTED_AND_TESTED | `before` on pending requests; revisions after approval | test_staff_see_revisions_activity_and_change_request_before_values | - | - |
| P3-29 | Partner accounts: list, detail, invitation resend/revoke, suspend/reactivate, reset | IMPLEMENTED_AND_TESTED | `/admin/accounts*` | test_gap_accounts (6) | - | - |
| P3-30 | Global document queue with role-scoped visibility | IMPLEMENTED_AND_TESTED | `GET /admin/documents` | test_document_queue_scope_filters_and_no_storage_details | - | - |
| P3-31 | Document review history, enquiry attachment list, document-level notes | IMPLEMENTED_AND_TESTED | `/admin/documents/{id}/history`, `/admin/enquiries/{id}/documents` (earlier agent); `review_comment` - independently reviewed 2026-11-10 | test_document_history_is_scoped_to_assigned_organisations, test_strategic_confidentiality | - | - |
| P3-32 | Additional-document request management for staff | IMPLEMENTED_AND_TESTED | `/reviewer/applications/{id}/document-requests`, cancel | test_phase2_document_requests | - | - |
| P3-33 | Admin upload/replace of partner documents | BUSINESS_DECISION_BLOCKED | Partners own documents | - | Decision | D17 |
| P3-34 | Reviewer assignment workload report | IMPLEMENTED_AND_TESTED | `GET /admin/workload` (earlier agent) - independently reviewed 2026-11-10 | test_workload_counts_match_the_data_and_hide_strategic_from_bdm | - | - |
| P3-35 | Staff in-app notification feed with read/archive | IMPLEMENTED_AND_TESTED | `/admin/feed*` | test_phase3_feed (2) | - | - |
| P3-36 | Typed outbox rows with filters and strategic flag | IMPLEMENTED_AND_TESTED | `GET /admin/notifications` | test_outbox_rows_are_typed_filterable_and_flag_strategic | - | - |
| P3-37 | Notification templates: override, validate, preview, placeholder list | IMPLEMENTED_AND_TESTED | `/admin/notification-templates*` - independently reviewed 2026-11-10 | test_template_override_is_used_and_validated, test_review_inherited | - | - |
| P3-38 | Template version history | NOT_APPLICABLE_WITH_JUSTIFICATION | PRD s.14 lists templates and settings, no version history | - | - | - |
| P3-39 | Communication history per record | IMPLEMENTED_AND_TESTED | follow-ups `communication` + activity feed | test_gap_enquiries | - | - |
| P3-40 | Delivery/open receipts | EXTERNAL_CONFIGURATION_BLOCKED | Outbox status only | - | Brevo webhooks + verified domain | Domain |
| P3-41 | CMS: draft, review, approve (super admin), publish, unpublish, versions, ownership, audit | IMPLEMENTED_AND_TESTED | `/admin/content*` | test_content_workflow_and_public_visibility (+ sort/date: test_content_list_sort_date_and_csv_cap) | - | - |
| P3-42 | CMS SEO fields and cover image | IMPLEMENTED_AND_TESTED | see P1-07 | test_phase1_seo_privacy | - | - |
| P3-43 | CMS media library; homepage/navigation/rich-text structures | EXTERNAL_CONFIGURATION_BLOCKED | see P1-02, P1-09 | - | Content model + media hosting | D23 |
| P3-44 | Content approver beyond super administrator | BUSINESS_DECISION_BLOCKED | Super administrator only | - | Decision | D24 |
| P3-45 | CSV exports (enquiries, applications, newsletter) with role limits, formula-safe, row cap | IMPLEMENTED_AND_TESTED | `/admin/reports/*.csv` | test_csv_export_is_safe_and_audited, CSV cap test | - | - |
| P3-46 | Reports: follow-up, document-review, communication | IMPLEMENTED_AND_TESTED | `/admin/reports/*` (earlier agent) - independently reviewed 2026-11-10 | test_reports_exclude_strategic_follow_ups_for_bdm_and_deny_other_roles | - | - |
| P3-47 | Audit: list, search, sort, actor names, strategic flag | IMPLEMENTED_AND_TESTED | `GET /admin/audit` | test_audit_rows_have_actor_names_strategic_flag_search_and_sort | - | - |
| P3-48 | Audit detail, event catalogue and export | IMPLEMENTED_AND_TESTED | `/admin/audit/{id}`, `/audit/actions`, `/audit.csv` (earlier agent) - independently reviewed 2026-11-10 | test_audit_detail_actions_and_csv_are_super_admin_only_and_safe | - | - |
| P3-49 | Audit IP/device and before/after payloads | BUSINESS_DECISION_BLOCKED | Audit metadata avoids personal data by design | - | Privacy decision | D4 |
| P3-50 | Settings (typed registry), security policy, launch readiness | IMPLEMENTED_AND_TESTED | `/admin/settings`, `/security-policy`, `/launch-readiness` | test_gap_reference (3) | - | - |
| P3-51 | Privacy-request handling and deletion execution | IMPLEMENTED_AND_TESTED | `/admin/privacy-requests*` | test_privacy_deletion_execution, test_phase1_seo_privacy | Legal checks D4 | - |
| P3-52 | Meetings: confirm / decline / cancel | IMPLEMENTED_AND_TESTED | `/admin/meetings/*` | test_content_engagement | - | - |
| P3-53 | Maintenance job: SLA escalation, reminders, retention purge, dry run | IMPLEMENTED_AND_TESTED | `scripts/run_maintenance.py` | test_maintenance_dry_run (3) | - | - |
| P3-54 | PDF/Excel export, advanced analytics | OUT_OF_SCOPE_PHASE_4_OR_LATER | Not in PRD Phases 1-3 | - | - | - |

## Shared requirements

| ID | Requirement | Status | Implementation / endpoints | Tests | Remaining | Dependency |
|---|---|---|---|---|---|---|
| SH-01 | Pagination metadata on every paginated list | IMPLEMENTED_AND_TESTED | page, page_size, total, pages | test_every_paginated_list_reports_page_total_and_pages | - | - |
| SH-02 | Typed request/response schemas | IMPLEMENTED_AND_TESTED | Most endpoints typed - independently reviewed 2026-11-10 | OpenAPI check: no untyped dict responses remain | - | - |
| SH-03 | OpenAPI regenerated | IMPLEMENTED_AND_TESTED | `docs/api/openapi.json` | generated from the app | - | - |
| SH-04 | Rate limiting on public and sensitive actions | IMPLEMENTED_AND_TESTED | auth, invitation, submit buckets | test_invitation_actions_are_rate_limited | Per-process; edge limit external | - |
| SH-05 | Private storage, no public file URLs | IMPLEMENTED_AND_TESTED | S3 adapter, signed server-side access only | test_no_public_download_route | Dashboard bucket-privacy check external | - |
| SH-06 | Migrations additive; local fresh-database check | IMPLEMENTED_AND_TESTED | `0011`-`0015` | alembic upgrade/check on an empty database | - | - |
| SH-07 | Supabase development database at 0015 | EXTERNAL_CONFIGURATION_BLOCKED | Remote at 0012 (last verified); remote migration not authorised | - | Apply 0013-0015 later | Owner authorisation |
| SH-08 | Live end-to-end verification with real accounts | EXTERNAL_CONFIGURATION_BLOCKED | - | - | Live accounts, CORS origin, deployed service | Ops |
| SH-09 | Monitoring, backups, incident response, rollback evidence | EXTERNAL_CONFIGURATION_BLOCKED | - | - | Operator | Ops |
| SH-10 | GitHub CI green run | EXTERNAL_CONFIGURATION_BLOCKED | Workflow written | - | Needs a push (not authorised) | Owner |

## Completion by actual counts

Completion % = `IMPLEMENTED_AND_TESTED` / in-scope requirements (total minus `OUT_OF_SCOPE_PHASE_4_OR_LATER` and `NOT_APPLICABLE_WITH_JUSTIFICATION`). A phase is **not** 100% while any in-scope row is another status.

| Phase | Rows | In scope | Implemented and tested | Implemented, not fully verified | Not implemented | Business-decision blocked | External blocked | Out of scope | N/A | Completion % (tested) | Completion % (tested + unverified) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Phase 1 - Public Website | 39 | 36 | 29 | 0 | 0 | 3 | 4 | 1 | 2 | 80.6% | 80.6% |
| Phase 2 - Partner Portal | 37 | 36 | 26 | 0 | 0 | 10 | 0 | 1 | 0 | 72.2% | 72.2% |
| Phase 3 - Admin Platform | 54 | 52 | 40 | 0 | 0 | 10 | 2 | 1 | 1 | 76.9% | 76.9% |
| Shared requirements | 10 | 10 | 6 | 0 | 0 | 0 | 4 | 0 | 0 | 60.0% | 60.0% |
| **All** | 140 | 134 | 101 | 0 | 0 | 23 | 10 | 3 | 3 | 75.4% | 75.4% |

`NOT_IMPLEMENTED` rows: 0. Every unblocked requirement found is implemented; the remaining in-scope rows are blocked by a business decision or external configuration, or are implemented but need an independent review.


## Review pass 2026-11-10
All former `IMPLEMENTED_BUT_NOT_FULLY_VERIFIED` rows were re-read in source and covered by new negative/authorisation tests in `tests/api/test_review_inherited.py`; they are now `IMPLEMENTED_AND_TESTED` (the generated table above is authoritative). Turnstile was split: server-side validation (tested with a mocked Cloudflare) vs live verification (external). Unverified rows remaining: 0. Not implemented and unblocked: 0.

### Decision-blocked rows (23): what was already built independent of the decision
Eligibility: human evidence records, outcomes and audit exist; no thresholds or auto-decisions are coded (D5, D6, D9, D11). MFA: enrolment, verify, recovery, disable and session revocation exist; required/optional stays configuration (`STAFF_MFA_REQUIRED`) pending the owner (D28). Retention: metadata, expiry, purge job (dry-run) exist; periods stay unset (D4). Queue ownership: routing/backup/SLA/escalation settings exist; no default owners (D3). CMS: SEO, cover image URL, scheduling, approval exist; page structures and media hosting wait (D23, D29). Privacy: verification, tracking, staff handling, deletion executor exist; legal retention rules wait (D4). Onboarding: no generic structure was added because any task list, status or required-document rule would be an invented policy (D10). What each decision must state is in `../business-decisions-required.md`.

### scripts/inspect_and_seed.py (reviewed, not run, not committed)
Untracked file from another agent. It inserts one staff admin and one partner user into **whatever database `.env` points at (Supabase dev)**, with hard-coded default passwords (`Admin@2026`, `Partner@2026` unless env vars override), proceeds past the password-policy check, and only refuses when the target is production. It duplicates `scripts/create_staff_user.py` and fails ruff E402 (imports after `sys.path.insert`). It is excluded from Git via `.git/info/exclude`. Treat as unsafe: do not run it; delete or rewrite it to require an explicit local-only flag, prompted passwords and the policy check.
