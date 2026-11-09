# Phase 1 Testing Strategy

Tests never touch the development database. `TEST_DATABASE_URL` must point to a disposable database whose name ends in `_test` (local Docker `coralswift_test`); pytest aborts otherwise. The session fixture runs `alembic upgrade head` on that database (upgrade only).

Isolation: API/integration tests share one connection inside an outer transaction; service commits become savepoints and everything is rolled back after each test. Two tests (concurrent idempotency claim, concurrent reference numbers) use real committed connections and remove only their own rows.

External systems are replaced by fakes: `InMemoryStorage`, `RecordingEmail`, `httpx.MockTransport` for Brevo, a stub S3 client. **Real S3 and real Brevo delivery are not exercised by the automated suite.**

| Area | File |
|---|---|
| Contact | `tests/api/test_contact.py` |
| Project / partner / strategic | `tests/api/test_project_partner_strategic.py` |
| Documents, status lookup, rate limit, bot hook, body size | `tests/api/test_documents_status_security.py` |
| Idempotency, concurrency, reference uniqueness | `tests/api/test_idempotency.py` |
| Notifications (templates, failure, retry, dedupe) | `tests/api/test_notifications.py` |
| Adapters (Brevo, local/S3 storage, file helpers) | `tests/unit/test_adapters.py` |
| Phase 0 regression | `tests/api/test_app.py`, `test_health.py`, `tests/unit/*`, `tests/integration/*` |

Gate: `ruff check . && ruff format --check . && mypy && pytest -q`.
