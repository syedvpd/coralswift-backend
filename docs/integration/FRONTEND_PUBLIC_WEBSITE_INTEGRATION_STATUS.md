# Frontend Public Website Integration Status & Readiness Guide

Date: 2026-11-11
OpenAPI spec: [`docs/api/openapi.json`](../api/openapi.json) (`162` paths, `291` schemas)
Base API prefix: `/api/v1`

Latest verification note: the full suite collected 334 tests; the run after hostname hardening reported 333 passed and one production-settings fixture failure. That fixture was fixed and the focused app/config/botcheck set passed (37 tests); the full suite was not rerun after that fixture-only correction. Static checks pass. Live provider and browser checks remain outstanding.

Response envelope (success):
```json
{
  "success": true,
  "message": "OK",
  "data": {},
  "meta": null
}
```

Response envelope (error):
```json
{
  "success": false,
  "message": "Human-readable message",
  "error": {
    "code": "ERROR_CODE",
    "details": []
  }
}
```

---

## 1. Readiness Summary Across All 8 Dependencies

Status categories used below:
- **Implemented** — code and schemas exist in this repository.
- **Locally tested** — exercised end-to-end against disposable local PostgreSQL (`localhost:5433`), in-memory storage, and recording email fake.
- **Mock-tested** — third-party HTTP verification (Cloudflare Turnstile) verified via mocked `httpx.MockTransport` responses.
- **Owner-reported live setup (not live-verified)** — owner confirmed configuration exists in external Render / Vercel / Cloudflare dashboards; this audit did not execute live HTTP calls against Render, Vercel, Cloudflare, or Supabase.
- **Remote verification pending** — requires post-deploy smoke test against live Render URL.
- **Blocked by business decision** — requires owner policy sign-off before populating data or adding provider integrations.

