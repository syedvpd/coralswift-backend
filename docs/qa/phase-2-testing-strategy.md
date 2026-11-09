# Phase 2 Testing Strategy

Tests run only against local Docker PostgreSQL (`TEST_DATABASE_URL`, name must end `_test`; currently `coralswift_p2_test`). Never against Supabase.
Concurrency tests use a second local database `<name>_conc_test` with real commits (created and migrated by the `concurrency_engine` fixture);
its rows are never deleted because `activities` is append-only, and it is separate so it cannot pollute other tests.
Storage is `InMemoryStorage`, email is `RecordingEmail`; no real S3 or Brevo calls.
`scripts/alembic_test_db.py` runs alembic only when `TEST_DATABASE_URL` is a local `*_test` database.

| Area | Files |
|---|---|
| Unit: state machine | `tests/unit/test_transitions.py` |
| Auth: invitation, login errors, lockout, expiry, logout, refresh rotation/replay, deactivation, sessions, reset abuse, log secrecy, rate limit | `tests/api/test_auth.py` |
| Organization: profile, completion, history, concurrency version, isolation, no merging | `tests/api/test_organizations.py` |
| Documents: upload validation, private storage, versions, download audit, cross-org 404, soft delete | `tests/api/test_partner_documents.py` |
| Applications: draft, completeness gate, snapshot, history, withdraw | `tests/api/test_applications.py` |
| Reviewer: assignment, workflow rules, eligibility, info request/response/resubmission, notes leakage, document review | `tests/api/test_reviewer.py` |
| Security: anonymous sweep over every partner/reviewer route, role separation, IDOR matrix, assignment limits, deactivation, field leakage | `tests/api/test_security_p2.py` |
| Audit + full journey | `tests/api/test_audit_e2e.py` |
| Concurrency: duplicate submit, duplicate open application, reviewer decision race, document replacement, notification dedupe, refresh rotation | `tests/api/test_concurrency_p2.py` |
