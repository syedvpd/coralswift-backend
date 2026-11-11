# Final acceptance status (frontend email, every bullet)

Statuses: **DONE** = implemented and automated tests pass (375 passed on the final full run, `pytest -q`); **LIVE VERIFIED** = exercised against `https://coralswift-backend.onrender.com` with the real test identities (see "Live evidence"); **BLOCKED EXTERNAL** = code ready, a named external action or owner decision is missing; **NOT DONE** = not built, reason given. Detailed per-endpoint evidence (file, test name, OpenAPI) is in `docs/frontend-backend-requirements-tracker.md` under the same IDs.

## P1
| # | Requirement | Status | Evidence / blocker |
|---|---|---|---|
| 1 | CORS: admin, partner, public origins + localhost:5173; preflight to /auth/login | LIVE VERIFIED | OPTIONS /api/v1/auth/login returns 200 with `access-control-allow-origin` echoing and `allow-credentials: true` for `http://localhost:5173`, `https://coralswift.com`, `https://coralswift-ochre.vercel.app` (you set the Render variable). Separate admin/partner production origins were never supplied; add them to `CORS_ALLOWED_ORIGINS` when they exist |
| 2 | Staff accounts x4 with MFA | LIVE VERIFIED | `superadmin|bdm|reviewer|contentadmin@coralswift.example`; login + TOTP verify through the live API (see Live evidence) |
| 2 | Partner accounts: 2 in different organisations + 1 invited | LIVE VERIFIED | `partner1|partner2@coralswift.example`, separate organisations; `invited.partner@coralswift.example` stays `invited` |
| 2 | Test mailbox | BLOCKED EXTERNAL | No mail provider domain. Safe alternative delivered: tokens are returned in this handoff (invitation, privacy) and the dev backend logs only. Real mailbox needs Brevo + verified domain |
| 2 | Privacy verification token | DONE | unconsumed token and a consumed case seeded through `POST /privacy/requests`; verify returns 200 once, 400 on reuse |
| 3 | Strategic/M&A: list, detail, search, CSV, documents, outbox, audit, KPIs, notifications; never in partner payloads; `strategic` flags | DONE | `test_strategic_confidentiality.py` (3), `test_review_workflow.py`, `test_final_decisions.py`; flags `is_strategic` on audit, outbox, notification, feed rows |
| 4 | Partner isolation (applications, messages, notifications, documents, attachments, team, projects, collaboration, privacy) | DONE | `test_security_p2.py`, `test_collaboration.py`, `test_team_prefs_onboarding.py`, `test_profile_performance.py`; live: projects/inbox 404/empty across organisations |
| 5 | Per-role 403 matrix | DONE | `docs/api/role-permission-matrix.md` generated from guards; `test_permission_matrix_matches_real_enforcement`; live probes for 6 endpoints x 4 roles |
| 6 | scan_status + malware scanning, block download/review until clean | DONE (code) / BLOCKED EXTERNAL (activation) | ClamAV client, fail-closed, `scan_status` = not_scanned / scan_pending / clean / infected / scan_failed; `test_scanner_auth_policy.py`. Activation needs a running clamd and `SCANNER_BACKEND=clamav` (+ `CLAMAV_HOST`, `CLAMAV_PORT`). Until then files are quarantined and reported `not_scanned` (owner decision D33); nothing is ever reported clean unscanned |
| 6 | Documented size/type limits (staff, partner, public, CMS) | DONE | 10 MiB; pdf/png/jpg/docx/xlsx; CMS images png/jpg; 413 `FILE_TOO_LARGE`, 415 `UNSUPPORTED_FILE_TYPE` (handoff doc) |
| 6 | `retention_until` + auditable hard deletion | DONE (mechanism) / BLOCKED EXTERNAL (periods) | `POST /admin/documents/{id}/purge` audited; answers 409 `RETENTION_POLICY_NOT_APPROVED` until legal sets `retention.partner_document_days` |
| 7 | Private storage, authenticated access, audited downloads | DONE (code) / BLOCKED EXTERNAL (bucket evidence) | Streaming authenticated downloads, audit event per download, no storage keys exposed. Provider evidence that buckets block public access is not available to the code |
| 8 | Distinct login errors | DONE | 403 `ACCOUNT_NOT_ACTIVATED` (invited), 403 `ACCOUNT_DEACTIVATED` (suspend/deactivate, only after correct password), 423 `ACCOUNT_LOCKED` (only after correct password), 401 `INVALID_CREDENTIALS` (wrong password/unknown). `ACCOUNT_NOT_ACTIVATED` reveals that an invitation is pending for the address (requested trade-off, rate limited). Suspended and deactivated share one status and one code |
| 8 | Distinct invitation errors | DONE | `TOKEN_EXPIRED`, `TOKEN_ALREADY_USED`, `TOKEN_REVOKED`, `INVALID_OR_EXPIRED_TOKEN` |
| 9 | Auth contract | DONE | reset `/reset-password?token=`; activation `/activate?token=`; password minimum 12; access 30 min, refresh 7 days (staff and partner, from config); partner MFA optional then enforced; refresh keeps MFA state (`test_mfa.py`) |
| 10 | Bot token documented; 403 `BOT_CHECK_FAILED`; rate limits; duplicates | DONE (code) / BLOCKED EXTERNAL (live enforcement) | Turnstile widget token in `X-Bot-Token`; Render has `CAPTCHA_ENABLED=false`. To enforce: set `CAPTCHA_ENABLED=true`, rotate/confirm `TURNSTILE_SECRET_KEY`, set `TURNSTILE_ALLOWED_HOSTNAMES`, and send the token from the public site. Not switched on by me because the frontend does not send it yet and every public form would then fail |
| 11 | Privacy: verification, rate limit, completion docs | DONE | single-use 72 h token, setting-driven SLA (default 30 days, provisional, not legal advice) |