| # | Dependency | Implementation Status | Local Test Result | Live / Environment Status | Remaining Action / Blocker |
|---|---|---|---|---|---|
| 1 | **CORS configuration** | **Implemented** (`CORSMiddleware`, credentials, `GET/POST/PUT/PATCH/DELETE/OPTIONS`, custom headers, exposed `X-Request-ID`, `Idempotent-Replay`, `Retry-After`, wildcard `*` rejected when hardened) | **Locally tested** across `http://localhost:3000`, `https://coralswift.com`, `https://coralswift-ochre.vercel.app`, and unapproved origins | **Owner-reported live setup (not live-verified)** — live Render `CORS_ALLOWED_ORIGINS` is externally configured | Owner/frontend: confirm live Render `CORS_ALLOWED_ORIGINS` includes the three approved origins and verify browser preflight against deployed URL |
| 2 | **Bot verification (`X-Bot-Token`)** | **Implemented** (`TurnstileVerifier` against Cloudflare `siteverify`; hardened config requires exact non-wildcard `TURNSTILE_ALLOWED_HOSTNAMES`; `NoopBotVerifier` only when `CAPTCHA_ENABLED=false`; whitespace/oversize local rejection) | **Mock-tested** (missing, blank, invalid, single-use replay `timeout-or-duplicate`, HTTP error fail-closed, hostname mismatch, >2048 chars) | **Owner-reported live setup (not live-verified)** — Turnstile widget + Render `CAPTCHA_ENABLED=true` / secret | Frontend: render Cloudflare Turnstile widget and send `X-Bot-Token`. Live end-to-end token test on deployed Render/Vercel required |
| 3 | **Public form submissions & status lookup** | **Implemented** (all 7 submission/verify endpoints + `GET /enquiries/{reference_number}/status`; idempotency; rate limits; strategic isolation) | **Locally tested** (valid payloads, 422 validation errors, 24 h `Idempotency-Key` replay, attachment rollback, rate limits, strategic isolation) | **Remote verification pending** — ready locally; meetings remain request-only (`calendar_checked=false`) | Deploy updated `main` to Render and run smoke tests; real calendar booking waits on **Business Decision D16** |
| 4 | **Document upload (`/documents/upload`)** | **Implemented** (`POST /api/v1/documents/upload`, MIME + magic-byte checks, 10 MiB file cap, 12 MiB body cap, 10 docs/enquiry, private storage, quarantine-only) | **Locally tested** (`.pdf`/`.png`/`.jpg`/`.docx`/`.xlsx`, 415 invalid type, 413 oversize, 422 cross-enquiry / failed-doc reuse, 404 org isolation, no public download) | **Remote verification pending** — production uses S3-compatible private bucket (`STORAGE_BACKEND=s3`) | Deploy updated `main` to Render; verify Render S3 bucket privacy and upload smoke test |
| 5 | **Privacy request verification** | **Implemented** (`POST /privacy/requests` + 72 h SHA-256 token email + single-use `POST /privacy/requests/verify` + CORS) | **Locally tested** (submission, email link extraction, verification, single-use replay rejection, >72 h expiry, CORS headers) | **Remote verification pending**; deletion execution policy waits on **D4** | Ensure `PORTAL_BASE_URL` on Render matches the frontend origin hosting `/privacy/verify`; **Business Decision D4** governs deletion policy |
| 6 | **Insights CMS (`GET /content?type=article`)** | **Implemented** (`PublicContent` / `PublicContentDetail` with all 8 SEO fields added in migration `0013`) | **Locally tested** (`?type=article` returns published items & SEO fields, drafts hidden, slug detail & sitemap work) | **Schema migrated on dev (`0015`), remote HTTP check pending** — `docs/handoff/SUPABASE_MIGRATION_PLAN.md` records Supabase dev at `0015 (head)` on 2026-11-11 | Push & deploy latest backend to Render and verify `GET /api/v1/content?type=article` returns HTTP 200 live; ensure published articles exist |
| 7 | **Corporate contact (`GET /site/contact`)** | **Implemented** (reads confirmed `contact.{domain,email,address,phone,representative}` from `system_settings`) | **Locally tested** (returns `{}` when unset; returns populated dict once set via admin settings) | **Blocked by business decision (D3)** — owner confirmed leaving contact details unpublished for now | **Business Decision D3**: owner approval of official contact fields, then populate via `PUT /api/v1/admin/settings` |
| 8 | **Newsletter (`/newsletter/subscribe`, `/unsubscribe`)** | **Implemented** (`POST /newsletter/subscribe`, `POST /newsletter/unsubscribe` with HMAC-SHA256 token, super-admin CSV export) | **Locally tested** (subscribe `200`, `consent=false` `422`, invalid unsubscribe token `404`, valid unsubscribe `200`, CSV export) | **Remote verification pending** (consent ledger only; no campaign mailer built) | Frontend: wire forms using Turnstile `X-Bot-Token`; verify on deployed Render URL |

---

## 2. Dependency 1 — CORS Configuration

### Backend Implementation
Configured in `app/main.py` (`CORSMiddleware`) and validated in `app/core/config.py`:
- **Approved website origins** (to configure in `CORS_ALLOWED_ORIGINS`):
  - `http://localhost:3000`
  - `https://coralswift.com`
  - `https://coralswift-ochre.vercel.app`
- **Credentials:** `allow_credentials=True`
- **Allowed methods:** `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `OPTIONS`
- **Allowed request headers:** `Authorization`, `Content-Type`, `Idempotency-Key`, `X-Bot-Token`, `X-Lookup-Token`, `X-Request-ID`
- **Exposed response headers:** `X-Request-ID`, `Idempotent-Replay`, `Retry-After`
- **Wildcard rule:** `Settings._production_rules` rejects `*` anywhere inside any `CORS_ALLOWED_ORIGINS` entry (for example `*` or `https://*.vercel.app`) when `APP_ENV` is `staging` or `production`.

### Render / External Configuration Required
Because CORS origins are environment-driven (`CORS_ALLOWED_ORIGINS`), verify the live Render service uses an explicit list matching the target environment:
- **Dev / Preview integration testing on Render:**
  ```env
  CORS_ALLOWED_ORIGINS=http://localhost:3000,https://coralswift.com,https://coralswift-ochre.vercel.app
  ```
- **Production on Render:** omit `http://localhost:3000` unless intentionally needed, keeping only approved HTTPS origins (e.g. `https://coralswift.com`, `https://coralswift-ochre.vercel.app`, plus any approved portal/admin HTTPS origins).
- **Local `.env` (already configured):** `CORS_ALLOWED_ORIGINS=http://localhost:3000`.

---

