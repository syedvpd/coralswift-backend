# PRD Master Requirement Register - Phases 0-3 and s.28 (final evidence audit, 2026-11-09)

Source: Coral Swift PRD v2.0 s.1-30, read in full for this audit. s.1-7, 24-26 and 30 add no backend requirement beyond the rows below; page, copy, SEO and analytics items in s.4-7, 16 and 20 are frontend. Phase 4 (s.15I, s.23) and the s.23 out-of-scope list are excluded by instruction.

**Status values**
- **VERIFIED** = IMPLEMENTED AND VERIFIED: code exists and an automated test run in this audit passed. Tests use the local Docker PostgreSQL with fakes and mocks only. Counts: 211 passed before the final edits of this audit, full-suite count after them in `docs/qa/final-backend-test-report.md`.
- **NOT VERIFIED** = IMPLEMENTED NOT VERIFIED. **PARTIAL** = PARTIALLY IMPLEMENTED. **NOT IMPL** = NOT IMPLEMENTED.
- **BLOCKED** = BLOCKED BY EXTERNAL/BUSINESS DECISION. Also used for frontend or content items that are outside this backend.
- A local test is never evidence of real Brevo, Turnstile, malware scanning, Supabase journeys, CI or Render behaviour. Where only a mock or fake ran, the row says so.
- Phase 1 acceptance stays **FAIL - NOT ACCEPTED** (`docs/qa/phase-1-verification-report.md`).

Test files are under `tests/api/` unless a path is given. Module paths are under `app/modules/`.

## Phase 0 - Foundation (s.16, 17, 19, 21, 22)
| # | Requirement | Implementation | Evidence | Status |
|---|---|---|---|---|
| 0.1 | Documented REST API, OpenAPI | `app/main.py`, `api/v1/router.py`; docs disabled in production | `test_app.py::test_startup_and_openapi`, `test_docs_disabled_in_production` | VERIFIED |
| 0.2 | PostgreSQL and migrations | `app/database`, `migrations/` 0001-0010 | `test_database.py::test_alembic_has_single_head`; `alembic check` clean on the local test DB in this audit; Supabase dev at 0010 is earlier evidence, not rerun | VERIFIED (local) |
| 0.3 | Env separation, secrets via environment, none in repo or logs | `core/config.py`, `.env` git-ignored, `.env.example` placeholders | `unit/test_config.py`, `test_auth.py::test_secrets_never_in_logs`, `unit/test_logging_security_pagination.py` | VERIFIED |
| 0.4 | Input validation, error envelope, no stack traces | `core/errors.py` | `test_app.py::test_validation_error_envelope`, `test_unexpected_exception_hides_internals` | VERIFIED |
| 0.5 | Security headers, CORS allow-list, trusted hosts, body-size limit, request IDs | middleware in `main.py` | `test_app.py` (headers, CORS x2, untrusted host, request id), `test_documents_status_security.py::test_oversized_request_rejected` | VERIFIED (app level) |
| 0.6 | HTTPS and secure transport | terminated by Render or proxy | none possible locally | BLOCKED (deployed environment) |
| 0.7 | Rate limiting on public and auth endpoints | `core/protection.py` (per-process window) | `test_rate_limit`, `test_status_lookup_is_rate_limited`, `test_auth.py::test_login_rate_limited` | VERIFIED per process; proxy/CDN limit BLOCKED (deployed) |
| 0.8 | Health and readiness | `health/router.py` | `test_health.py` (4 tests); container check in the earlier run, not rerun | VERIFIED |
| 0.9 | Structured logging with secret redaction | `core/logging.py` | `unit/test_logging_security_pagination.py` | VERIFIED |
| 0.10 | Docker image, non-root user | `Dockerfile` | build, uid 10001 and health checks in the earlier run only | NOT VERIFIED in this audit |
| 0.11 | CI/CD, automated tests, rollback plan | `.github/workflows/ci.yml`, `render.yaml`, readiness doc | workflow never executed on GitHub | PARTIAL |
| 0.12 | Version control | directory has no Git history; git not initialised | - | BLOCKED (owner decision) |
| 0.13 | Monitoring, error tracking, uptime alerts, incident owner | none configured | - | BLOCKED (operations) |
| 0.14 | Encrypted backups and restoration test | one manual dev-DB dump, restore-tested once (earlier run) | no production backup policy | PARTIAL / BLOCKED (production policy) |
| 0.15 | Hosting, CDN, staging and production | `render.yaml` prepared, not deployed | - | BLOCKED (deployment not authorised) |

