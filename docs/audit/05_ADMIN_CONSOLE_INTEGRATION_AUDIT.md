# Admin Console Integration & Management Audit

**Intended Users:** Super Administrators, Business Development Managers (BDMs), Partner Reviewers, Content Administrators.  
**Backend Modules:** `app/modules/admin`, `app/modules/reviews`, `app/modules/review_workflow`, `app/modules/content`.

---

## 1. Admin Console Capabilities Matrix

| Screen / Feature | Backend Route | Required Role | Persistence Verified | Frontend Mismatch / Gap |
|---|---|---|---|---|
| **Executive Dashboard** | `GET /api/v1/admin/overview` | Super Admin, BDM, Reviewer | Live DB queries | Un-typed dict response in some builds; needs strict schema |
| **KPI & Turnaround Reports**| `GET /api/v1/admin/reports/kpis` | Super Admin, BDM | Live DB aggregations | Requires Redis caching (heavy SQL COUNT/AVG) |
| **Enquiry Queue** | `GET /api/v1/admin/enquiries` | Super Admin, BDM, Reviewer | DB `enquiries` table | Paginated, supports queue/status filtering |
| **Enquiry Details** | `GET /api/v1/admin/enquiries/{id}`| Super Admin, BDM, Reviewer | DB `enquiries` table | Includes signed attachment download metadata |
| **Enquiry Assignment** | `POST /api/v1/admin/enquiries/{id}/assign`| Super Admin, BDM | DB `assigned_to_user_id`| Single assignee only; logged in `activities` |
| **Enquiry Email Reply** | `POST /api/v1/admin/enquiries/{id}/reply` | Super Admin, BDM | DB + Brevo | Returns 409 `FEATURE_DISABLED` unless `ENQUIRY_REPLY_ENABLED=true` |
| **Reviewer Applications** | `GET /api/v1/reviewer/applications` | Reviewer, Super Admin | DB `portal_applications` | **403 FORBIDDEN TO BDM.** BDMs cannot review applications |
| **Application Assignment** | `POST /api/v1/reviewer/applications/{id}/assign`| Super Admin | DB `assigned_reviewer_id` | **Only assigns Reviewer.** Cannot assign BDM |
| **Evaluation Checklist** | `PUT /api/v1/reviewer/applications/{id}/checklist`| Reviewer, Super Admin | DB `review_checklist_items`| `pass|fail|not_applicable|pending` (Scores rejected) |
| **Checklist Exception** | `POST /api/v1/reviewer/applications/{id}/exceptions`| Super Admin Only | DB `application_exceptions`| Allows overriding failed checklist with justification |
| **Application Stage Transition**| `POST /api/v1/reviewer/applications/{id}/transition`| Reviewer, Super Admin | DB `portal_applications` | **Any reviewer can approve `pilot_onboarding` (No tier separation)** |
| **User & Staff Management** | `GET /api/v1/admin/users`, `POST /admin/users/staff` | Super Admin Only | DB `users` table | Staff invitation via email (token-based) |
| **System Audit Log** | `GET /api/v1/admin/audit-log` | Super Admin Only | DB `activities` table | Immutable append-only trigger; verified |
| **System Settings** | `GET/PUT /api/v1/admin/settings[/{key}]` | Super Admin Only | DB `system_settings` | Enforces type and range validations |

---

## 2. Deep-Dive: Segregation of Duties Defect

In the approved PRD and enterprise governance model:
1. **Partner Reviewer:** Assesses technical, financial, and eligibility evidence and makes a **recommendation** (e.g. `recommend_approval` or `recommend_rejection`).
2. **Business Development Manager (BDM):** Evaluates commercial alignment, market need, and project fit.
3. **Authorized Management / Super Administrator:** Holds sole authority to execute final approval (`pilot_onboarding`) or terminal rejection (`rejected`).

### Code Inspection in `app/modules/reviews/router.py`:
```python
# CURRENT IMPLEMENTATION (VULNERABILITY)
@router.post("/applications/{id}/transition", ...)
def transition(
    id: uuid.UUID,
    payload: TransitionIn,
    staff: ReviewerDep, # Accepts ANY staff with Partner Reviewer role!
    db: DbSession,
    ...
):
    # Reviewer can directly set status = PortalStatus.PILOT_ONBOARDING
```
**Impact:** A junior reviewer can unilaterally approve an enterprise partner application into pilot onboarding without management review or authorization.

---

## 3. Deep-Dive: BDM Application Ownership Exclusion

In `app/modules/auth/dependencies.py`:
```python
ReviewerDep = Annotated[
    StaffContext,
    Depends(require_staff(StaffRole.SUPER_ADMINISTRATOR, StaffRole.PARTNER_REVIEWER)),
]
```
All reviewer workflow routes (`/api/v1/reviewer/applications/*`) inject `ReviewerDep`.
- When a user logged in as `StaffRole.BUSINESS_DEVELOPMENT_MANAGER` requests `GET /api/v1/reviewer/applications`, the backend raises `403 Forbidden`.
- Furthermore, `PortalApplication` has no `assigned_bdm_id` column.
- **Result:** BDMs are locked out of managing the very partner applications they are assigned to lead.