## 3. Dependency 2 — Bot Verification (`X-Bot-Token`)

### Provider & Token Acquisition
- **Provider:** Cloudflare Turnstile (`app/integrations/botcheck.py`).
- **No backend token-issuing endpoint exists.** Do not look for or call a backend endpoint to mint `X-Bot-Token`.
- **Frontend flow:**
  1. Render the Cloudflare Turnstile widget client-side using your public Cloudflare Turnstile **Site Key** (`NEXT_PUBLIC_*` / Vercel env).
  2. Turnstile yields a single-use token string on widget completion.
  3. Send that token verbatim in the `X-Bot-Token` HTTP request header on every guarded `POST` call.
  4. **Expiry & refresh:** Cloudflare Turnstile tokens are **single-use** and short-lived (**~300 seconds** per Cloudflare). Any replay or expired token causes Cloudflare `siteverify` to return `timeout-or-duplicate` (`403 BOT_CHECK_FAILED`). Call `turnstile.reset()` on the frontend after every submission (success or failure) and whenever the widget expires before submitting again.

### Server-Side Validation & Environment Behavior
- `TurnstileVerifier.verify(token, client_ip)` strips whitespace and immediately rejects `None`, empty strings, or tokens `> 2048` characters without contacting Cloudflare.
- Valid-length tokens are posted as `application/x-www-form-urlencoded` (`secret`, `response`, `remoteip`) to `https://challenges.cloudflare.com/turnstile/v0/siteverify` (fail-closed on network error or non-200 HTTP status).
- In `staging` and `production`, `TURNSTILE_ALLOWED_HOSTNAMES` is required and must be an explicit non-wildcard comma-separated or JSON hostname list. The `hostname` returned by Cloudflare `siteverify` must match it (e.g., `coralswift.com,coralswift-ochre.vercel.app`).
- **Environment matrix:**
  - `development` / `testing` with `CAPTCHA_ENABLED=false` (local backend default): `NoopBotVerifier` bypasses Turnstile so local API tests work without Cloudflare calls.
  - `development` with `CAPTCHA_ENABLED=true`, or `staging` / `production` (required by startup validation): `TURNSTILE_SECRET_KEY` is mandatory; startup fails if `CAPTCHA_ENABLED=false` or secret is missing in `staging`/`production`.
  - Keep `TURNSTILE_SECRET_KEY` strictly on the backend (Render); expose only the public Site Key on Vercel/frontend.

### Endpoints Requiring `X-Bot-Token`
| Endpoint | `X-Bot-Token` | Rate Limit (`rate_limit_per_minute=10` default) | `Idempotency-Key` |
|---|---|---|---|
| `POST /api/v1/enquiries/contact` | Required | `submit` (10/min) | Optional (24 h TTL) |
| `POST /api/v1/enquiries/project` | Required | `submit` (10/min) | Optional (24 h TTL) |
| `POST /api/v1/enquiries/partner` | Required | `submit` (10/min) | Optional (24 h TTL) |
| `POST /api/v1/enquiries/strategic` | Required | `submit` (10/min) | Optional (24 h TTL) |
| `POST /api/v1/meetings` | Required | `submit` (10/min) | Optional (24 h TTL) |
| `POST /api/v1/documents/upload` | Required | `upload` (20/min) | Not supported |
| `POST /api/v1/privacy/requests` | Required | `submit` (10/min) | Not supported |
| `POST /api/v1/newsletter/subscribe` | Required | `submit` (10/min) | Not supported |
| `POST /api/v1/newsletter/unsubscribe` | Required | `submit` (10/min) | Not supported |
| `POST /api/v1/privacy/requests/verify` | **Not required** | `submit` (10/min) | Not supported |
| `GET /api/v1/enquiries/{reference_number}/status` | **Not required** (uses `X-Lookup-Token`) | `status` (30/min) | N/A |

Failure response for missing, invalid, expired, or replayed token (`403`):
```json
{
  "success": false,
  "message": "Bot check failed",
  "error": { "code": "BOT_CHECK_FAILED", "details": null }
}
```

---

## 4. Dependency 3 — Public Form Submissions, Meetings & Status Lookup

