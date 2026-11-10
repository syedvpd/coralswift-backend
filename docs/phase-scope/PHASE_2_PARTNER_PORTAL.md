# PRD Phase 2 - Partner Portal (backend)

Date 2026-11-10. Evidence: commit `15ebe59` (254 tests passed locally). Uncommitted work from another agent is present in the working tree and is **not verified** here. Item-level detail: `DEVELOPER_REQUEST_TO_PRD_MAPPING.md`, `../backend-gap-audit.md`.

## Delivered and tested
- Invitation, activation, login, refresh rotation, password reset, change-password, MFA (TOTP, recovery), session list/revoke, lockout, distinct token errors, `ACCOUNT_DEACTIVATED` (`test_auth`, `test_mfa`, `test_gap_phase_a`).
- Company profile with completion, history, change requests with decision (`test_organizations`, `test_ops`).
- Application lifecycle: draft, submit, readiness checklist, withdraw, resubmit, history, information requests and responses (`test_applications`, `test_reviewer`).
- Private partner documents: versions, review status, audited download, expiry reminders, retention mechanism (`test_partner_documents`).
- Partner notifications with read state and unread count (`test_gap_lists`); enquiry history.
- Organisation isolation on every endpoint (`test_security_p2`, anonymous route sweep).

## Remaining in-scope work
1. `MeOut`: `partner_role`, phone, `mfa_enabled`, `mfa_required`, `last_login_at`; `PATCH /auth/me` (name, phone) with audit.
2. MFA disable and a guard so enrolment never silently replaces an existing secret; sessions `expires_at` and sign-out-all-others.
3. Authenticated partner privacy requests (`/partner/privacy-requests`).
4. Document-request resource (deadline, status, link to the uploaded document).
5. Partner-visible application fields: decision date and reason, `last_updated`, information-request due date/status, activation timestamps.
6. Profile: editable-vs-approval metadata, null-clearing, before/after revisions.
7. Notification feed fields: category, title, related record; mark unread.

## Blocked
D1 (session persistence), D2 (login error detail), D4 (retention, account closure), D6 (mandatory documents per pathway), D10 (onboarding tasks), D20 (extra profile fields), D22 (partner roles), D27 (partner-visible eligibility). Partner MFA policy needs the owner's confirmation (currently optional).

## Acceptance
A partner can be invited, activate, sign in, keep data isolated, submit information and documents, follow status, answer information requests and receive notifications: covered by tests. Items 1-7 and the decisions above remain before sign-off.

## Update 2026-11-10 (Claude Code)
Delivered and tested: `MeOut` extension, `PATCH /auth/me`, session expiry and sign-out-others, MFA disable (partners), authenticated partner privacy requests, document-request resource with deadline/status/upload linking. Tests: `test_phase2_account.py` (4), `test_phase2_privacy.py` (1), `test_phase2_document_requests.py` (2), all passed. Open: partner-visible decision note (D27), notification feed fields, onboarding (D10), partner MFA policy confirmation.

## Completion (actual counts, 2026-11-10)
Local work only (no commit, push, deploy, backup or remote database operation). Full table with every requirement, evidence and tests: `REQUIREMENT_AUDIT_PHASES_1_3.md`. In scope 36 rows: **25 implemented and tested (69.4%)**, 1 not fully verified (editable-field metadata), 10 business-decision blocked (self-registration, login error detail, partner MFA policy, session cookie, partner roles, extra profile fields, eligibility/decision visibility, onboarding, per-pathway documents, retention/closure). Added this session: partner message fields (`title`, `category`, `related_reference`), `GET /partner/notifications/unread-count`, `POST /partner/notifications/{id}/unread`.
