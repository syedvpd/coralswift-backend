# CoralSwift Backend

FastAPI modular monolith for the Coral Swift website, partner portal and admin platform (PRD v2.0).

## Project status (2026-11-09)

| Phase | Status |
|---|---|
| 0 - Foundation | Implemented; covered by the final automated run. |
| 1 - Public website backend | Implemented. Acceptance decision still **FAIL - not accepted** (`docs/qa/phase-1-verification-report.md`): real Brevo, CAPTCHA, malware scanning and business inputs open. |
| 2 - Partner portal | Implemented incl. MFA; covered by the final automated run. |
| 3 - Admin platform + PRD s.28 items | Implemented; covered by the final automated run. |
| 4 - Extended ecosystem | Not started (excluded). |

**Latest local run (2026-11-09): 219 tests passed, ruff/format/mypy clean, `alembic check` clean. Docker, Supabase and storage checks are from the earlier 211-test run.** Migration head is **0010**: applied to the local test DB and the Supabase **dev** DB (backed up first). Not applied to any production DB. **Not production-ready:** Brevo, CAPTCHA, calendar, malware scanning and business decisions are open, and nothing is deployed.
Detail: `docs/requirements/prd-master-register.md`, `docs/qa/final-backend-completion-report.md`, `docs/qa/final-backend-test-report.md`, `docs/deployment/render-deployment-readiness.md`.

## Stack

Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (sync, psycopg 3), PostgreSQL, Alembic, Argon2id, Fernet (MFA secret), Pytest, Ruff, MyPy, Docker Compose.

## Local development

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt
cp .env.example .env            # then fill in; never commit .env
docker compose up -d db         # local PostgreSQL (host port 5433)
.venv/Scripts/uvicorn app.main:create_app --factory --reload
```

Docs: http://localhost:8000/docs (off when `APP_ENV=production`).

## Environments

- `DATABASE_URL`: development database (Supabase pooler or local Docker; URL-encode special characters).
- `TEST_DATABASE_URL`: disposable local `*_test` database. Pytest refuses anything else.
- Storage: `STORAGE_BACKEND=local|s3` + `S3_*`. Email: `EMAIL_BACKEND=console|brevo` + `BREVO_API_KEY`, `EMAIL_SENDER_ADDRESS` (console = nothing delivered).
- Staff MFA is required (`STAFF_MFA_REQUIRED`, mandatory in production).

## Migrations

Never run alembic against a shared database by accident. For the local test database use the guarded helper:

```bash
python scripts/alembic_test_db.py upgrade head
python scripts/alembic_test_db.py check
```

Applying to Supabase needs explicit approval and a target check (`alembic current`).

## Staff accounts and scheduled jobs

```bash
STAFF_PASSWORD=... python scripts/create_staff_user.py --email a@b.com --name "Name" --role super_administrator
```

Maintenance: `scripts/run_maintenance.py`, run from the repo root (it reads `.env` from the current directory). The only option is `--dry-run`.

| Command | Effect |
|---|---|
| `python scripts/run_maintenance.py --dry-run` | **Safe preview.** Counts what each job would act on, inside a READ ONLY transaction. Deletes, changes, queues and sends nothing, and builds no storage or email client. |
| `python scripts/run_maintenance.py` | **Real run.** Executes all jobs below. |
| `docker run --rm --env-file .env <image> python scripts/run_maintenance.py [--dry-run]` | Same, inside the image (WORKDIR `/srv`; pass the environment explicitly). |

Jobs (real run): idempotency-key cleanup; SLA escalation emails (once per overdue enquiry); document expiry reminders (needs `expiry_reminder_days`); retention purge of stored files of removed documents (needs a retention date; **deletes files from storage**); notification dispatch and retries (**sends real email** when `EMAIL_BACKEND=brevo`). Output is one result dict; exit 0.

Target: whatever `DATABASE_URL`, `STORAGE_*` and `EMAIL_*` the environment holds. Check them first; with the local `.env` that is the Supabase **development** database and its buckets. Before any real run against shared or production data: take a verified backup, get explicit authorisation, and run `--dry-run` first to read the counts (`documents_would_purge` is the retention purge). Render runs the real command as a cron job every 15 minutes (`render.yaml`).

## Checks

```bash
ruff check . && ruff format --check . && mypy && pytest -q
```

## API areas (all under `/api/v1`)

Public: `/enquiries/*`, `/documents/upload`, `/meetings`, `/newsletter/*`, `/privacy/requests`, `/content/*`.
Auth: `/auth/*` (login, refresh, MFA, reset, invitations). Partner: `/partner/*`. Reviewer: `/reviewer/*`. Admin: `/admin/*`.
Contracts: `docs/architecture/phase-1-api-contracts.md`, `docs/api/phase-2-api-contract.md`, `docs/api/phase-3-api-contract.md`.

## Docs

`docs/architecture/` (overview, per-phase architecture + data model), `docs/engineering/`, `docs/requirements/`, `docs/qa/`, `docs/decisions/`.