### Shared Validation Rules (`SubmitterIn`)
Every enquiry and meeting schema uses `extra="forbid"` (unknown keys return `422`):
- `full_name`: `1..150` chars, stripped, non-empty.
- `designation`: optional `1..150` chars (`contact`, `project`, `meetings`); **required** on `partner` and `strategic`.
- `business_email`: max `254` chars, normalized lowercase. **Important:** reserved special-use test domains such as `.example` and `.test` are accepted ONLY when `APP_ENV` is `development` or `testing`; use real deliverable-syntax domains when testing `staging` or `production`.
- `phone`: cleaned of spaces/`()`/`.`/`-`, must match E.164 `^\+[1-9][0-9]{6,14}$` (e.g. `"+14155550123"`).
- `country`: 2-letter uppercase ISO country code (`^[A-Z]{2}$`, e.g. `"IN"`, `"US"`).
- `company_name`: optional `1..200` chars on `contact`/`meetings`; **required** on `project`, `partner`, `strategic`.
- `lead_source`: optional `<= 50` chars matching `^[A-Za-z0-9_.-]+$`.
- `privacy_consent`: boolean, **must be `true`**.

### Common Success Response (`201 Created`) for Enquiries & Meetings (`SubmissionOut`)
```json
{
  "success": true,
  "message": "Submission received",
  "data": {
    "reference_number": "CS-2026-000001",
    "lookup_token": "8f2a9c...40-char-hex-hmac...",
    "enquiry_type": "general|project|partner|strategic|meeting",
    "status": "received",
    "submitted_at": "2026-11-11T05:00:00Z",
    "documents_attached": 0
  },
  "meta": null
}
```
> Keep `reference_number` and `lookup_token` on the confirmation screen (or prompt the user to save them): `lookup_token` is an HMAC-SHA256 credential required for subsequent status checks and cannot be recovered by public lookup.

Idempotency replay (`Idempotency-Key`, <= 128 chars): repeating the same key + identical payload within 24 hours returns the cached response with HTTP header `Idempotent-Replay: true`. Reusing the same key with a different payload returns `409 Conflict` (`IDEMPOTENCY_CONFLICT`).

Rate limit exceeded (`429 Too Many Requests`): returns `error.code = "TOO_MANY_REQUESTS"` and header `Retry-After: <seconds>`.

### Exact Request Payloads by Endpoint

#### A. `POST /api/v1/enquiries/contact` (`201`)
`enquiry_type` enum: `general_information` | `services` | `partnership` | `other` (`message`: `5..5000` chars).
```json
{
  "full_name": "Asha Nair",
  "designation": "VP Operations",
  "business_email": "asha.nair@acme-corp.com",
  "phone": "+919820012345",
  "country": "IN",
  "company_name": "Acme Corp",
  "lead_source": "website_contact",
  "privacy_consent": true,
  "enquiry_type": "services",
  "message": "Looking to discuss enterprise operations support."
}
```
Response `data.enquiry_type` is `"general"`.

#### B. `POST /api/v1/enquiries/project` (`201`)
`project_category` enum (13 values): `erp_implementation` | `web_app_development` | `custom_software` | `cloud_infrastructure` | `testing_maintenance` | `medical_coding_billing` | `healthcare_support` | `data_entry` | `document_processing` | `banking_kyc` | `mortgage_processing` | `mutual_fund_operations` | `back_office`.
```json
{
  "full_name": "Rohan Mehta",
  "designation": "IT Director",
  "business_email": "rohan@acme-corp.com",
  "phone": "+919820012346",
  "country": "IN",
  "company_name": "Acme Corp",
  "lead_source": "website_project",
  "privacy_consent": true,
  "project_category": "custom_software",
  "requirement_summary": "Customer onboarding workflow modernization.",
  "scope": "Web portal and API integration.",
  "expected_timeline": "Q1 2027",
  "estimated_volume": "500 transactions/day",
  "geography": "India and UK",
  "security_constraints": "ISO 27001 aligned controls",
  "document_ids": ["550e8400-e29b-41d4-a716-446655440000"]
}
```