## P2 Partner portal
| Item | Status | Evidence |
|---|---|---|
| Projects (list/detail, shared only, labels, milestones, contact, 4 actions, share/unshare, document+message links) | DONE | `test_collaboration.py` |
| Onboarding (record, stages, checklist, dates, editable template) | DONE | `test_team_prefs_onboarding.py`, `test_d39_d45.py` |
| Document requests (resource, deadline, status, upload link) | DONE | `test_phase2_document_requests.py` |
| Document categories mandatory per pathway | BLOCKED EXTERNAL | configurable `required_documents.<pathway>` setting exists; the business has not defined the lists |
| Application status (outcome, decision date/explanation, last_updated, information requests with due date, kind enum) | DONE | `test_final_decisions.py` |
| Notifications (typed, categories, meta.total, preferences, mandatory) | DONE | `test_gap_lists.py`, `test_final_decisions.py`, `test_team_prefs_onboarding.py` |
| Messages (inbox, detail, read state, attachments, partner-initiated, sender label, partner_visible) | DONE | `test_collaboration.py` |
| Discussions, meetings, follow-ups | DONE | `test_collaboration.py` |
| Team management (all actions, protections, ownership transfer, admin view) | DONE | `test_team_prefs_onboarding.py`, `test_final_decisions.py` |
| Settings and security (PATCH /auth/me, MeOut, MFA disable, sessions, privacy requests, account closure) | DONE | `test_phase2_account.py`, `test_phase2_privacy.py`, `test_team_prefs_onboarding.py` |
| Profile fields, direct vs change request, null-clearing, revisions | DONE | `test_profile_performance.py`, `test_organizations.py` |
| Performance (indicators, definitions, trends, publish, scorecards, feedback, CSV) | DONE | `test_d39_d45.py`, `test_profile_performance.py` |
| Performance PDF export | NOT DONE | decision D26/D41: CSV only |

