# Architecture Overview

**Status:** Phase 0 complete (previously verified). Phase 1 implemented, **verification pending** (see README for what has
and has not been re-run). Phase 2 (Partner Portal) must not start until Phase 1 passes its verification and acceptance gates.

Modular monolith: one FastAPI deployable, one PostgreSQL database, feature code split into modules.

## Layers

| Layer | Location | Responsibility |
|---|---|---|
| Entry / wiring | `app/main.py` | `create_app(settings)` builds engine, middleware, handlers, routers |
| API | `app/api/v1/router.py`, `app/modules/<m>/router.py` | HTTP only: parse, call service, shape response. No business logic |
| Service | `app/modules/<m>/service.py` | Business rules, transactions (commit here) |
| Persistence | `app/modules/<m>/models.py`, `app/database/` | SQLAlchemy models, session, `Base`, mixins |
| Core | `app/core/` | Config, logging, exceptions + handlers, middleware, security helpers |
| Common | `app/common/` | Response envelope, pagination, tiny utilities |
| Integrations | `app/integrations/` | Adapters for external vendors (email, storage, CRM); none yet |

## Request lifecycle

1. `RequestContextMiddleware` assigns/validates `X-Request-ID`, starts timer.
2. `SecurityHeadersMiddleware`, then CORS, then TrustedHost.
3. Router -> dependencies (`get_db` opens one session per request, closes it after).
4. Service does the work and commits; the route returns `ok(...)` (`ApiResponse` envelope).
5. Any exception goes to a central handler -> error envelope; internals are logged, never returned.
6. Middleware logs one JSON access line: method, path, status, duration, request id.

## Database

Synchronous SQLAlchemy 2.0 with psycopg 3; pool 5 + 10 overflow, `pool_pre_ping`, UTC session timezone.
Engine and sessionmaker live on `app.state` (no import-time globals), so tests build their own.
`Base` carries a naming convention; `UUIDPrimaryKeyMixin` and `TimestampMixin` are provided for future tables.
Schema changes only through Alembic (`migrations/`), which reads the URL from app settings.

## Dependency injection

FastAPI `Depends`: `DbSession` (`app/database/dependencies.py`), `get_settings`, `PageDep`.
Tests replace behaviour via `app.dependency_overrides` or by constructing `create_app(test_settings)`.

## Adding a module (Phase 1+)

1. `app/modules/<name>/{models,schemas,service,router}.py`.
2. Import its models in `migrations/env.py` so autogenerate sees them; generate and review a migration.
3. `api_router.include_router(<name>.router, prefix="/<name>")` in `app/api/v1/router.py`.
4. Raise `AppError` subclasses from services; never build error JSON by hand.
5. Add unit tests for rules, API tests through the HTTP layer, and an integration test for queries.

## Phase 1 modules

`enquiries` (company/contact/enquiry/activity, reference + status lookup, shared submit pipeline), `projects`, `partners`,
`strategic`, `documents` (upload, validation, attach), `notifications` (outbox, templates, dispatch). Adapters in
`app/integrations/` (`storage`, `email`, `botcheck`) are injected through `create_app(...)`. Submit pipeline:
rate-limit/bot guard -> idempotency claim -> one transaction (rows + outbox + stored response) -> commit -> background dispatch.

Integration state: storage adapters (local, S3-compatible) and email adapters (console, Brevo) are implemented but the
real S3 and Brevo calls are untested; the active email backend is `console` (nothing is delivered). Uploads are stored
`quarantined`: no malware scanner exists. Meeting requests are not built (need an approved calendar integration).
Business-decision dependencies: queue owners/addresses, SLA wording, privacy notice, partner threshold bands.

## Phase 2 modules (partner portal)

`auth` (users, sessions, tokens), `organizations` (profile, memberships, revisions), `partner_documents`, `applications` (state machine in `transitions.py`),
`reviews` (reviewer API), `messaging`. Details: `phase-2-architecture.md`, `phase-2-data-model.md`, `docs/api/phase-2-api-contract.md`.
Migrations 0004-0006 are applied to the Supabase development database; MFA (TOTP) is implemented in code with migration 0007 pending, untested.

## Auth (Phase 2: implemented, see above; MFA pending)

JWT, Argon2 hashing, RBAC and signed document access land in Phases 2-3. `app/core/security.py` is the only place for those helpers.
Settings already carry `SECRET_KEY` and token lifetimes.
