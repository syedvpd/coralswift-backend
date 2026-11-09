# ADR-001: Backend architecture

- Status: Accepted (Phase 0)
- Date: 2026-11-09
- Source of scope: Coral Swift PRD v2.0 (sections 16-19, 23)

## Decision

Build the backend as a **modular monolith** in **FastAPI**, persisted in **PostgreSQL** through **SQLAlchemy 2.0**,
with schema managed by **Alembic**. Use synchronous database access (psycopg 3).

## Why it fits Coral Swift

- **Modular monolith**: the PRD's four phases add modules (enquiries, partner portal, admin, ecosystem) that share users,
  documents, audit and notifications. One deployable keeps transactions, auditing and local development simple for a small team.
  Module boundaries keep a later split possible. Microservices would add cost with no current need.
- **FastAPI**: typed request/response models, automatic OpenAPI (the PRD asks for documented REST APIs), dependency
  injection for auth/RBAC later. Matches the PRD's "Node or equivalent maintained backend" recommendation.
- **PostgreSQL**: PRD names it. Relational constraints suit workflow states, eligibility evidence, reviews and audit data.
- **SQLAlchemy 2.0**: mature typed ORM; explicit transactions; works with Alembic.
- **Alembic**: reviewed, versioned migrations. The PRD requires controlled schema change and retention/audit rigour.
- **Sync DB access**: workload is form-driven CRUD, not high-concurrency I/O. Sync is simpler to write, test and debug.
  FastAPI runs sync routes in a threadpool. Revisit only if profiling shows a need.

## Consequences

- Background work (email, malware scan, retention jobs) will need a worker. Redis/Celery is prepared in Compose (profile `jobs`) but not wired.
- All modules share one database; module ownership of tables is by convention and review.
- Auth, RBAC, file storage and email are deliberately absent from Phase 0 and arrive with the phases that need them.
- PRD open decisions (hosting, email/CRM/storage vendors, legal entity, retention policy) are not assumed by this ADR.