## Phase 1 - Public website backend (s.8-12, 15B/C/E, 19, 28)
| # | Requirement | Implementation | Evidence | Status |
|---|---|---|---|---|
| 1.1 | General contact form: fields, validation, consent, acknowledgement | `enquiries/`, `POST /enquiries/contact` | `test_contact.py` (5 tests) | VERIFIED |
| 1.2 | Project enquiry (IT/Non-IT, scope, timeline, volume, geography, optional files) | `projects/` | `test_project_partner_strategic.py::test_project_*` | VERIFIED |
| 1.3 | Partner application form (all s.12 fields) and document links | `partners/` | `test_partner_valid_application`, `test_partner_invalid` | VERIFIED |
| 1.4 | Strategic discussion form (confidential) | `strategic/` | `test_strategic_*` (3 tests) | VERIFIED |
| 1.5 | Meeting request; confirm only after calendar check | `engagement/` (`MeetingRequest`, DB CHECK `confirm_needs_calendar_check`) | `test_content_engagement.py::test_meeting_request_and_manual_confirmation`, `test_meeting_db_forbids_confirmation_without_calendar_check` | PARTIAL (staff-attested confirmation; calendar integration BLOCKED) |
| 1.6 | Server-side validation, phone and email validation | Pydantic schemas per module | `test_contact.py::test_validation_errors`, `test_project_invalid` | VERIFIED (client-side validation and country-aware picker are frontend: BLOCKED) |
| 1.7 | Secure uploads: type, size, magic bytes, path traversal, private storage | `documents/` | `test_documents_status_security.py` (allowed, rejected, docx/oversize, traversal, storage failure, no public download) | VERIFIED with local storage and fakes; real S3 round trip done on dev buckets in the earlier run, not rerun |
| 1.8 | Malware scanning where available (s.13, 19) | files stored as `quarantined`; no scanner | `documents/constants.py`, `partner_documents/service.py:125` | PARTIAL (no scanner; owner must choose one or formally accept quarantine-only) |
| 1.9 | Submission reference number | `enquiry_reference_seq` | `test_references_are_unique`, `test_reference_numbers_unique_under_concurrency` | VERIFIED |
| 1.10 | Duplicate-submission handling and idempotency | `common/idempotency.py` | `test_idempotency.py` (10 tests) | VERIFIED |
| 1.11 | Bot and spam protection | Turnstile verifier `integrations/botcheck.py`; `CAPTCHA_ENABLED`; production requires it (`core/config.py`) | `unit/test_botcheck.py` (mocked Cloudflare: missing, invalid, expired, provider error), `unit/test_config.py::test_captcha_rules`, `test_bot_check_hook` | PARTIAL (never run against real Cloudflare; keys pending) |
| 1.12 | Acknowledgement and internal notification emails | `notifications/` outbox, Brevo adapter | `test_notifications.py` (6), `unit/test_adapters.py` (Brevo mocked) | Outbox logic VERIFIED locally; real Brevo delivery NOT VERIFIED (key and DNS pending) |
| 1.13 | Failure handling: no silent loss, admin visibility, retry | `admin/ops_router.py` `/admin/notifications` | `test_section28.py::test_notification_failure_visibility_and_retry`, `test_contact.py::test_db_failure_rolls_back_everything_and_sends_no_email` | VERIFIED (preserving entered data and retry guidance are frontend) |
| 1.14 | Status lookup with minimal data | `enquiries/` status token | `test_status_with_token_returns_minimal_fields`, `test_status_failures_are_indistinguishable` | VERIFIED |
| 1.15 | Distinct conversion paths routed to queues and owners (s.15B, s.28) | `enquiries/routing.py` | `test_section28.py::test_routing_sla_backup_owner_and_ack_promise` | VERIFIED (owner and SLA values BLOCKED, business) |
| 1.16 | Lead source, category, priority, owner, status, follow-up date | `enquiries/models.py`, `admin/` | `test_admin.py::test_assignment_status_and_followups` | VERIFIED |
| 1.17 | Show criteria (3 years, 50 staff, INR 2 crore) as proposed, applicability by pathway | `catalog/router.py` `/catalog/partner-criteria` (status "proposed") | `test_section28.py::test_catalog_is_illustrative_and_criteria_proposed` | PARTIAL (pathway applicability BLOCKED, business) |
| 1.18 | Three pathways with distinct routes | partner `pathway` field, separate enquiry types | `test_project_partner_strategic.py` | VERIFIED |
| 1.19 | Eight-item partner submission checklist | `EvidenceCategory` in `documents/constants.py` | `test_partner_evidence_needs_category_and_uses_partner_area` | VERIFIED |
| 1.20 | Illustrative project categories labelled as examples | `/catalog/project-categories` always illustrative | `test_catalog_is_illustrative_and_criteria_proposed` | VERIFIED |
| 1.21 | FAQ, search, tags, related content, downloads, sitemap | `content/` public router | `test_content_engagement.py::test_content_workflow_and_public_visibility`, `test_content_attachment_download` | VERIFIED |
| 1.22 | Newsletter opt-in | `engagement/` | `test_newsletter_and_privacy_requests` | VERIFIED (list only; nothing is sent) |
| 1.23 | Data minimisation: unknown fields rejected, no sensitive data requested | `extra="forbid"` schemas | `test_missing_consent_and_unknown_fields_rejected` | VERIFIED |
| 1.24 | Trust centre content only with evidence and permission (s.15A) | claims register (28.1) | `test_claims_gate_publication` | VERIFIED (claims data BLOCKED, business) |
| 1.25 | Pages, copy, brand, SEO metadata, analytics events, cookie consent, legal pages, accessibility | not backend | - | BLOCKED (frontend and content) |
| 1.26 | Authenticated email: SPF, DKIM, DMARC (s.17) | none | - | BLOCKED (domain and Brevo setup) |

