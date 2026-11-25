# Partner Application Workflow Audit (Report 1)

**Scope:** End-to-End Partner Application Workflow across Public Website, Admin Console, Partner Portal, Backend, and Database.

---

## 1. Overall Workflow Audit Matrix

| Workflow Stage | Frontend Status | Backend Implementation | Database & Integration | Overall Status |
|---|---|---|---|---|
| **Stage 1: Application Submission** | Form exists on Website (`/partner`) with required fields and Turnstile guard. | `POST /api/v1/enquiries/partner` in `app/modules/partners/router.py`. | Saves to `enquiries` table only. No `portal_applications` or `partner_organizations` row created. | **PARTIALLY IMPLEMENTED** |
| **Stage 2: Super Admin Receipt** | Enquiry appears in Admin Console enquiry list. | `GET /api/v1/admin/enquiries` in `app/modules/admin/router.py`. | `enquiries` table read with status, filters, and attachments. | **PARTIALLY IMPLEMENTED** |
| **Stage 3: BDM Assignment** | Assignee dropdown exists on enquiries. | `POST /api/v1/admin/enquiries/{id}/assign` exists, but application assignment `POST /reviewer/applications/{id}/assign` only accepts `reviewer_id`. | `assigned_reviewer_id` exists on `portal_applications`. **No `assigned_bdm_id` exists.** | **IMPLEMENTED INCORRECTLY** |
| **Stage 4: Eligibility Verification** | Reviewer checklist view exists. | `POST /reviewer/applications/{id}/eligibility` and checklist routes exist. | Recorded in `review_checklist_items` and `portal_applications`. | **COMPLETE** |
| **Stage 5: Capability Review** | Generic checklist UI only. | Generic `PUT /reviewer/applications/{id}/checklist` with `stage='capability_review'`. | No dedicated rating columns (1–5) or table. Stored as plain pass/fail notes. | **PARTIALLY IMPLEMENTED** |
| **Stage 6: Commercial & Legal Review** | Generic checklist UI only. | Generic `PUT /reviewer/applications/{id}/checklist` with `stage='commercial_legal_review'`. | No dedicated `commercial_legal_reviews` table for NDA, IP, and commercial terms. | **PARTIALLY IMPLEMENTED** |
| **Stage 7: Final Approval Decision** | Status transition action. | `POST /reviewer/applications/{id}/transition`. Any reviewer can set `pilot_onboarding`. | No `authorized_management` role. No recommendation entity. | **IMPLEMENTED INCORRECTLY** |
| **Stage 8: Pilot / Onboarding** | Onboarding view in Partner Portal & Admin. | `POST /reviewer/onboarding`, `GET /partner/onboarding`, `POST /partner/onboarding/tasks/{id}/complete`. | Persists in `onboarding_records` and `onboarding_tasks`. | **COMPLETE** |
| **Stage 9: Scale-Up** | Performance & Scorecards views. | `/reviewer/.../performance`, `GET /partner/performance/summary`. | Persists in `performance_entries`. | **COMPLETE** |
| **Partner Portal Synchronization** | Real-time status badge and messages. | `GET /partner/applications/{id}`, `GET /partner/messages`. | State changes in `portal_applications` reflect immediately. | **COMPLETE** |

---

## 2. Technical Evidence & Stage Breakdown

### Stage 1: Public Intake Break
- In `app/modules/partners/service.py`: `create_partner_application` writes exclusively to the `enquiries` table with `enquiry_type='partner'`.
- It does **not** create a row in `partner_organizations` or `portal_applications`.
- As a result, the application does not exist in the reviewer workflow database until someone manually invites the partner.

### Stage 3: BDM Application Ownership Exclusion
- In `app/modules/applications/models.py`: `PortalApplication` has `assigned_reviewer_id` but **no** `assigned_bdm_id`.
- In `app/modules/auth/dependencies.py`: `ReviewerDep` strictly requires `StaffRole.PARTNER_REVIEWER` or `StaffRole.SUPER_ADMINISTRATOR`. BDMs receive 403 Forbidden on `/reviewer/applications`.

### Stage 7: Segregation of Duties Failure
- In `app/modules/reviews/router.py`: Any reviewer can call `POST /reviewer/applications/{id}/transition` to move status from `commercial_legal_review` to `pilot_onboarding`.
- There is no requirement for management authorization or two-man rule sign-off.

