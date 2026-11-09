# Phases 0-3 Completion Gap Report (2026-11-09)

> **Superseded by** `final-backend-completion-report.md` and `final-backend-test-report.md` (211 tests passed, migration head 0010 on local and Supabase dev, PRD s.28 now implemented). Text below is the earlier pre-test snapshot; statements about "testing pending", "no item VERIFIED", Supabase at 0006 or s.28 excluded are out of date.

**Overall status: PHASES 0-3 IMPLEMENTATION COMPLETE - COMPREHENSIVE TESTING PENDING**, for the feasible backend scope, with the exclusions below that the user chose or that need external input. Master register: `docs/requirements/prd-master-register.md`.
Phase 1 acceptance stays **FAIL - NOT ACCEPTED**. No item is VERIFIED.

## What was added in this pass
Content CMS (draft -> review -> SA approval -> publish, versions, attachments, public search/related/sitemap), newsletter opt-in, meeting requests with staff-attested confirmation, privacy requests, notification-template management, system settings (retention, expiry reminders), profile change requests, partner notification list and enquiry history, KPI report, MFA reset, reviewer-assignment email, expiry reminders + retention purge job (`scripts/run_maintenance.py`), lead source field, CI workflow file.

## Migration state (no destructive operations were run)
0001-0006 applied to Supabase dev DB. **0007 (MFA), 0008 (follow-ups, lead owner), 0009 (content, engagement, settings, templates, change requests, purge column, widened CHECKs) are not applied to Supabase.** The application code needs all of them: run against Supabase only after approval and `alembic upgrade head` there. The local test database `coralswift_p2_test` is at 0009 with no drift reported by `alembic check`. Downgrade of 0009 fails if rows already use new enum values (intentional).
Dependency notes: 0008 requires 0007; 0009 requires 0008 and widens `ck_enquiries_enquiry_type` and `ck_notifications_template_key`.

## Excluded by the user (PRD section 28 and Phase 4)
Claims register and evidence status; publication gate and illustrative-label enforcement; contact-readiness launch gate; SLA targets, queue-owner auto-routing, escalation, out-of-office, acknowledgement promises; admin alerting on notification failures; claims-driven content governance. Phase 4 items (partner directory, scorecards, automation, CRM/calendar/ticketing integrations, collaboration workspace).
Left in place for them: manual assignment, `owner/reviewer/last_reviewed/version` fields on content, outbox retries.

## Blocked or undecided
| Item | Dependency |
|---|---|
| Real S3 behaviour, bucket privacy | owner confirmation, test with real bucket |
| Real Brevo delivery, SPF/DKIM/DMARC | Brevo key, DNS |
| Malware scanning | provider choice |
| CAPTCHA / bot check | provider choice |
| Calendar availability and booking links | calendar provider (Phase 4 integration) |
| Retention periods, privacy notice text, expiry reminder days | business decisions (jobs are inert until set) |
| Invitation vs self-registration, reviewer-assignment authority, explicit "approved" status, threshold applicability per pathway, BDM access to strategic discussions, content approver role, freeze-profile-during-review | business decisions (current defaults documented in each architecture doc) |
| Hosting, backups/restore tests, incident process, monitoring, HTTPS, cookie consent, analytics | operations / frontend |

## Known limitations and risks
All code written since the last executed run (MFA, Phase 3, this pass) is untested; new tests exist but were not run: `tests/api/test_mfa.py`, `test_admin.py`, `test_content_engagement.py`, `test_ops.py`.
Newsletter list has no double opt-in. Privacy requests do not verify identity. KPI "qualified enquiry" and "% meeting criteria" are not computed (undefined; humans decide). Partner enquiry history matches by account email.
Three files (`README.md`, this phase's API contract and completion report) were found blanked to NUL bytes by a disk fault and were rewritten from scratch; other documents should be skimmed for similar loss during the test cycle.

## Checks performed this pass
`ruff format`, `ruff check` (clean at last run), `python -c "import app.main"` (ok), `alembic check` on the local test DB (no drift). No pytest or mypy run, no Supabase connection.