## Phase 2 - Partner portal (s.13, 14, 19, 11)
| # | Requirement | Implementation | Evidence | Status |
|---|---|---|---|---|
| 2.1 | Secure sign-in, password reset, invitation-only accounts | `auth/` | `test_auth.py` (invitation, reset, generic errors) | VERIFIED |
| 2.2 | Session expiry, refresh rotation with replay revoke, logout, session list | `auth/service.py` | `test_expired_access_token_rejected`, `test_refresh_rotation_and_replay_revokes_session`, `test_logout_revokes_token`, `test_concurrency_p2.py::test_concurrent_refresh_token_use_allows_one_rotation` | VERIFIED |
| 2.3 | Lockout and brute-force defence, Argon2id | `auth/security.py` | `test_lockout_after_repeated_failures_even_with_correct_password`, `test_login_errors_are_generic` | VERIFIED |
| 2.4 | MFA for privileged users, optional for partners, recovery | `auth/mfa.py` | `test_mfa.py` (7), `test_section28.py::test_mfa_recovery_codes_regeneration`, `test_ops.py::test_mfa_reset_by_super_admin` | VERIFIED |
| 2.5 | Partner self-registration | invitation-only by design | - | BLOCKED (business: invitation or self-registration) |
| 2.6 | Partner profile, completion indicator, change history | `organizations/` | `test_organizations.py::test_profile_update_completion_and_history`, `test_validation_and_optimistic_concurrency` | VERIFIED |
| 2.7 | Profile update requests | `organizations/extras.py` | `test_ops.py::test_profile_change_request_flow_and_partner_extras` | VERIFIED |
| 2.8 | Application lifecycle, snapshot, history, withdraw, duplicate guard | `applications/` | `test_applications.py` (5), `test_concurrency_p2.py` | VERIFIED |
| 2.9 | Six-stage project allocation as separate statuses with timestamps, owners, notes | `applications/transitions.py`, `ApplicationStatusHistory` | `unit/test_transitions.py` (9), `test_reviewer.py::test_workflow_rules_enforced` | VERIFIED |
| 2.10 | Reviewer messages, additional document requests, responses, resubmission | `messaging/` | `test_reviewer.py::test_information_request_response_resubmission`, `test_internal_notes_never_reach_partners` | VERIFIED |
| 2.11 | Reviewer scope, evidence review, eligibility notes | `reviews/` | `test_reviewer.py` (6), `test_security_p2.py::test_reviewer_cannot_act_outside_assignment` | VERIFIED |
| 2.12 | Eligibility is a human record; no auto approve or reject from form values | `reviews/` eligibility records; no thresholds in code | `test_project_partner_strategic.py::test_partner_thresholds_never_decide` | VERIFIED |
| 2.13 | Partner documents: private, versions, review, expiry, download audit | `partner_documents/` | `test_partner_documents.py` (7), `test_reviewer.py::test_document_review_and_download` | VERIFIED (local storage fake) |
| 2.14 | Safe download: authorised, audited, `attachment`, no public URL | `partner_documents/router.py:116-140` | `test_replace_keeps_history_and_download_audited`, `test_no_public_download_route` | VERIFIED; no scan gate exists, files stay quarantined (see 1.8) |
| 2.15 | Retention rule and secure deletion of stored files | `admin/maintenance.py::purge_retained` | `test_ops.py::test_retention_purge_and_expiry_reminders` (fake storage) | Mechanism VERIFIED; retention periods BLOCKED (business); no real-storage purge ever run |
| 2.16 | Document expiry reminders | `maintenance.py::send_expiry_reminders` | same test | VERIFIED (inert until `expiry_reminder_days` is set) |
| 2.17 | Notifications and enquiry history for partners | `organizations/extras.py` | `test_ops.py::test_profile_change_request_flow_and_partner_extras` | VERIFIED |
| 2.18 | Organization isolation, IDOR (foreign ids return 404) | org-scoped queries | `test_security_p2.py::test_cross_organization_idor_matrix`, `test_organizations_are_isolated`, `test_partner_documents.py::test_cross_organization_access_is_404` | VERIFIED |
| 2.19 | Every protected route rejects anonymous requests | - | `test_security_p2.py::test_every_protected_route_rejects_anonymous_requests` | VERIFIED |
| 2.20 | Append-only audit trail with actor and request id | `activities` table plus DB trigger | `test_audit_e2e.py::test_audit_table_is_append_only`, `test_reviewer.py::test_audit_history_has_actors_and_request_ids` | VERIFIED |
| 2.21 | Full partner journey | - | `test_audit_e2e.py::test_full_partner_journey` (local DB, fake email and storage) | VERIFIED locally; Supabase or staging journey NOT run |
| 2.22 | Reviewer assignment authority | super admin assigns; notification sent | `test_ops.py::test_reviewer_assignment_sends_notification` | VERIFIED; who may assign BLOCKED (business confirm) |
| 2.23 | Explicit "approved" application status | not in the status model (s.11 lists six stages only) | - | BLOCKED (business decision) |

