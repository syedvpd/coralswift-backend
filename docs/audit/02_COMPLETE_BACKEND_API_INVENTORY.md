# Complete Backend API Inventory & Route Classification

**Total Discovered Paths in OpenAPI / Runtime:** 251 Routes  
**Total Schema Definitions:** 435 Schemas  
**Framework:** FastAPI 0.162.2, Pydantic v2.14.3, SQLAlchemy 2.1.8

---

## 1. Authentication & Session Management (`/api/v1/auth`)

| Method | Path | Auth / Role | Rate Limit | Cache Status | Description / Purpose |
|---|---|---|---|---|---|
| POST | `/api/v1/auth/login` | Anonymous | `auth` (10/min) | NON_CACHEABLE | Authenticate staff/partner via email/password. Returns access + refresh token. **MFA removed.** |
| POST | `/api/v1/auth/refresh` | Anonymous (Bearer Refresh) | `auth` (10/min) | NON_CACHEABLE | Rotates refresh token; revokes session if replay detected. |
| POST | `/api/v1/auth/logout` | Authenticated | None | NON_CACHEABLE | Revokes current session and marks token family inactive. |
| POST | `/api/v1/auth/invitations/accept` | Anonymous (Token) | `auth` (10/min) | NON_CACHEABLE | Activates user account with initial password. |
| POST | `/api/v1/auth/password-reset/request` | Anonymous | `auth` (10/min) | NON_CACHEABLE | Sends password reset email if account exists (generic response). |
| POST | `/api/v1/auth/password-reset/confirm` | Anonymous (Token) | `auth` (10/min) | NON_CACHEABLE | Sets new password via single-use reset token. |
| POST | `/api/v1/auth/change-password` | Authenticated | `auth` (10/min) | NON_CACHEABLE | Changes password for currently logged-in user. |
| GET | `/api/v1/auth/me` | Authenticated | None | CACHE_COND (User-scoped) | Returns identity, role, partner/staff permissions, account status. |
| PATCH | `/api/v1/auth/me` | Authenticated | None | NON_CACHEABLE | Updates current user's profile (name, phone). |
| GET | `/api/v1/auth/sessions` | Authenticated | None | CACHE_COND (User-scoped) | Lists active sessions with IP, user-agent, last seen. |
| DELETE | `/api/v1/auth/sessions` | Authenticated | None | NON_CACHEABLE | Revokes all other active sessions for current user. |
| DELETE | `/api/v1/auth/sessions/{id}` | Authenticated | None | NON_CACHEABLE | Revokes specific session by ID. |
| GET | `/api/v1/auth/permissions` | Authenticated | None | CACHE_COND | Returns user permission bitmask/matrix. |

---

## 2. Public Intake & Submissions (`/api/v1/enquiries`, `/api/v1/documents`, `/api/v1/engagement`)

| Method | Path | Auth / Role | Guards | Cache Status | Description / Purpose |
|---|---|---|---|---|---|
| POST | `/api/v1/enquiries/contact` | Anonymous | BotCheck + RateLimit (10/min) | NON_CACHEABLE | General business enquiry form submission. |
| POST | `/api/v1/enquiries/partner` | Anonymous | BotCheck + RateLimit (10/min) | NON_CACHEABLE | Public partner application intake. **Saves to `enquiries` table only.** |
| POST | `/api/v1/enquiries/project` | Anonymous | BotCheck + RateLimit (10/min) | NON_CACHEABLE | Client project engagement enquiry submission. |
| POST | `/api/v1/enquiries/strategic` | Anonymous | BotCheck + RateLimit (10/min) | NON_CACHEABLE | Confidential M&A / strategic enquiry submission. |
| GET | `/api/v1/enquiries/{ref}/status` | Anonymous (`X-Lookup-Token`) | RateLimit (30/min) | CACHE_COND (Token-scoped) | Minimal status lookup for submitted public enquiry. |
| POST | `/api/v1/documents/upload` | Anonymous | BotCheck + RateLimit (20/min) | NON_CACHEABLE | Temporary file upload for public forms (10 MiB limit). |
| POST | `/api/v1/meetings` | Anonymous | BotCheck + RateLimit (10/min) | NON_CACHEABLE | Public meeting / discovery call request. |
| POST | `/api/v1/newsletter/subscribe` | Anonymous | BotCheck + RateLimit (10/min) | NON_CACHEABLE | Newsletter subscription opt-in. |
| POST | `/api/v1/newsletter/unsubscribe` | Anonymous (Token) | RateLimit (10/min) | NON_CACHEABLE | Newsletter unsubscribe via emailed link. |
| POST | `/api/v1/privacy/requests` | Anonymous | BotCheck + RateLimit (5/min) | NON_CACHEABLE | GDPR/DPDP data subject privacy request. |
| POST | `/api/v1/privacy/requests/verify` | Anonymous (Token) | RateLimit (10/min) | NON_CACHEABLE | Verifies email ownership for privacy request. |