## P2 Admin console
| Item | Status | Evidence |
|---|---|---|
| Review checklist, exceptions, stage owners, reopen, state mapping | DONE | `test_review_workflow.py` |
| Scoring storage | NOT DONE | decision D9: pass/fail/not_applicable only, no numerical scoring |
| Six allocation stages, clearing the assignee, assignment history | DONE | `test_gap_applications.py`, `test_transitions.py`, audit rows |
| Typed schemas (overview, kpis, settings, org detail, permissions, transitions, launch-readiness, outbox, notifications, enquiry detail) | DONE | OpenAPI response models; `test_review_inherited.py`, `test_admin.py` |
| Pagination `total`, `pages`, `page`, `page_size` | DONE | `test_gap_lists.py` sweep |
| Strategic enquiries (access, discussion_type filter, assessment outcome, queue/owner/targets) | DONE | `test_review_workflow.py`, `test_section28.py`; named owners are staff-configured settings, none invented |
| Enquiry detail (assignment history, note types, reply endpoint) | DONE (reply off by default) | reply answers 409 `FEATURE_DISABLED` until `ENQUIRY_REPLY_ENABLED=true` (D15; needs real provider) |
| Documents (admin upload/replace, review history, replacement_requested) | DONE | `test_review_workflow.py` |
| Communication: templates create/activate/versions | DONE | `test_review_workflow.py` |
| Delivery status incl. bounces | DONE (code) / BLOCKED EXTERNAL (live) | `POST /webhooks/email`; needs Brevo webhook + `EMAIL_WEBHOOK_SECRET` |
| SPF/DKIM/DMARC evidence | BLOCKED EXTERNAL | no sending domain |
| Partner management (category, contact, diffs) | DONE | `test_profile_performance.py`, `test_phase3_org_history.py` |
| Staff edit of the partner profile | NOT DONE | decision D19: change requests only |
| Account detail, admin password reset | DONE | `test_gap_accounts.py` |
| CMS (hero, services, industries, navigation, media, SEO, scheduling, audit, updated_at/by, rich text) | DONE | `test_cms_audit_batch.py`, `test_review_inherited.py` |
| Settings typed schema | DONE | `test_ops.py` |
| Security-policy write | DONE (lockout) / NOT DONE (other values) | `security.login_max_failures`, `security.login_lockout_minutes` are writable; password length and token lifetimes stay environment-only |
| Secrets API | NOT DONE | decision D40: secrets stay in environment variables |
| Audit (export, by id, search, IP/device, outcome, before/after, catalogue) | DONE | `test_cms_audit_batch.py`, `test_review_inherited.py` |
| Reports (filters, turnaround, onboarding duration, totals not page-limited) | DONE | `test_final_decisions.py` |
| Reports PDF/Excel | NOT DONE | decision D26/D41: CSV only |

## P3
| Item | Status |
|---|---|
| q / sort / date filters on the six lists | DONE (`test_gap_lists.py`, `test_gap_applications.py`) |
| updated_at and actor names | DONE |
| Applicant name/email/phone on application rows | DONE |
| Application-per-reviewer workload | DONE (`GET /reviewer/workload`) |
| Admin user get/search/pagination/profile/activity/status enum | DONE (`test_requirements_batch.py`) |
| Reviewer and content administrator roles enforced | DONE (role matrix test) |
| 409 self-change and last super administrator | DONE |
| CSV permissions, strategic exclusion, 10,000-row cap | DONE |
| HttpOnly-cookie session | NOT DONE (optional; decision D1 keeps bearer tokens; residual XSS risk documented) |

## Business decisions answered with defaults (your instruction)
Thresholds and mandatory categories: configurable, unset. Retention: blocked until legal sets it. Partner roles: Owner and Member. Indicators: turnaround and completeness. Queue targets: 24 h first response, 48 h escalation target (escalation job still fires at the first-response breach). Providers: Render, Supabase, Brevo; no calendar, no CRM. Meetings: staff-attested only. Privacy SLA: 72 h verification, 30 days completion, provisional.
