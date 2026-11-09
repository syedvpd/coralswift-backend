# Phase 2 Architecture - Partner Portal Backend

Status: **implemented, CONDITIONAL** (see `docs/qa/phase-2-implementation-report.md`). Migrations were merged into 0004 (auth + organizations + audit), 0005 (documents), 0006 (applications/reviews/messaging).
Phase 1 acceptance remains **FAIL - NOT ACCEPTED**; Phase 2 builds on Phase 1 code and does not change that decision.

## PRD basis (original PRD v2.0)
s.13 partner portal (secure sign-in, password reset, MFA for privileged / consider for partners, role-based access, session expiry,
profile + completion indicator, application status + reviewer messages, document requests, notifications, change history, private documents
with type/size limits, scanning where available, audit, retention); s.14 roles (Partner Reviewer: applications, evidence review, eligibility notes,
status updates); s.11 / s.28 six evaluation stages tracked as separate statuses with timestamps, owners, notes; s.8 criteria (proposed only);
s.19 security; s.22-23 Phase 2 = "partner registration, login, profile, secure uploads, reviewer workflow, notifications".

## Module map (app/modules/)
| Module | Responsibility |
|---|---|
| `auth` | users, invitations / reset tokens, sessions, password hashing, lockout, auth dependencies |
| `organizations` | partner organization, membership, profile fields, completion, revision history |
| `partner_documents` | versioned private documents, review status, authorised download |
| `applications` | portal applications, submissions, state machine (`transitions.py`), status history |
| `reviews` | eligibility verifications, internal notes, document review, reviewer API |
| `messaging` | information requests and partner responses |
Reused from Phase 1: storage adapters (+`get`), `documents.files.validate_upload`, notification outbox / dispatch / templates, `activities` audit table,
rate limiter, error envelope, request IDs, idempotent patterns.

## Authentication design
- Opaque random tokens (256-bit, `secrets.token_urlsafe`), stored only as SHA-256 hashes. No JWT: instant revocation, no signing-key risk, no new dependency.
- `auth_sessions`: one row per login holding current access hash + refresh hash. Refresh **rotates** both; presenting the previous refresh token again
  (replay) revokes the whole session. Access TTL `ACCESS_TOKEN_EXPIRE_MINUTES`, refresh TTL `REFRESH_TOKEN_EXPIRE_MINUTES` (existing settings).
- Every request re-reads the user: deactivated/locked users and revoked or expired sessions fail immediately.
- Passwords: Argon2id via `argon2-cffi` (only new dependency; stdlib has no Argon2; hash parameters live in the hash string). Min length 12.
- Login: generic `INVALID_CREDENTIALS` for unknown email, wrong password, locked or inactive account; dummy hash verify for unknown emails (timing).
  Lockout after `LOGIN_MAX_FAILURES` (5) for `LOGIN_LOCKOUT_MINUTES` (15). IP rate limit via existing limiter.
- One-time tokens (`auth_tokens`: invitation, password_reset): random, hashed, single use (atomic `UPDATE ... WHERE used_at IS NULL`), expiring
  (invitation 7 days, reset 1 hour). Reset request always returns 202 with the same body. Reset confirmation revokes all sessions.
- Token links are emailed through the outbox; the plaintext token is scrubbed from the outbox row after the send attempt completes.
- Staff (reviewer) accounts are created only by script `scripts/create_staff_user.py` (no public path). Staff and partner users share `users`
  but are separated by `user_type`; every route declares who may call it.

### Business decisions made safely / pending
1. **Account creation**: PRD lists "partner registration" in Phase 2 but does not say self-service or invitation. Implemented **invitation-only**
   (a super_administrator issues an invitation bound to an organization; accepting sets the password and activates the account). Self-registration is not built.
   `BUSINESS DECISION REQUIRED`.
2. **Email verification**: accepting an emailed invitation proves control of the address; no separate verification flow. PRD silent.
3. **MFA**: PRD requires MFA for privileged users and suggests it for partners. Implemented as TOTP (`auth/mfa.py`): secret encrypted with Fernet (key derived from `SECRET_KEY`; new dependency `cryptography`),
   replay-proof time steps, 8 hashed single-use recovery codes, shared lockout. Staff sessions are limited until verified (`STAFF_MFA_REQUIRED`, mandatory in production); partners may opt in. Migration 0007. Implemented, tests written but not yet executed.