---

## 3. Reviewer & Assessment Queue (`/api/v1/reviewer`)

| Method | Path | Required Role | Cache Status | Description / Purpose |
|---|---|---|---|---|
| GET | `/api/v1/reviewer/applications` | Partner Reviewer, Super Admin | NON_CACHEABLE | Lists assigned partner applications (`portal_applications`). **BDM gets 403.** |
| GET | `/api/v1/reviewer/applications/{id}` | Partner Reviewer, Super Admin | NON_CACHEABLE | Returns detailed application snapshot, documents, history. |
| POST | `/api/v1/reviewer/applications/{id}/assign` | Super Admin | NON_CACHEABLE | Assigns reviewer (`reviewer_id`). **No BDM assignment parameter.** |
| POST | `/api/v1/reviewer/applications/{id}/transition` | Partner Reviewer, Super Admin | NON_CACHEABLE | Executes stage transition. **Reviewer can approve pilot unilaterally.** |
| GET | `/api/v1/reviewer/applications/{id}/history` | Partner Reviewer, Super Admin | NON_CACHEABLE | Returns status progression history. |
| GET | `/api/v1/reviewer/applications/{id}/notes` | Partner Reviewer, Super Admin | NON_CACHEABLE | Internal confidential reviewer notes. |
| POST | `/api/v1/reviewer/applications/{id}/notes` | Partner Reviewer, Super Admin | NON_CACHEABLE | Adds internal reviewer note. |
| GET | `/api/v1/reviewer/applications/{id}/checklist` | Partner Reviewer, Super Admin | NON_CACHEABLE | Evaluation checklist items across 6 stages. |
| PUT | `/api/v1/reviewer/applications/{id}/checklist` | Partner Reviewer, Super Admin | NON_CACHEABLE | Saves pass/fail/pending checklist evaluation. |
| POST | `/api/v1/reviewer/applications/{id}/exceptions` | Super Admin | NON_CACHEABLE | Grants exception on failed checklist item. |
| POST | `/api/v1/reviewer/applications/{id}/reopen` | Super Admin | NON_CACHEABLE | Reopens rejected/withdrawn application for reconsideration. |
| POST | `/api/v1/reviewer/applications/{id}/messages` | Partner Reviewer, Super Admin | NON_CACHEABLE | Sends information request message to partner. |
| POST | `/api/v1/reviewer/invitations` | Super Admin | NON_CACHEABLE | Generates partner organization + invitation token from enquiry. |

---

## 4. Admin Console Management (`/api/v1/admin`)

| Method | Path | Required Role | Cache Status | Description / Purpose |
|---|---|---|---|---|
| GET | `/api/v1/admin/overview` | Super Admin, BDM, Reviewer | CACHE_READ (TTL: 60s) | Dashboard counters, recent activities, queue summaries. |
| GET | `/api/v1/admin/reports/kpis` | Super Admin, BDM | CACHE_READ (TTL: 300s) | Aggregated operational KPIs, turnaround metrics. |
| GET | `/api/v1/admin/enquiries` | Super Admin, BDM, Reviewer | NON_CACHEABLE | Paginated enquiry database with queue/status/assigned filters. |
| GET | `/api/v1/admin/enquiries/{id}` | Super Admin, BDM, Reviewer | NON_CACHEABLE | Complete enquiry detail with uploaded attachments. |
| PATCH | `/api/v1/admin/enquiries/{id}` | Super Admin, BDM | NON_CACHEABLE | Updates status, queue, priority, follow-up date. |
| POST | `/api/v1/admin/enquiries/{id}/assign` | Super Admin, BDM | NON_CACHEABLE | Assigns enquiry to staff user. |
| POST | `/api/v1/admin/enquiries/{id}/reply` | Super Admin, BDM | NON_CACHEABLE | Sends email reply (gated by `ENQUIRY_REPLY_ENABLED`). |
| GET | `/api/v1/admin/audit-log` | Super Admin Only | NON_CACHEABLE | Immutable system audit log with actor and IP. |
| GET | `/api/v1/admin/users` | Super Admin Only | NON_CACHEABLE | Lists all staff and partner user accounts. |
| POST | `/api/v1/admin/users/staff` | Super Admin Only | NON_CACHEABLE | Invites new staff member with designated role. |
| PATCH | `/api/v1/admin/users/{id}/status` | Super Admin Only | NON_CACHEABLE | Suspends / activates user account. |
| GET | `/api/v1/admin/settings` | Super Admin Only | CACHE_READ (TTL: 300s) | System configuration settings. |
| PUT | `/api/v1/admin/settings/{key}` | Super Admin Only | NON_CACHEABLE | Updates system parameter (SLA, lockout, TTLs). |

