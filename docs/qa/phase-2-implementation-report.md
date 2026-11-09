# Phase 2 Implementation Report (2026-11-09)

Phase 1 acceptance decision is unchanged: **FAIL - PHASE 1 NOT ACCEPTED**. Phase 2 was started on explicit user instruction.

## Module status
| Module | Status | Evidence / gaps |
|---|---|---|
| 2.1 Authentication | VERIFIED (MFA missing) | Argon2id, opaque hashed tokens, refresh rotation + replay revoke, lockout, reset, invitation-only accounts. **MFA not implemented** (PRD requires it for reviewers). Account creation model = BUSINESS DECISION REQUIRED |
| 2.2 Organization / profile | VERIFIED | profile, completion, revision history, optimistic version, no merging |
| 2.3 Documents | VERIFIED (scanner BLOCKED) | versions, private storage, authorised audited download, soft delete. No malware scanner, no retention policy, expiry only stored |
| 2.4 Applications | VERIFIED | central state machine, snapshots, one-open-application guard (assumption) |
| 2.5 Eligibility | VERIFIED | human append-only records; thresholds not coded |
| 2.6 Reviewer workflow | VERIFIED | assigned-only access; assignment by super admin (decision pending) |
| 2.7 Communication | VERIFIED | information request / response / resubmit; notes separate |
| 2.8 Audit | VERIFIED | `activities` extended, DB trigger blocks UPDATE/DELETE, request IDs |
| Notifications | IMPLEMENTED | outbox + 7 templates + dedupe + link scrubbing verified with fakes; real Brevo untested |

## Database
Migrations (additive): 0004 users/auth_tokens/auth_sessions/organizations/memberships/profile revisions + activities columns + widened CHECKs + append-only trigger;
0005 partner documents + versions; 0006 portal applications, submissions, status history, eligibility, notes, messages + `portal_application_seq`.
Applied to the local test databases and, on the user's instruction, to the Supabase development database (`alembic current` = 0006, `alembic check` = no drift).
Not exercised: the running application against Supabase; staff accounts do not yet exist there (create with `scripts/create_staff_user.py`).

## Evidence (local isolated DB)
`ruff check .` pass; `ruff format --check .` 151 files already formatted; `mypy` success (131 files); `pytest -q` **176 passed, 0 failed** (one deprecation warning from Starlette/httpx).
Defects found and fixed during testing: dedicated-transition guard blocked information requests; outdated Phase 1 test assertions (template keys, "document" path filter);
test pollution from committed concurrency data (moved to a separate disposable database); `.env` `TEST_DATABASE_URL` now points to `coralswift_p2_test` because `coralswift_test` held committed leftovers (left untouched, not dropped).

## Open items
MFA; malware scanning; retention policy; Brevo credentials/DNS; real S3 behaviour and bucket privacy; reviewer-assignment authority; invitation vs self-registration; whether an explicit "approved" status exists;
per-pathway threshold applicability; live-server sweep of Phase 2 routes; reviewer assignment notification (not sent); document expiry enforcement; Phase 1 remains not accepted.

## Scope check
No Phase 3 admin dashboard, reporting, CSV or global user admin; no Phase 4 directory, scoring or automation; no payments or e-signature.