#### C. `POST /api/v1/enquiries/partner` (`201`)
Required enums:
- `preferred_engagement_pathway`: `strategic_merger_integration` | `direct_project_engagement` | `vendor_subcontracting`
- `workforce_range`: `under_50` | `50_to_100` | `101_to_250` | `over_250`
- `turnover_range`: `under_inr_2_crore` | `inr_2_to_10_crore` | `over_inr_10_crore`
- `service_categories` (`1..12` unique): `erp` | `web_applications` | `custom_software` | `cloud_infrastructure` | `testing_maintenance` | `digital_transformation` | `medical_coding_billing` | `healthcare_support` | `data_entry_document_processing` | `banking_kyc_mortgage` | `mutual_fund_operations` | `back_office`
- `year_established`: integer `>= 1800` and `<= current year`
- `client_references`: `2..5` items of `{name, organization, contact}`
- `website`: optional `http://` or `https://` URL
```json
{
  "full_name": "Priya Menon",
  "designation": "Managing Partner",
  "business_email": "priya@partnerfirm.com",
  "phone": "+919820012347",
  "country": "IN",
  "company_name": "Partner Firm Pvt Ltd",
  "lead_source": "website_partner",
  "privacy_consent": true,
  "website": "https://partnerfirm.com",
  "year_established": 2018,
  "registered_address": "12 MG Road, Bengaluru 560001",
  "company_country": "IN",
  "preferred_engagement_pathway": "direct_project_engagement",
  "workforce_range": "50_to_100",
  "turnover_range": "inr_2_to_10_crore",
  "service_categories": ["erp", "cloud_infrastructure"],
  "infrastructure_summary": "SOC-aligned delivery center with 80 seats.",
  "client_experience": "Six years delivering enterprise ERP rollouts.",
  "client_references": [
    { "name": "Ref One", "organization": "Client A", "contact": "ref1@clienta.com" },
    { "name": "Ref Two", "organization": "Client B", "contact": "+919820099999" }
  ],
  "document_ids": []
}
```

#### D. `POST /api/v1/enquiries/strategic` (`201`)
`discussion_type` enum: `merger` | `integration` | `strategic_partnership`. `authorized_representative` must be `true`. Records are super-administrator only (BDM cannot view or download attachments); confidential text is never logged or emailed.
```json
{
  "full_name": "Vikram Rao",
  "designation": "CEO",
  "business_email": "vikram@strategic-co.com",
  "phone": "+919820012348",
  "country": "IN",
  "company_name": "Strategic Co",
  "privacy_consent": true,
  "discussion_type": "merger",
  "business_overview": "Profitable mid-market IT services firm.",
  "confidential_summary": "Exploring strategic combination in FY27.",
  "authorized_representative": true,
  "document_ids": []
}
```

#### E. `POST /api/v1/meetings` (`201`)
`preferred_slots`: `1..3` items with timezone-aware future `start`/`end` (`end > start`); `timezone`: valid IANA timezone string (e.g. `"Asia/Kolkata"`, `"UTC"`).
**Important:** Creating a meeting request does **not** check live calendar availability or confirm a slot (`calendar_checked` stays `false`, status `"received"` on `Enquiry` and `"requested"` internally). Real calendar provider integration awaits **Business Decision D16**.
```json
{
  "full_name": "Asha Nair",
  "business_email": "asha.nair@acme-corp.com",
  "phone": "+919820012345",
  "country": "IN",
  "company_name": "Acme Corp",
  "privacy_consent": true,
  "purpose": "Initial capabilities walkthrough",
  "preferred_slots": [
    { "start": "2026-12-01T10:00:00Z", "end": "2026-12-01T10:30:00Z" }
  ],
  "timezone": "Asia/Kolkata"
}
```

#### F. `GET /api/v1/enquiries/{reference_number}/status` (`200`)
Public status lookup **does exist**. Send header `X-Lookup-Token: <lookup_token>`. No `X-Bot-Token` required (`30/min` rate limit). Invalid reference or mismatched token returns an indistinguishable `404`.
```json
{
  "success": true,
  "message": "OK",
  "data": {
    "reference_number": "CS-2026-000001",
    "enquiry_type": "project",
    "status": "received",
    "submitted_at": "2026-11-11T05:00:00Z"
  },
  "meta": null
}
```
`status` enum: `received` | `in_review` | `closed`.

#### G & H. `POST /api/v1/privacy/requests` (`201`) & `POST /api/v1/privacy/requests/verify` (`200`)
Covered in Section 6 below.

---