## Phase 3 - Admin platform (s.14, 15H, 20)
| # | Requirement | Implementation | Evidence | Status |
|---|---|---|---|---|
| 3.1 | Four roles with least privilege | `auth/constants.py`, `require_staff` | `test_admin.py::test_anonymous_and_wrong_roles_rejected`, `test_security_p2.py::test_role_separation` | VERIFIED |
| 3.2 | Overview and recent activity | `GET /admin/overview` | `test_admin.py` | VERIFIED |
| 3.3 | Enquiry and lead management: filters, search, assign, status, priority, follow-ups, history | `admin/router.py`, `service.py` | `test_filters_search_pagination`, `test_assignment_status_and_followups` | VERIFIED |
| 3.4 | Strategic and M&A restricted; financial documents more restricted | `visible_types`, hidden fields | `test_admin.py::test_bdm_cannot_see_strategic_or_financial_data`, `test_strategic_documents_are_confidential` | VERIFIED; BDM access (default none) BLOCKED (business confirm) |
| 3.5 | Partner database and document review | `admin/` organizations | `test_organizations_and_staff_management` | VERIFIED |
| 3.6 | Website pages and insights with approval workflow and publication history | `content/` draft, in_review, approved (super admin), published; versions | `test_content_workflow_and_public_visibility`, `test_content_rejection_slug_conflict_and_permissions` | VERIFIED; approver role BLOCKED (business confirm) |
| 3.7 | User roles and staff invitations | `auth/service.py::invite_staff_user`, `scripts/create_staff_user.py` | `test_organizations_and_staff_management`, `test_auth.py::test_only_super_admin_can_invite` | VERIFIED |
| 3.8 | Notification templates and system settings | `admin/settings_service.py`, template overrides | `test_ops.py::test_settings_validation_and_permissions`, `test_template_override_is_used_and_validated` | VERIFIED |
| 3.9 | Reports, formula-safe CSV export, audit-log viewer | `admin/` | `test_csv_export_is_safe_and_audited`, `test_audit_log_super_admin_only` | VERIFIED |
| 3.10 | KPIs: enquiries by category and source, application completion, response time, review turnaround, portal adoption | `GET /admin/reports/kpis` (`ops_router.py`) | `test_ops.py::test_kpis` | PARTIAL: "qualified enquiry", "share meeting screening criteria" and "enquiry to qualified discussion" are not auto-computed (no agreed definition; humans decide). No numeric targets, by design |
| 3.11 | Analytics events (page views, CTA clicks) | frontend | - | BLOCKED (frontend) |
| 3.12 | Privacy requests: access, correction, deletion intake and handling | `engagement/` | `test_newsletter_and_privacy_requests`, `test_section28.py::test_privacy_deletion_execution` | VERIFIED (deletion anonymises contact data; free text and documents need manual review); privacy policy and retention BLOCKED |
| 3.13 | Backup restoration test and incident response (s.15H) | - | - | BLOCKED (operations) |

