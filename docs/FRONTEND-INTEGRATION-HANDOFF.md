# Frontend integration handoff (backend state 2026-11-11, local only)

Contract file: `docs/api/openapi.json` (generated from `create_app()`, sorted keys, indent 1; 251 paths, 435 schemas; verified identical to the runtime schema). **The live service `https://coralswift-backend.onrender.com` still runs the OLD version (162 paths, no `/partner/projects`). Nothing below is callable on the live URL until it is deployed.** The development database is already migrated to `0025`. Base path `/api/v1`. Envelope `{success, message, data, meta}`; errors `{success:false, message, error:{code, details}}`. Pagination meta keys: `page, page_size, total, pages`. Roles/403 matrix: `docs/api/role-permission-matrix.md`.

## Auth facts the frontend must use
- Bearer tokens only (D1). Access 30 min, refresh 7 days (staff and partner), refresh keeps MFA state.
- Password minimum **12** characters. Invitation link `/activate?token=` (D38). Reset link `/reset-password?token=`.
- Login errors: 401 `INVALID_CREDENTIALS` (also for unknown, invited, wrong password); 403 `ACCOUNT_DEACTIVATED` and 423 `ACCOUNT_LOCKED` only after the correct password. Invitation/reset token errors: `TOKEN_EXPIRED`, `TOKEN_ALREADY_USED`, `TOKEN_REVOKED`, `INVALID_OR_EXPIRED_TOKEN`.
- `GET /auth/me` returns `partner_role` (owner|member), `permissions` (owner: `team.manage`), `account_status`, `mfa_enabled`, `mfa_required`, `last_login_at`.

## Documents and malware scanning (D33: quarantine-only)
Every document payload carries `scan_status`, always `not_scanned` today, and `upload_status: quarantined`. **No malware scanner is active; the frontend requirement for active scanning is NOT satisfied.** Do not show files as "clean". Downloads are authenticated and audited. Limits: 10 MiB per file, pdf/png/jpg/docx/xlsx (CMS images: png/jpg).

## Typed responses to wire
| Area | Endpoints |
|---|---|
| Notifications | `GET /partner/notifications` rows: `title`, `description`, `category` (application\|account\|acknowledgement\|other), `related_record {type, reference}`, `link` (portal-relative, **assumed** route `/applications?reference=`), `meta.total`, `meta.unread`. Preferences: `GET/PUT /partner/notification-preferences` (mandatory: `account`, `application`; optional: `acknowledgement`) |
| Applications | `status`, `status_label` (`pilot_onboarding` = "Approved - pilot"), `last_updated`, `decided_at`, `decision_explanation` (reviewer-written, partner-safe), `next_information_due`; messages carry `due_date`, `is_overdue`, `requested_categories` |
| Document requests | `/partner/document-requests[/{id}]`, upload with form field `request_id` |
| Projects | `/partner/projects[/{id}]` + `acknowledge|confirm|respond|submit-information`; `status` enum + `status_label` |
| Inbox | `/partner/messages` (read/unread, attachments), `POST /partner/messages` |
| Collaboration | `/partner/discussions|meetings|follow-ups` + `/{id}/respond` (`action`: reply, accept, decline, complete per kind) |
| Team | `/partner/team` + invitations, resend, cancel, role, deactivate, activate, delete, transfer-ownership (owners only). Errors `LAST_OWNER`, `SELF_CHANGE` |
| Onboarding | `GET /partner/onboarding` (null until staff start one): `stages`, `tasks[]`, `progress`, `provisioned_at`, `first_login_at` |
| Performance | `/partner/performance/{summary,trends,scorecards,feedback,export.csv}`; only staff-published rows appear; `definition` documents each calculation |
| Profile | new fields `trading_name, company_type, state, city, primary_industry, competencies, operating_model, coverage, years_of_experience, offices, workforce, financial_period, additional_contacts`; omit = unchanged, `null` clears. `company_type`/`operating_model` are free text until D44 is confirmed |
| Staff | review checklist `PUT /reviewer/applications/{id}/checklist` (pass\|fail\|not_applicable\|pending + note; **no scores**), exceptions, stage owners, reopen; team list `GET /reviewer/organizations/{id}/team` |

## Behaviour changes to be aware of
- Review checklist results are `pass|fail|not_applicable|pending`; numerical scores are rejected (422).
- `POST /admin/enquiries/{id}/reply` answers 409 `FEATURE_DISABLED` unless `ENQUIRY_REPLY_ENABLED=true` (D15).
- `POST /admin/documents/{id}/purge` answers 409 `RETENTION_POLICY_NOT_APPROVED` until the retention setting exists (D4).
- BDMs: read-only on projects, collaboration, partner messages, onboarding and the team list, **only for organisations whose originating partner enquiry is assigned to them**; every write is 403; no performance, no strategic data.


## Added in the final pass
- **Enums (D44, enforced):** `company_type`: private_limited, public_limited, partnership, llp, proprietorship, nonprofit, other. `operating_model`: onsite, remote, hybrid, multi_location. Assessment `outcome`: approved, rejected, needs_clarification, pending. Performance `indicator_key`: application_turnaround_days, document_completeness_percentage. Component names in OpenAPI: `CompanyType`, `OperatingModel`, `AssessmentOutcome`, `IndicatorKey`.
- **Profile edits (D19):** `PUT /partner/organization` only fills fields that are still empty. Changing or clearing a value returns 409 `CHANGE_REQUEST_REQUIRED`; use `POST /partner/organization/change-requests` (explicit `null` clears). `GET /partner/organization/editable-fields` flags `direct_update` and `approval_required`.
- **Performance (D39):** `GET /partner/performance/summary` always returns both indicators with `state` = `published` | `unavailable`; unpublished values are never exposed. Definitions: turnaround days = average days from submission to recorded decision for applications decided in the period; completeness % = accepted, current, unexpired required categories / required categories x 100 (unavailable until the pathway's required categories are defined).
- **BDM (D45):** read-only access only to organisations explicitly assigned by a super administrator (`POST/DELETE /admin/organizations/{id}/bdm-assignments`). Being the assignee of the originating enquiry grants nothing.
- **Defaults:** first-response target 24 h, escalation target 48 h (settings `sla.<queue>`, `sla_escalation.<queue>`); privacy request completion due in 30 days (setting `privacy.completion_days`), email verification link valid 72 h (setting `privacy.verification_hours`). These are operational targets, not legal advice.
- **Onboarding template:** `GET/PUT /admin/onboarding-template`; `POST /reviewer/onboarding` accepts `use_template`.
- **Bot token:** the public site obtains `X-Bot-Token` from the Cloudflare Turnstile widget in the browser (no backend endpoint). Protected endpoints answer 403 `BOT_CHECK_FAILED` without a valid token once `CAPTCHA_ENABLED=true`; today the Render service has it **false**, so the live check is not enforced.
- **Limits:** 10 MiB per file; pdf, png, jpg, docx, xlsx (CMS images png/jpg); 12 MiB request body; max 10 documents per enquiry; 413 `FILE_TOO_LARGE`, 415 `UNSUPPORTED_FILE_TYPE`.