## 5. Dependency 4 — Document Upload (`/api/v1/documents/upload`)

### Specification
- **Method & path:** `POST /api/v1/documents/upload` (anonymous public endpoint).
- **Headers:** `X-Bot-Token` (required when `CAPTCHA_ENABLED=true`), `Content-Type: multipart/form-data` (set automatically by browser when using `FormData`). Do **not** set a manual `Content-Type` header on `fetch`.
- **Rate limit:** `2 * rate_limit_per_minute` (`20/min` by default) -> `429 TOO_MANY_REQUESTS`.
- **Multipart form fields (single file per request):**
  - `file` (file): required.
  - `purpose` (string): required — one of `project_attachment`, `partner_evidence`, `strategic_attachment`.
  - `category` (string): **required iff `purpose=partner_evidence`**; must be omitted otherwise. Values: `registration_proof`, `operating_history`, `employee_strength`, `financial_statements`, `service_portfolio`, `infrastructure_summary`, `client_references`.
- **Allowed file extensions & MIME types (verified by BOTH extension AND file magic bytes):**
  - `.pdf` (`application/pdf`)
  - `.png` (`image/png`)
  - `.jpg` / `.jpeg` (`image/jpeg`)
  - `.docx` (`application/vnd.openxmlformats-officedocument.wordprocessingml.document`)
  - `.xlsx` (`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`)
  - Rejected files return `415 UNSUPPORTED_FILE_TYPE`. ZIP-based Office formats enforce decompression-bomb limits.
- **Size & count limits:**
  - Single file cap: **`10 MiB` (`10,485,760` bytes)** -> `413 FILE_TOO_LARGE`.
  - Total request body cap: **`12 MiB` (`12,582,912` bytes)** -> `413 PAYLOAD_TOO_LARGE`.
  - Maximum files per enquiry payload (`document_ids`): **`10`** (`MAX_DOCUMENTS_PER_ENQUIRY=10`) -> `422 TOO_MANY_DOCUMENTS` (schema caps array at 20). Upload multiple files by calling `/api/v1/documents/upload` once per file and collecting each `document_id`.

### Upload Response (`201 Created`)
```json
{
  "success": true,
  "message": "Document uploaded",
  "data": {
    "document_id": "550e8400-e29b-41d4-a716-446655440000",
    "original_filename": "architecture.pdf",
    "content_type": "application/pdf",
    "file_size": 12450,
    "checksum_sha256": "e3b0c44298fc1c149afbf4c8996fb924...",
    "upload_status": "quarantined"
  },
  "meta": null
}
```
> **Security & Storage Behavior:** Every uploaded file remains `upload_status="quarantined"`; **no malware scanner is configured** (accepted per owner policy). Storage keys (`storage_key`) are never returned, and there are **no public download URLs**. Only authorized staff (`/api/v1/admin/enquiries/{id}/documents/{doc_id}/download`, where financial statements & strategic attachments are Super-Administrator-only) or owning partners (`/api/v1/partner/documents/{id}/download`) can download files.
> Attaching a non-existent, failed, or already-attached `document_id` to `POST /enquiries/{project,partner,strategic}` returns `422 INVALID_DOCUMENT_REFERENCE` and rolls back the enquiry atomically.

### Frontend JavaScript Example
```ts
async function uploadAttachment(
  apiBase: string,
  botToken: string,
  file: File,
  purpose: "project_attachment" | "partner_evidence" | "strategic_attachment",
  category?: string,
): Promise<string> {
  const form = new FormData();
  form.append("file", file);
  form.append("purpose", purpose);
  if (category) form.append("category", category);

  const res = await fetch(`${apiBase}/api/v1/documents/upload`, {
    method: "POST",
    headers: { "X-Bot-Token": botToken },
    body: form,
  });
  const json = await res.json();
  if (!res.ok) throw new Error(json?.error?.code ?? "UPLOAD_FAILED");
  return json.data.document_id;
}
```