---

## 5. Partner Portal APIs (`/api/v1/partner`)

| Method | Path | Auth / Role | Cache Status | Description / Purpose |
|---|---|---|---|---|
| GET | `/api/v1/partner/organization` | Authenticated Partner | CACHE_COND (Org-scoped) | Organization profile, legal details, contacts. |
| PUT | `/api/v1/partner/organization` | Authenticated Partner (Owner) | NON_CACHEABLE | Direct edit for blank fields only (D19). |
| POST | `/api/v1/partner/organization/change-requests` | Authenticated Partner | NON_CACHEABLE | Submits profile amendment requiring admin approval. |
| GET | `/api/v1/partner/applications` | Authenticated Partner | CACHE_COND (Org-scoped) | Lists partner's portal applications. |
| POST | `/api/v1/partner/applications` | Authenticated Partner (Owner) | NON_CACHEABLE | Submits new partner portal application. |
| GET | `/api/v1/partner/applications/{id}` | Authenticated Partner | CACHE_COND (Org-scoped) | Detailed view with status history and partner-safe labels. |
| POST | `/api/v1/partner/applications/{id}/withdraw` | Authenticated Partner (Owner) | NON_CACHEABLE | Withdraws active application before pilot. |
| GET | `/api/v1/partner/team` | Authenticated Partner | CACHE_COND (Org-scoped) | Lists company team members and roles. |
| POST | `/api/v1/partner/team` | Authenticated Partner (Owner) | NON_CACHEABLE | Invites colleague to company portal. |
| POST | `/api/v1/partner/team/{id}/role` | Authenticated Partner (Owner) | NON_CACHEABLE | Changes colleague role (owner / member). |
| POST | `/api/v1/partner/team/{id}/deactivate` | Authenticated Partner (Owner) | NON_CACHEABLE | Deactivates team member account. |
| GET | `/api/v1/partner/notifications` | Authenticated Partner | NON_CACHEABLE | In-app notifications with unread counts. |
| POST | `/api/v1/partner/notifications/{id}/read`| Authenticated Partner | NON_CACHEABLE | Marks notification as read. |
| GET | `/api/v1/partner/onboarding` | Authenticated Partner | CACHE_COND (Org-scoped) | Onboarding stages, progress, and tasks. |
| POST | `/api/v1/partner/onboarding/tasks/{id}/complete`| Authenticated Partner | NON_CACHEABLE | Marks onboarding task completed. |
| GET | `/api/v1/partner/performance/summary` | Authenticated Partner | CACHE_COND (Org-scoped) | Published turnaround and completeness KPIs. |
| GET | `/api/v1/partner/performance/scorecards` | Authenticated Partner | CACHE_COND (Org-scoped) | Published quarterly partner scorecards. |

---

## 6. Public Content & Catalog APIs (`/api/v1/content`, `/api/v1/catalog`)

| Method | Path | Auth / Role | Cache Status | Description / Purpose |
|---|---|---|---|---|
| GET | `/api/v1/content` | Anonymous | CACHE_READ (TTL: 300s) | Published CMS pages, articles, insights. |
| GET | `/api/v1/content/{slug}` | Anonymous | CACHE_READ (TTL: 300s) | Full content article by slug. |
| GET | `/api/v1/content/sitemap` | Anonymous | CACHE_READ (TTL: 3600s) | Dynamic XML/JSON sitemap of published URLs. |
| GET | `/api/v1/catalog/partner-criteria` | Anonymous | CACHE_READ (Static) | Proposed screening criteria (3 yrs, 50 staff, 2 Cr). |
| GET | `/api/v1/catalog/project-categories` | Anonymous | CACHE_READ (Static) | Illustrative service and industry taxonomy. |
| GET | `/api/v1/media/{asset_id}/file` | Anonymous | CACHE_READ (TTL: 86400s) | Public CDN image serving from media library. |

