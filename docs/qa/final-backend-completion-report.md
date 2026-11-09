# Final Backend Completion Report (2026-11-09)

## Status
**PHASES 0-3 BACKEND: IMPLEMENTED AND AUTOMATED-TESTED LOCALLY. NOT PRODUCTION-READY.**
Production readiness is not claimed. Open items below need provider credentials, business decisions or operations setup. Phase 1 acceptance stays **FAIL - PHASE 1 NOT ACCEPTED** (decision not re-taken). Phase 4, payments, e-signature and ERP were not built, as instructed.

## Evidence summary
| Item | Result | Source |
|---|---|---|
| pytest (local Docker Postgres) | 211 passed, 0 failed | `final-backend-test-report.md` |
| ruff / ruff format / mypy | clean (159 source files) | same |
| Alembic, local test DB | head `0010`, `alembic check` no drift | same |
| Alembic, Supabase **dev** DB | upgraded 0006 -> 0010 after backup; `alembic_version` 0010; expected tables/columns/trigger present; existing enquiry row count unchanged | `supa_migrate.py` / `supa_verify.py` output |
| Supabase backup | `public` schema dump taken before migration and restore-tested into a throw-away local DB; file in `C:\Users\ABC\Desktop\coralswift-backups\` (outside repo; contains data, do not commit) | `supa_backup.py` output |
| Storage | put/get/exists/delete round trip with dedicated `_selftest/<uuid>.pdf` objects on both buckets; test objects deleted; anonymous public URL not served (HTTP 400) | `supa_verify.py` output |
| Docker / startup | builds, non-root, `/health/live` 200, `/health/ready` 503 without DB | test report |
| Config | `.env` regrouped (values kept), `.env.example` placeholders only, Settings fields aligned, production validation tested | `test_config` |

Supabase target was positively identified as development (empty business tables, project the user designated for development) before migration. Supabase data was not used for tests.

## What was built or completed in this final cycle
- s.28 items: claims register + publication gate; enquiry routing with owner, backup owner, SLA due date, lead source; SLA escalation job; acknowledgement-time promise toggle; launch-readiness check and public contact config (confirmed values only); project categories and partner criteria catalogue endpoints (labelled illustrative/proposed); failed-notification visibility and retry; privacy-deletion executor (anonymisation); MFA recovery-code regeneration.
- Migration 0010; maintenance job `scripts/run_maintenance.py`; Render blueprint; hardened Dockerfile; CI workflow; env cleanup.
- Four defects found by tests and fixed (see test report).
- Docs: master register rewritten, test report, this report, Render readiness.

## Not verified / not done
- Brevo delivery, SPF/DKIM/DMARC: no key or domain. Console backend only; adapter tested with a mock.
- CAPTCHA, calendar integration, malware scanning: no provider. Uploads stay quarantined.
- Full journey tests against Supabase: not run (by design, tests use only the local test DB). Only schema checks, the live smoke run and the storage round trip hit Supabase.
- GitHub CI run, Render deploy, load/performance, accessibility/SEO (frontend): not run.
- Phase 1 re-acceptance review: not performed.
- Retention purge and privacy deletion: logic tested; periods and policy not approved, so purge stays inert until configured.

## Business decisions still needed
Queue owners / backup owners / SLA hours / escalation emails; contact details; privacy notice text and version; retention periods; invitation-only vs self-registration; who may assign reviewers; explicit "approved" application status; threshold applicability per pathway; BDM access to strategic enquiries (default none); content approver role (default super administrator); incident owner; hosting and monitoring.

## Risks
- DB password and S3 keys were pasted into chat. Rotate before production.
- Enum-widening migrations 0009/0010 cannot be downgraded once rows use new values. Restore from backup instead.
- Code is not in git; no history or remote CI evidence exists.
- Test harness nests sessions in one transaction; background-task commits are asserted by direct calls (documented in the test report).

## Noticed, not changed
Older phase reports (`phase-1-verification-report.md`, `phase-2-*`, `phase-3-*`, `phase-0-to-3-completion-gap-report.md`) still describe migrations 0007-0009 as unapplied to Supabase and s.28 as excluded. They are historical; this report and the master register supersede them.


## Final audit addendum (2026-11-09)
Scope: evidence audit of the current tree. Checks rerun in this audit: ruff, format, mypy, full pytest (**214 passed**), `alembic check` on the local test DB (head 0010), app import. Not rerun: Docker, live server, Supabase, storage (earlier results stand, dated above). Matrix with per-requirement status: `docs/requirements/prd-master-register.md` (legend maps its labels to the five audit labels). Overall: **Phases 0-3 backend implemented; mandatory coverage complete in code, incomplete in verification and blocked on external/business items.**

Change during the audit: Cloudflare Turnstile verifier (chosen as the simplest provider: free, no user puzzle, one secret key on the backend). Inactive until `TURNSTILE_SECRET_KEY` is set. Mocked-transport tests only; the real Cloudflare endpoint was not called.

Maintenance script: `python scripts/run_maintenance.py` has no arguments and no `--help`; any run executes the jobs. README corrected.

### Final blocker register
**Code:** none known open for mandatory Phase 0-3 scope. Frontend must send the Turnstile token in `X-Bot-Token`.
**Business decisions:** queue owners, backup owners, SLA hours, escalation emails; contact details; privacy notice text/version; retention periods; invitation vs self-registration; reviewer-assignment authority; explicit "approved" status; threshold applicability per pathway; BDM access to strategic enquiries; content approver role; incident owner; whether quarantine-only uploads are formally accepted or a scanner is chosen.
**External / deployment (not configured or not verified):**
- Brevo: key, verified sender domain, SPF/DKIM/DMARC; one internal test mail. Owner will supply keys on 2026-11-10 (user said "tomorrow").
- Cloudflare Turnstile: site key (frontend) and secret key, then one real verification.
- Calendar integration; malware scanning (uploads stay `quarantined`).
- Supabase full-journey tests, GitHub CI run, Render deployment: not done.
- Supabase bucket privacy: needs owner confirmation in the dashboard (anonymous request returned HTTP 400, which is not proof of the setting).
- Production TLS, proxy rate limiting, request-size limit: verify on the deployed environment.
- Monitoring, error tracking, backups policy for production.
- Project directory has no Git history (still true); git was not initialised.

### Safety reminders
- The development DB password and S3 keys were pasted in chat: **rotate them**; production must use separate credentials and a newly generated `SECRET_KEY`.
- Migrations 0009 and 0010 widen enum CHECKs; their downgrades fail once rows use the new values. Restore from a verified backup instead of downgrading.
- No secrets are written in any report. `.env` is git-ignored.

### Corrections addendum (2026-11-09, supersedes the counts above)
- **Latest local verification: 219 passed**, ruff/format/mypy clean, `alembic check` clean on the local test DB (details: `final-backend-test-report.md`, "Corrections rerun"). The 211 and 214 counts above are earlier states of the tree. Docker, Supabase and storage results remain the earlier run's evidence and were not repeated.
- **Turnstile configuration:** `CAPTCHA_ENABLED` defaults to `false` (explicit local/dev opt-out). Enabling it without `TURNSTILE_SECRET_KEY` fails settings validation in every environment. Production refuses to start unless `CAPTCHA_ENABLED=true` and the secret is set, so a missing secret cannot silently bypass the check. When enabled, a missing, invalid or expired token returns 403 `BOT_CHECK_FAILED` (mocked Cloudflare). `.env.example`, `render.yaml`, `config.py` and the readiness doc agree. Never run against real Cloudflare. **Consequence:** the Render service will not boot until the Turnstile secret is provided.
- **Maintenance:** `python scripts/run_maintenance.py --dry-run` counts affected rows in a READ ONLY transaction and changes nothing. Real run and dry-run commands, jobs, target and backup rules are in `README.md`. The dry run was not executed against Supabase.
- **Requirement found missing and added:** portal adoption KPI (`GET /admin/reports/kpis`, super administrator). Register: `docs/requirements/prd-master-register.md` (row-by-row, 100+ rows).

### Release-preparation addendum (2026-11-09)
- **Git:** repository initialised locally; baseline commit `c9ea506` on `main`; no remote created, nothing pushed. Author identity on the commit is a placeholder (`Coral Swift Dev`, the account email); amend before publishing if a different author is wanted.
- **Secret safety:** scan found no live Supabase password, S3 key or `SECRET_KEY` in tracked files; `.env`, `var/`, dumps, keys and caches are ignored. The Supabase DB password and S3 keys that were pasted in chat **must still be rotated** (procedure: `docs/deployment/staging-release-checklist.md`, section C). Rotation is not done.
- **CI:** workflow now also validates migrations on a fresh database, builds the app, checks `run_maintenance.py --help`, and has a Docker build / non-root job. It uses no secrets and an ephemeral Postgres. **Never run on GitHub.**
- **Staging:** `render.staging.yaml` and the `staging` app profile (recipient allow-list required, strict production-level validation) are ready; nothing deployed.
- **Latest local verification:** 222 passed, ruff/format/mypy clean. Phase 1 remains **FAIL - NOT ACCEPTED**; backend completion is not production readiness.
- **Owner decisions:** `docs/requirements/business-decision-register.md` (18 items, all OPEN).