### Safe Upload Test Procedure
1. Upload a small valid `.pdf` (`<= 1 MiB`) with `purpose=project_attachment` -> expect `201` with `document_id` and `upload_status: "quarantined"`.
2. Pass `[document_id]` inside `POST /api/v1/enquiries/project` (`Idempotency-Key` recommended; note Turnstile tokens are single-use so obtain a fresh token for the form submit!) -> expect `201` with `documents_attached: 1`.
3. Re-submit the same `document_id` on a second enquiry -> expect `422 INVALID_DOCUMENT_REFERENCE`.
4. Attempt a `.txt` or `.exe` renamed to `.pdf` -> expect `415 UNSUPPORTED_FILE_TYPE`.
5. Attempt a file `> 10 MiB` -> expect `413`.

---

## 6. Dependency 5 — Privacy Request Verification

### Workflow & Contract
1. **Submit request:** `POST /api/v1/privacy/requests` (`X-Bot-Token` required, `10/min` rate limit, no `Idempotency-Key`).
   - Request body:
     ```json
     {
       "email": "user@acme-corp.com",
       "kind": "access",
       "details": "Please share a copy of my enquiry records."
     }
     ```
     (`kind`: `access` | `correction` | `deletion`; `details` optional `1..4000` chars).
   - Response (`201 Created`):
     ```json
     {
       "success": true,
       "message": "Request received",
       "data": { "reference": "PR-2026-000001" },
       "meta": null
     }
     ```
2. **Email verification link:** Backend creates a high-entropy single-use token, stores only its SHA-256 hash (`email_verified_at=NULL`), sets **`verification_expires_at` = 72 hours**, and sends email containing:
   ```text
   {PORTAL_BASE_URL}/privacy/verify?token=<raw_token>
   ```
3. **Confirm token from frontend route `/privacy/verify`:** `POST /api/v1/privacy/requests/verify`
   - **No `X-Bot-Token` required** (`10/min` rate limit); CORS origins (`http://localhost:3000`, `https://coralswift.com`, `https://coralswift-ochre.vercel.app`) are supported on this endpoint.
   - Request body: `{ "token": "<raw_token>" }` (`10..200` chars).
   - Success response (`200 OK`):
     ```json
     {
       "success": true,
       "message": "Email confirmed",
       "data": { "reference": "PR-2026-000001" },
       "meta": null
     }
     ```
   - Errors (`400 Bad Request`): `INVALID_OR_EXPIRED_TOKEN` (unknown or already used) and `TOKEN_EXPIRED` (past 72 h).
   - Staff cannot process (`in_review`/`completed`) or execute deletion until verified (`409 EMAIL_NOT_VERIFIED`). Legal retention/deletion sign-off remains open under **Business Decision D4**.

---

## 7. Dependency 6 — Insights CMS (`GET /api/v1/content?type=article`)

- **Why HTTP 500 occurred previously:** `ContentItem` queries eight SEO/cover-image columns (`seo_title`, `seo_description`, `canonical_url`, `og_title`, `og_description`, `og_image_url`, `image_url`, `image_alt`) introduced in Alembic migration `0013`. When the backend queried a database still at revision `0012`, PostgreSQL failed on missing `content_items.seo_title`.
- **Current database state:** [`docs/handoff/SUPABASE_MIGRATION_PLAN.md`](../handoff/SUPABASE_MIGRATION_PLAN.md) records that on `2026-11-11` the owner-authorized upgrade brought the Supabase development database (`zibfzlwzaecapfrgjret`) from `0012` to `0015 (head)`, with `alembic check` clean and the SEO columns verified on `content_items`.
- **Endpoints & fields verified locally:**
  - `GET /api/v1/content` (query params: `page`, `page_size`, `q`, `type=article|faq|page|resource`, `category`, `tag`) -> returns paginated `PublicContent` list with all 8 nullable SEO fields (`seo_title`, `seo_description`, `canonical_url`, `og_title`, `og_description`, `og_image_url`, `image_url`, `image_alt`; `https://` URLs enforced when set).
  - `GET /api/v1/content/{slug}` -> `PublicContentDetail` (includes `body` and up to 4 `related` published items).
  - `GET /api/v1/content/sitemap` -> `[{slug, updated_at}]` for published items.
  - `GET /api/v1/content/{slug}/download` -> attachment download when attached.
  - Only `status = "published"` items appear publicly; empty state returns `200` with `data: []` once migrated.
- **Remaining step:** Ensure latest backend code is deployed on Render (where `render.yaml` `preDeployCommand: alembic upgrade head` also safeguards migrations) and smoke-test `GET /api/v1/content?type=article` against the live Render URL.

