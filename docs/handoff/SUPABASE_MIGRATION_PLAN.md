# Supabase development migration plan

Status verified from current instructions on 2026-11-10: **no remote operation is authorized in this task**. The intended development project ref is `zibfzlwzaecapfrgjret`; the connected Supabase account cannot access it, and no verified backup is available. Do not inspect/apply through another project, change credentials, or contact production.

## Repository migration state

- Alembic repository head is `0012` (`20261110_0012_scheduled_content_publication.py`).
- Supabase dev is reported to be at `0010`; this target state remains unverified. Re-check the exact project and migration history only after verified access is available.
- `0011` has already been applied to local disposable test databases in the previous session. `0012` is new in this working tree and is not applied to any database. The current local PostgreSQL/Docker daemon is unavailable, so neither a fresh-database migration check nor runtime behavior could be verified in this session.

## Impact of 0011

`0011` is additive:

- `auth_tokens.revoked_at`: nullable timestamp used to distinguish revoked/superseded tokens.
- `notifications.read_at`: nullable timestamp used for notification read state.
- `enquiry_followups.kind`: non-null text with default `follow_up` and a check allowing `note`, `follow_up`, `communication`.
- `enquiry_followups.assignee_id`: nullable FK to `users.id` (`ON DELETE RESTRICT`) plus index.
- `enquiry_followups.cancelled_at`: nullable timestamp.

Existing rows are preserved; the `kind` default populates existing follow-ups. The code at repository head selects/writes these columns, so deploying that code against a database still at `0010` can break token, notification and follow-up flows. Downgrade removes the new columns and loses values recorded in them; do not use downgrade as a rollback after new data is written. No destructive table rewrite is intended by the upgrade, but index/FK/check creation and the database's size/lock behavior must be checked against the actual target before execution.

## Impact of 0012

`0012` is additive:

- `content_items.scheduled_publish_at`: nullable timestamp for approved content scheduled to publish in the future.
- `ix_content_status_scheduled`: index on `(status, scheduled_publish_at)` used by the maintenance job.

Existing content remains unchanged. The maintenance job only publishes approved rows whose schedule is due and whose linked claims still pass the existing publication gate. Downgrade drops the index and timestamp; any scheduled publication times are lost. Since code now reads this column, a deployment containing that code requires migration `0012` first.

## Preconditions before any remote migration

1. Obtain access to the exact Supabase project and independently verify its project ref matches `zibfzlwzaecapfrgjret` and its environment is development.
2. Verify a recent restorable backup/PITR point for that exact project, record its timestamp and retention window, and verify the owner/operator can restore it. A backup file's existence alone is insufficient.
3. Read the live migration history and schema state without changing them; confirm the target is at `0010` or identify every pending repo migration. Stop if the database state diverges from the repository history.
4. Review the exact SQL Alembic will execute, including names and existing constraints/indexes; capture pre-migration health and row counts for the affected tables without exposing records or secrets.
5. Schedule a low-traffic window, ensure the application deployment does not race schema changes, and prepare a tested forward-fix/restore procedure. Because downgrade drops data, prefer restoring the verified backup if a rollback is necessary.

## Execution and verification after those preconditions

Only after separate explicit approval for the exact verified target: apply pending migrations in order (`0011`, then `0012` if both are absent); record each revision and result. Verify Alembic history/head, required columns/default/check/FK/index, table row counts, application health, token/notification/follow-up/invitation flows, and the scheduled-content job in dry run before enabling it. Production remains out of scope.


## Correction (2026-11-10, verified by Claude Code after the owner approved)
The statements above that Supabase was at `0010`, the project was not accessible and no backup existed are **outdated**. Verified read-only against the configured development project (`postgres.zibfzlwzaecapfrgjret` via the session pooler, same project ref as `S3_ENDPOINT_URL`): the database had 0 enquiries and 0 users and was at `0010`. A `pg_dump` of the `public` schema (38 tables) was taken to `C:\Users\ABC\Desktop\coralswift-backups\supabase-dev-public-before-0011-20261110T085302Z.sql`, then `alembic upgrade head` applied **`0011` and `0012`**. Result: revision `0012`, `alembic check` clean, all five `0011` columns present, business row counts unchanged. Nothing is pending on the development database; production was never touched. The `0012` file is untracked in Git: do not edit it, and keep it (Supabase records revision `0012`).

## Re-verification and pending migrations (2026-11-10, Claude Code)
Read-only check against `postgres.zibfzlwzaecapfrgjret` (pooler): database `postgres`, recorded revision `0012`, `alembic heads` = `0012` at that time, `alembic check` clean, columns from `0011` and `0012` present. The repository head is now **`0015`**. Pending for Supabase dev and **not applied**: `0013` (content SEO columns, privacy-request verification columns, `document_requests` table), `0014` (`users.phone`), `0015` (`staff_notifications` table). All three are additive. Before applying: explicit owner approval, a fresh `pg_dump` backup, and target confirmation. Until applied, deploying the current code to the Render dev service will fail on any query touching these columns (privacy requests, content reads, users, notifications feed, document requests) - do not deploy it before the migration. The `0012`-`0015` migration files are uncommitted; keep them unedited.
