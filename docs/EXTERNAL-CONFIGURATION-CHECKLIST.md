# External configuration checklist (2026-11-11)

Nothing below was done or verified by the backend work. Send values through a password manager or the host's secret store, never in chat, code or logs. Owner = who must supply it.

| # | Item | Exact input needed | Owner | Blocks |
|---|---|---|---|---|
| 1 | CORS origins (Render env `CORS_ALLOWED_ORIGINS`; live check: localhost:5173 preflight -> 400, coralswift.com -> 200) | Exact https origin of the admin console, partner portal, public site and each preview URL, plus `http://localhost:5173` for dev. No wildcards in staging/production | Owner / DevOps | P1-01: portals cannot call the API from a browser until set; preflight to `/auth/login` currently fails on the deployed host |
| 2 | Development test accounts | Email addresses (aliases you control) for: 1 super admin, 1 BDM, 1 partner reviewer, 1 content admin, 2 partners in different organisations, 1 invited-not-activated partner. Delivery channel for first passwords/MFA setup | Owner | P1-02, all live checks |
| 3 | Development database | **DONE 2026-11-11**: migrations `0016`-`0025` applied to project ref `zibfzlwzaecapfrgjret` (verified identical in `.env` and `.env.render`); remote revision `0025` | - | - |
| 4 | Brevo | API key (set as `BREVO_API_KEY` on Render), verified sender address/domain (`EMAIL_SENDER_ADDRESS`), `EMAIL_BACKEND=brevo` | Owner / DevOps | Real email: invitations, resets, privacy verification, bounces |
| 5 | SPF / DKIM / DMARC | DNS records on the sending domain (records come from Brevo's domain setup). No domain exists yet | DevOps | Deliverability evidence (A-08c) |
| 6 | Bounce webhook | `EMAIL_WEBHOOK_SECRET` (long random) and registration of `POST /api/v1/webhooks/email` in Brevo with header `X-Webhook-Secret`. Payload shape must be checked against a live event | DevOps | A-08b live verification |
| 7 | Turnstile | Site key (frontend) and secret (`TURNSTILE_SECRET_KEY`), `TURNSTILE_ALLOWED_HOSTNAMES`, `CAPTCHA_ENABLED=true` once the frontend sends `X-Bot-Token`. The secret pasted in chat earlier must be rotated | Owner / DevOps | P1-10 live check |
| 8 | Private document storage | S3-compatible bucket(s) with public access blocked, `STORAGE_BACKEND=s3`, `S3_BUCKET`, `S3_PARTNER_BUCKET`, credentials in Render secrets. Proof of block-public-access setting | DevOps | P1-07 (privacy cannot be verified from code) |
| 9 | Public media storage (D29) | Decision: keep serving CMS images through the API (`/media/{id}/file`, today) or a separate public bucket/CDN. If a CDN, its base URL | Owner | Image hosting |
| 10 | Scheduled maintenance | Cron on Render running `scripts/run_maintenance.py` (scheduled publishing, retention job, expiry reminders) | DevOps | Scheduled CMS publishing |
| 11 | Deployment and OpenAPI publication | Explicit approval to deploy and to republish `docs/api/openapi.json` (165 -> current file). Not done | Owner | Frontend consumption of the new endpoints |
| 12 | Queue owners | Named staff user per queue (set via `PUT /admin/settings/route.owner.<queue>` and `route.backup.<queue>`); targets via `sla.<queue>` (24-48 h proposed, not set) | Management | D3 |
| 13 | Retention policy | Legal sign-off, then set `retention.partner_document_days`. Until then permanent deletion answers 409 `RETENTION_POLICY_NOT_APPROVED` | Owner + legal | D4 |
| 14 | Privacy SLA | After legal review set `privacy.completion_days` and `privacy.verification_hours` (nothing is set today; verification falls back to 72 h) | Owner + legal | D34 |

| 15 | Deploy the new code to Render | Approval to commit and push (Render builds from git) or Render dashboard/API access. Live service still serves the old 162-path API against the already-migrated database | Owner | Frontend cannot call any new endpoint on the live URL |