---

## 8. Dependency 7 — Corporate Contact Information (`GET /api/v1/site/contact`)

- **Behavior:** Reads `system_settings` keys `contact.domain`, `contact.email`, `contact.address`, `contact.phone`, `contact.representative`, omitting any unset key (`Cache-Control: public, max-age=300`).
- **Current status:** Returns `{}` while approved corporate contact details remain unavailable. **Business Decision D3** (`docs/business-decisions-required.md`) is still open; no address, phone, email, or legal entity has been invented.
- **Frontend guidance:** Render only keys present in `res.data`, or hide/omit the contact block when `Object.keys(res.data).length === 0`. No placeholder address/phone/email will be returned until D3 is approved and populated via `PUT /api/v1/admin/settings` (Super Administrator).

---

## 9. Dependency 8 — Newsletter

- **Status:** **Implemented and locally tested** (`app/modules/engagement/router.py`).
- **Behavior scope:** Records explicit newsletter opt-in consent and opt-out withdrawals in the backend database (plus `GET /api/v1/admin/reports/newsletter.csv` for Super Administrators). Does **not** dispatch marketing campaigns or sync to external mailing lists.
- **Endpoints:**
  1. **Subscribe:** `POST /api/v1/newsletter/subscribe` (`200 OK`)
     - Headers: `X-Bot-Token` (required when `CAPTCHA_ENABLED=true`), `Content-Type: application/json`. Rate limit: `10/min`.
     - Body (`NewsletterIn`, `extra="forbid"`):
       ```json
       { "email": "reader@acme-corp.com", "consent": true }
       ```
       (`consent: false` returns `422`).
     - Response:
       ```json
       {
         "success": true,
         "message": "Subscribed",
         "data": { "unsubscribe_token": "32-char-hex-hmac..." },
         "meta": null
       }
       ```
  2. **Unsubscribe:** `POST /api/v1/newsletter/unsubscribe` (`200 OK`)
     - Headers: `X-Bot-Token` (required when `CAPTCHA_ENABLED=true`), `Content-Type: application/json`. Rate limit: `10/min`.
     - Body (`UnsubscribeIn`, `extra="forbid"`):
       ```json
       { "email": "reader@acme-corp.com", "token": "32-char-hex-hmac..." }
       ```
     - Response: `{ "success": true, "message": "Unsubscribed", "data": null, "meta": null }` (`404` if email or HMAC token is invalid).

---

## 10. Pending External Configuration, Business Decisions & Next Actions

| Item | Responsible Party | Action Needed |
|---|---|---|
| Deploy `main` to Render & verify live URL | Backend / DevOps (Owner) | Push updates to `main`, allow Render deploy + health check (`/health/live`, `/health/ready`) to complete, then smoke-test `/api/v1/content?type=article` and CORS preflight (`OPTIONS`) against the live Render URL |
| Render live environment check | Backend / DevOps (Owner) | Confirm Render `CORS_ALLOWED_ORIGINS` matches approved origins (`http://localhost:3000,https://coralswift.com,https://coralswift-ochre.vercel.app` during dev/preview integration), `CAPTCHA_ENABLED=true`, valid `TURNSTILE_SECRET_KEY`, required exact `TURNSTILE_ALLOWED_HOSTNAMES`, `PORTAL_BASE_URL` matching live web domain, `STORAGE_BACKEND=s3`, `EMAIL_BACKEND=brevo`, and `APP_ENV` appropriate for email validation |
| Cloudflare Turnstile widget & real-domain E2E check | Frontend + Owner | Verify live Turnstile widget on `https://coralswift.com` / `https://coralswift-ochre.vercel.app` produces a token accepted by Render `/api/v1/enquiries/contact` |
| **Business Decision D3** | Business Owner | Approve official corporate contact details (`domain`, `email`, `address`, `phone`, `representative`) and populate via `PUT /api/v1/admin/settings` when ready to publish `/api/v1/site/contact` |
| **Business Decision D4** | Business Owner + Legal | Sign off on retention periods & legal deletion check procedure before operational privacy-deletion execution |
| **Business Decision D16** | Business Owner | Confirm calendar provider (or accept manual staff confirmation) before automated meeting availability checks are added |
