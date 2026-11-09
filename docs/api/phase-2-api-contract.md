# Phase 2 API Contract (base `/api/v1`)

Envelope, error format, request IDs, rate-limit headers as Phase 1. Auth: `Authorization: Bearer <access token>` (opaque, from `/auth/login`).
Roles: **partner** (organization taken from the active membership, never from input), **reviewer** (`partner_reviewer`), **super admin** (`super_administrator`).
Foreign-organization or unassigned resources answer **404**, wrong role **403**, no/expired/revoked token **401**. Audit = row in `activities`.

## Auth
| Method path | Who | Notes |
|---|---|---|
| `POST /auth/login` | public, rate-limited | generic `INVALID_CREDENTIALS` for any failure; lockout after `LOGIN_MAX_FAILURES` (audited) |
| `POST /auth/refresh` | public, rate-limited | rotates access+refresh; reuse of an old refresh token revokes the session |
| `POST /auth/logout` | any | revokes current session |
| `POST /auth/invitations/accept` | public | `{token, password}`; single-use token; password policy (>=12 chars) |
| `POST /auth/password-reset/request` | public | always `202` same body; emails link if account exists |
| `POST /auth/password-reset/confirm` | public | single-use, 1 h; revokes all sessions |
| `GET /auth/me`, `GET /auth/sessions`, `DELETE /auth/sessions/{id}` | any | own account/sessions only |
| `POST /auth/mfa/enroll`, `/auth/mfa/confirm`, `/auth/mfa/verify` | any session (also unverified) | TOTP. Enroll returns secret + otpauth URI; confirm `{code}` enables MFA and returns 8 recovery codes once; verify `{code}` or `{recovery_code}` completes sign-in. Login response carries `mfa_required` / `mfa_enrollment_required`. Until verified, protected routes answer `401 MFA_REQUIRED` (or `403 MFA_ENROLLMENT_REQUIRED` for staff when `STAFF_MFA_REQUIRED`); `/auth/me` and logout stay available |
| `POST /reviewer/invitations` | super admin | `{email, full_name, organization_id | new_organization_legal_name, source_enquiry_reference?}`; creates pending account (invitation-only; self-registration not built) |

## Partner (role: partner)
| Endpoint | Behaviour |
|---|---|
| `GET/PUT /partner/organization` | own profile; partial update; optional `expected_version` -> `409 PROFILE_VERSION_CONFLICT`; audited; revision stored |
| `GET /partner/organization/completion`, `/history` | completion % + missing fields; change history |
| `POST /partner/documents` (multipart `file`, `category`, `expires_on?`) | private upload, status `quarantined`; 413/415 on size/type |
| `GET /partner/documents`, `GET /{id}`, `GET /{id}/history` | own documents (no storage keys) |
| `POST /partner/documents/{id}/versions` | replace; old versions kept |
| `GET /partner/documents/{id}/download?version=` | authorised, audited byte stream, `Cache-Control: private, no-store` |
| `DELETE /partner/documents/{id}` | soft delete; data retained |
| `POST /partner/applications` `{pathway, cover_note?}` | create draft; one open application per organization (`409 APPLICATION_ALREADY_OPEN`) |
| `GET /partner/applications`, `GET /{id}`, `PATCH /{id}` (draft only), `GET /{id}/readiness` | partner-safe view; unknown fields rejected |
| `POST /{id}/submit` | needs complete profile + 7 required document categories (none rejected) else `422 APPLICATION_INCOMPLETE`; takes snapshot; notifies |
| `POST /{id}/resubmit` | only after every open information request is answered |
| `POST /{id}/withdraw` | allowed before pilot_onboarding |
| `GET /{id}/history` | status changes with partner note only (never reviewer reasons) |
| `GET/POST /{id}/messages` | conversation; `POST {in_reply_to, body}` answers an open information request |

## Reviewer (roles: reviewer, super admin) - reviewers see only applications assigned to them; super admin sees all submitted
| Endpoint | Behaviour |
|---|---|
| `GET /reviewer/applications?status=&unassigned=&page=` | paginated queue (drafts never listed) |
| `GET /reviewer/applications/{id}` | profile, documents, eligibility records, full history with reasons |
| `POST /{id}/assign` (super admin) | `{reviewer_id}` must be an active staff reviewer |
| `POST /{id}/transition` | `{to_status, reason?, partner_note?}`; centralised state machine; reason required for decisions; `409 INVALID_TRANSITION`, `422 ASSIGNMENT_REQUIRED / ELIGIBILITY_RECORD_REQUIRED / REASON_REQUIRED`; information_requested/withdrawn/draft/submitted cannot be forced |
| `POST /{id}/information-requests` | creates partner-visible request and moves to `information_requested` |
| `GET /{id}/messages` | conversation incl. author ids |
| `POST/GET /{id}/notes` | internal notes (never exposed to partner routes; text not copied to audit) |
| `POST/GET /{id}/eligibility-verifications` | append-only human record; `verified_with_exception` needs `exception_note`; no thresholds evaluated |
| `POST /{id}/documents/{doc}/review` | `{version_no?, status, comment}`; comment required for rejected/clarification_needed; visible to partner |
| `GET /{id}/documents/{doc}/download` | audited download of that organization's document |
| `GET /{id}/history` | audit trail (actor, request id, metadata) |

Status values: draft, submitted, eligibility_verification, capability_review, commercial_legal_review, pilot_onboarding, scale_up, information_requested, rejected, withdrawn.
Partner labels hide internal wording (`rejected` is shown as "Not progressed").
