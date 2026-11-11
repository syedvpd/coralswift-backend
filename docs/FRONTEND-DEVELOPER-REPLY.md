# Reply to the frontend developer (copy-ready, 2026-11-11)

Hi,

Status of the backend against your list. The code for everything below exists and is tested locally (371 tests pass) and the development database is migrated, **but the new code is not deployed yet**: the live URL still serves the previous version (162 endpoints), so none of the new endpoints answer there today. I will tell you when the deployed OpenAPI changes.

**Ready to integrate once deployed** (contract: `docs/api/openapi.json`, details: `docs/FRONTEND-INTEGRATION-HANDOFF.md`):
- Partner: projects, inbox, discussions/meetings/follow-ups, team management, notification preferences and typed notifications, onboarding checklist, extended profile fields (D44 enums), change requests (existing values can no longer be edited directly), performance (two indicators, published only), account closure request, sessions, partner privacy requests, information-request due dates and decision explanations.
- Admin: users get/patch/activity, application workload, review checklist (pass/fail/not applicable + notes, no scores), exceptions, stage owners, reopen, assessment outcomes, staff document upload/replace, `replacement_requested`, template versions, CMS hero/service/industry/navigation, media library, audit IP/outcome, KPI filters and turnaround, BDM assignment, team list, onboarding template.

**Needs your confirmation:** the notification `link` is `/applications?reference=<ref>` (my assumption); activation route `/activate?token=`; password minimum is 12 characters; tokens last 30 minutes (access) and 7 days (refresh).

**Not available by deliberate owner decision:** active malware scanning (files stay `scan_status: not_scanned`), PDF/Excel export, secrets API, calendar integration, CRM, HttpOnly-cookie sessions, ad-hoc requester email replies (endpoint answers 409 `FEATURE_DISABLED`).

**Blocked outside the code:** CORS on the live service still rejects `http://localhost:5173` (preflight 400) until the Render environment variable is updated; test accounts and a test mailbox need approved addresses; real email needs Brevo plus a verified domain; the bot check is disabled on the live service (`CAPTCHA_ENABLED=false`); required document categories and eligibility thresholds per pathway are not defined, so document completeness shows as unavailable.