## s.28 acceptance-level requirements
| # | Requirement | Implementation | Evidence | Status |
|---|---|---|---|---|
| 28.1 | Claims register: owner, evidence status (verified, pending, illustrative, prohibited) | `content/` `ContentClaim`, `/admin/content-claims` | `test_claims_gate_publication` | VERIFIED (register data BLOCKED, business) |
| 28.2 | Partner publication gate: names, logos, testimonials need verification and written permission | `claim_problems` blocks publish; `PERMISSION_REQUIRED`; un-clearing pulls content | same test | VERIFIED |
| 28.3 | No certification or compliance claims without assessment (s.19) | claim category needs permission | same test | VERIFIED |
| 28.4 | Distinct conversion paths routed to owners | `enquiries/routing.py` | `test_routing_sla_backup_owner_and_ack_promise` | VERIFIED (owner values BLOCKED) |
| 28.5 | Partner submission completeness (8 items) | see 1.19 | see 1.19 | VERIFIED |
| 28.6 | Eligibility display, stored evidence, reviewer outcome, no auto decision | see 1.17 and 2.12 | see there | PARTIAL (pathway applicability BLOCKED) |
| 28.7 | Allocation statuses with timestamps, owners, notes | see 2.9 | see 2.9 | VERIFIED |
| 28.8 | Strategic and financial records restricted, excluded from public search, retention policy | see 1.4 and 3.4 | `test_strategic_confidential_and_not_leaked` | VERIFIED; retention policy BLOCKED |
| 28.9 | Project listing safeguards ("illustrative category") | see 1.20 | see 1.20 | VERIFIED |
| 28.10 | Contact readiness launch gate | `GET /admin/launch-readiness`, public `/site/contact` | `test_launch_readiness_and_public_contact` | VERIFIED (confirmed values BLOCKED, business) |
| 28.11 | Service levels: targets, queue owners, escalation, out-of-office; no acknowledgement promise until enabled | `sla.*`, `route.owner/backup.*`, `ack_promise_enabled` settings; `maintenance.escalate_overdue` | `test_routing_sla_backup_owner_and_ack_promise`, `test_escalation_and_first_response` | VERIFIED locally; cron job never run on Render; values BLOCKED (business) |
| 28.12 | Content governance: owner, reviewer, last reviewed, version control, PDF versions | `content/` versions and attachment | `test_content_workflow_and_public_visibility`, `test_content_attachment_download` | VERIFIED |
| 28.13 | Form failure handling and admin alerts | see 1.13 | see 1.13 | VERIFIED |
| 28.14 | Data minimisation | see 1.23 | see 1.23 | VERIFIED |

## s.29 business-owner checklist (backend view)
All ten areas need owner sign-off, so they are **BLOCKED** until the owner provides: brand and corporate facts; partner claims data; service copy; thresholds per pathway; named queue owners and SLA numbers; privacy notice, retention schedule and incident owner; launch checks (accessibility, performance, SEO, backup, monitoring, rollback). Backend controls for Forms, Workflow and Privacy/security are the rows above.

## Audit result
- One mandatory backend gap found: the **portal adoption KPI** (s.20). Added in this audit (`ops_router.py`, asserted in `test_ops.py::test_kpis`). No other mandatory backend requirement found missing.
- No row is NOT IMPLEMENTED. Rows not marked VERIFIED are PARTIAL, NOT VERIFIED or BLOCKED for the stated reason.
- Not audited by execution: anything needing a real provider, Supabase journeys, GitHub CI, Render or a browser.
