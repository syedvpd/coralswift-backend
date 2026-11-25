# Public Website Integration Audit

**Public Domain:** `https://coral-swift.vercel.app`  
**Backend API Base:** `https://coralswift-backend.onrender.com/api/v1`  
**Scope:** Intake forms, Cloudflare Turnstile, CORS, Idempotency, and Public Content Delivery.

---

## 1. Public Form Verification Matrix

| Form Name | Route | HTTP Method | Bot-Check Guard | Rate Limit | Backend Service | Database Destination | Status |
|---|---|---|---|---|---|---|---|
| **Partner Application Intake** | `/enquiries/partner` | POST | Required (`X-Bot-Token`) | 10 / min | `partners/service.py` | `enquiries` table | 🟡 Functional intake, but disconnected from reviewer queue |
| **Contact Form** | `/enquiries/contact` | POST | Required (`X-Bot-Token`) | 10 / min | `enquiries/service.py` | `enquiries` table | ✅ Fully operational |
| **Project Enquiry** | `/enquiries/project` | POST | Required (`X-Bot-Token`) | 10 / min | `projects/service.py` | `enquiries` table | ✅ Fully operational |
| **Strategic Discussions** | `/enquiries/strategic` | POST | Required (`X-Bot-Token`) | 10 / min | `strategic/service.py`| `enquiries` table | ✅ Fully operational |
| **Document Upload** | `/documents/upload` | POST | Required (`X-Bot-Token`) | 20 / min | `documents/service.py`| `enquiry_attachments` | ✅ Uploads to private S3 bucket |
| **Meeting Request** | `/meetings` | POST | Required (`X-Bot-Token`) | 10 / min | `engagement/service.py`| `meeting_requests` | ✅ Operational |
| **Newsletter Subscribe** | `/newsletter/subscribe` | POST | Required (`X-Bot-Token`) | 10 / min | `engagement/service.py`| `newsletter_subscribers`| ✅ Operational |
| **Enquiry Status Check** | `/enquiries/{ref}/status`| GET | None (`X-Lookup-Token`) | 30 / min | `enquiries/service.py` | `enquiries` read | ✅ Minimal privacy-safe fields |

---

## 2. Cloudflare Turnstile Bot-Check Root Cause Analysis

### Observed Live Frontend Error
Users on `https://coral-swift.vercel.app/contact` and `/partner` encounter the following blocking banner:
> **Cloudflare Turnstile Verification Required**  
> *Public anti-bot Site Key is not configured (missing `NEXT_PUBLIC_TURNSTILE_SITE_KEY`). The backend enforces single-use X-Bot-Token verification on live submission endpoints.*

### Root Cause
1. **Frontend Configuration Gap:**
   In Next.js, client-side Turnstile components read `process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY`. If undefined, the Turnstile widget fails to mount and the frontend disables form submission to prevent 403 API rejections.
   - **Required Public Site Key:** `0x4AAAAAAF_cJue3EvIWbD8f`
   - **Action Required:** Add `NEXT_PUBLIC_TURNSTILE_SITE_KEY=0x4AAAAAAF_cJue3EvIWbD8f` to Vercel Environment Variables and trigger a fresh deployment.

2. **Backend Server-Side Verification (`app/integrations/botcheck.py`):**
   - The backend checks `settings.captcha_enabled`.
   - In production Render settings: `CAPTCHA_ENABLED=true` and `TURNSTILE_SECRET_KEY=0x4AAAAAAF_cJujHwRyCPEtzFJSDJxJbXtI`.
   - When the token arrives in the `X-Bot-Token` header, the backend calls `https://challenges.cloudflare.com/turnstile/v0/siteverify`.
   - If `TURNSTILE_ALLOWED_HOSTNAMES` is set, it validates the returned hostname against `coral-swift.vercel.app`.

3. **CORS Allowlist Requirement:**
   - The frontend origin `https://coral-swift.vercel.app` **must be present** in `CORS_ALLOWED_ORIGINS` in Render. Without this, browser preflight `OPTIONS` requests fail before the form data can be submitted.

---

## 3. Ingestion Bridge Gap (The Missing Link)

```
[User submits Partner Form on Website]
               │
               ▼
   POST /api/v1/enquiries/partner
               │
               ▼
      [Writes to `enquiries`]
      Reference: ENQ-2026-XXXX
               │
               ▼
   [Acknowledgement Email Sent]
               │
               ▼
 ❌ STOPS HERE! No Organization or PortalApplication created!
 ❌ Reviewers at /reviewer/applications see NOTHING!
```

### Remediation Required
1. Implement automated ingestion promotion: Upon successful validation and database persistence in `create_partner_application`, automatically create a corresponding `partner_organizations` row and an initial `portal_applications` row in status `submitted`.
2. Provide a manual promotion endpoint in the Admin Console: `POST /api/v1/reviewer/applications/from-enquiry/{enquiry_id}` allowing Super Admins or BDMs to elevate any existing enquiry into the formal review queue.

