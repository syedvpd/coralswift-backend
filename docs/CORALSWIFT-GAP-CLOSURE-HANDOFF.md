# CoralSwift gap closure - handoff (updated 2026-11-11)

State: branch `claude/coralswift-backend-requirements-26403a`, HEAD `6ad57a7`, **nothing committed, pushed or deployed**. Migrations `0016`-`0018` exist locally and were applied only to the local disposable test database (`localhost:5433`, `coralswift_p2_test`). No remote DB was touched. Owner authorised implementing the previously PRD-excluded features on 2026-11-11.

## How to run the gates (Windows, Git Bash)
```
PY=/c/Users/ABC/Desktop/coralswift-backend/.venv/Scripts/python.exe
export TEST_DATABASE_URL=$($PY -c "from dotenv import dotenv_values;print(dotenv_values('C:/Users/ABC/Desktop/coralswift-backend/.env')['TEST_DATABASE_URL'])") SECRET_KEY=ci-only-secret-key-not-for-deployment-0000
$PY -m ruff check . && $PY -m ruff format --check . && $PY -m mypy && $PY -m pytest -q -p no:cacheprovider
$PY scripts/alembic_test_db.py check            # no drift
PYTHONPATH=. $PY "$TEMP/gen.py" "$TEMP/perm.json"  # OpenAPI: json.dumps(indent=1, sort_keys=True) of create_app(Settings(_env_file=None, app_env="development",...)).openapi()
```
Docker Desktop must be running (container `coralswift-backend-db-1`, port 5433).

## Done in this gap-closure pass (code + tests)
| Batch | Feature | Code | Test |
|---|---|---|---|
| 0 | staff user get/patch/activity, application workload, `ACCOUNT_LOCKED`, `scan_status` | admin/router.py, reviews/router.py, documents/scan.py | test_requirements_batch.py |
| 1 | projects, org inbox, discussions/meetings/follow-ups (partner + staff) | app/modules/collaboration/ (migration 0016) | test_collaboration.py |
| 2 | team management, notification preferences (applied in `queue_notification`), account closure request, onboarding checklist, `MeOut.permissions` | app/modules/partner_team/, app/modules/onboarding/, notifications/preferences.py (0017) | test_team_prefs_onboarding.py |
| 3 | review checklist/scores, exceptions, stage owners, reopen, assessment outcomes, enquiry reply, staff document upload/replace, `replacement_requested`, template version history | app/modules/review_workflow/, admin/ops_router.py (0018) | test_review_workflow.py |

## Next unfinished task (do in this order)
1. **Batch 4a - audit**: add nullable `ip_address`, `user_agent`, `outcome` columns to `activities` (migration 0019; table is append-only at DB level, check the trigger first), fill them in `log_activity` from a request-context var (see `request_id_var` in `app/core/middleware.py`), expose in `AuditRow` and CSV. Retention of IP/UA is decision D36 - store but mark in the tracker.
2. **Batch 4b - CMS**: new `ContentType` values `hero`, `service`, `industry`, `navigation` (check `ck_content_items_*` constraints), media library table + `POST /admin/media` upload (reuse `validate_upload`, images only, public bucket decision D29 -> store privately, serve through an authenticated admin route only), `updated_by` on content rows, rich-text flag `body_format`.
3. **Batch 4c - reports**: `assignee_id` and `category` filters on `/admin/reports/kpis` (`app/modules/admin/ops_router.py::kpis`), application turnaround metric from `application_status_history`.
4. **Batch 4d - bounces**: `POST /webhooks/email` guarded by a shared-secret header setting (refuse when unset), set `delivery_status` bounced (needs `DeliveryStatus.BOUNCED` + check constraint migration).
5. **Batch 5**: performance foundation (`/reviewer/organizations/{id}/performance` entries with staff-supplied indicator key/label/definition/value, publish flag; `/partner/performance/*` read published only + CSV), partner notification `description`/`link` fields, information-request `due_date`, `StaffOut.status` enum, `retention_until` alias + auditable purge endpoint, CORS default for `http://localhost:5173` in development only.
6. Final: regenerate `docs/api/openapi.json` + `docs/api/role-permission-matrix.md`, update `docs/frontend-backend-requirements-tracker.md` (rows still say OUT OF APPROVED SCOPE for items now built), full gates, report.

## Decisions to ask the owner (numbered, defaults not applied)
See `docs/business-decisions-required.md` D1-D39 plus the new ones appended at the end of that file during this pass.

## Update (end of pass 2)
Batches 4 and 5 are done: audit origin/outcome (0019), CMS blocks + media (0020), extended profile (0021), performance (0022), bounced status (0023), KPI filters/turnaround, purge endpoint, bounce webhook. Tracker rows updated. Remaining, in order:
1. Final gate run and OpenAPI/matrix regeneration (done once; redo after any further code change).
2. Owner answers: D1-D45 in `docs/business-decisions-required.md`.
3. Not built by decision: secrets API (D40), PDF/Excel (D41), "not activated" login error (D37), HttpOnly cookie sessions (D1), malware scanner (D33), security-policy write (D36).
4. External, cannot be done locally: CORS origins on Render (D32), test accounts + mailbox (D31), Brevo + SPF/DKIM/DMARC, Turnstile live check, bucket privacy check, remote migrations 0016-0023 (need your explicit approval), republishing the deployed OpenAPI.

## Update (final owner round)
Done: staff team list, notification description/related_record/link, information-request `due_date`, `decision_explanation`, D9 pass/fail checklist (migration 0024), D15 reply gate, D4 purge gate, D42, D45 BDM read scope, privacy SLA settings, KPI/turnaround tests. Full suite 367 passed. Next: only owner answers listed at the end of `docs/business-decisions-required.md` and the external items in `docs/EXTERNAL-CONFIGURATION-CHECKLIST.md`. Nothing committed, deployed, or applied remotely.