4. **Multiple users per organization**: model supports it (`partner_memberships`); no self-service member management (PRD only says "authorized contact").
   One active organization per user.
5. **Who assigns reviewers**: super_administrator only (Phase 3 lead assignment is out of scope). Reviewers see only applications assigned to them.
6. **One non-terminal application per organization** (partial unique index): technical guard against duplicate submissions; business rule unconfirmed.
7. **Statuses**: PRD defines six evaluation stages, not "approved". Terminal outcomes are `rejected` and `withdrawn`; acceptance is expressed by moving to
   `pilot_onboarding` / `scale_up`. Whether an explicit "approved" status is wanted is `BUSINESS DECISION REQUIRED`.
8. **Retention / deletion**: removal is a soft delete; blobs and rows are kept. No retention period is invented (`retention_date` stays null).
9. **Malware scanning**: not configured. Versions stay `quarantined`; no claim of scanning.

## Application state machine (proposed; centralised in `applications/transitions.py`)
Statuses: `draft`, `submitted`, `eligibility_verification`, `capability_review`, `commercial_legal_review`, `pilot_onboarding`, `scale_up`,
`information_requested`, `rejected`, `withdrawn`.

| From | To | Actor | Preconditions | Side effects |
|---|---|---|---|---|
| draft | submitted | partner | profile complete; 7 required document categories present, none rejected; creates submission snapshot | notify partner + reviewers; audit |
| information_requested | resume_status (submitted/stage) | partner | all open information requests answered; new submission snapshot | notify; audit |
| submitted | eligibility_verification | reviewer (assigned) | assigned reviewer | audit |
| eligibility_verification | capability_review | reviewer | >=1 eligibility verification recorded | notify partner (status) |
| capability_review | commercial_legal_review | reviewer | - | notify |
| commercial_legal_review | pilot_onboarding | reviewer | decision reason | notify; decision audit |
| pilot_onboarding | scale_up | reviewer | decision reason | notify |
| submitted / any review stage | information_requested | reviewer | creates information request message; stores `resume_status` | notify partner |
| any review stage / submitted | rejected | reviewer | decision reason | notify; decision audit |
| draft / submitted / information_requested / review stages | withdrawn | partner | not terminal | notify reviewers |
Terminal: `rejected`, `withdrawn`. Any other transition raises `INVALID_TRANSITION` (409). Partners can never set a status directly; they invoke
named actions (submit, resubmit, withdraw). Each transition writes `application_status_history` and an `activities` audit event in the same transaction.
Row-level `SELECT ... FOR UPDATE` on the application serialises concurrent transitions.

## Eligibility verification
Append-only human records (`eligibility_verifications`): verified operating years, personnel, annual turnover (INR crore), outcome chosen by the
reviewer, exception text, notes, supporting document version IDs, reviewer, timestamp. The code **contains no thresholds** and never derives an outcome;
the proposed 3 years / 50 personnel / INR 2 crore remain reviewer guidance pending business approval.

## Authorization
`require_partner` resolves token -> session -> active user -> active membership -> organization id. Every partner query filters by that organization id;
objects of other organizations return **404** (no existence leak). `require_staff(roles)` for reviewer routes; reviewers additionally need
`assigned_reviewer_id == user.id` for every application-scoped action and document access. Deny by default; internal notes live in a table that no partner route reads.

## Audit
`activities` is extended (additive) with `actor_user_id`, `organization_id`, `request_id`; actor types gain `partner`, `reviewer`. A database trigger rejects
`UPDATE` and `DELETE` on `activities`. `meta` carries field names / status codes only - never passwords, tokens, document contents or free-text notes.

## Notifications
Outbox reuse: new template keys (invitation, password reset, application submitted, information requested, partner response received, status changed,
decision). Dedupe keys include an event id. Console backend remains default; Brevo untested.
