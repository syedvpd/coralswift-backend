# Missing Functionality, Defects & Blocker Backlog

**Priority Framework:**
- **CRITICAL:** Blocks end-to-end business workflow or introduces security/compliance failure. Must resolve before handover.
- **HIGH:** Operational defect or significant missing feature impacting daily staff usage.
- **MEDIUM:** Secondary feature or architectural optimization.
- **LOW:** Cosmetic, typing, or minor cleanup task.

---

## 1. Prioritized Backlog

| # | Priority | Category | Feature / Defect Description | Affected Module & Layer | Resolution Plan |
|---|---|---|---|---|---|
| **B-01** | 🔴 **CRITICAL** | Ingestion | Public partner submission saves to `enquiries` but does not populate `portal_applications` | `app/modules/partners/service.py` | Auto-create `PartnerOrganization` + `PortalApplication` upon submission, or provide promotion endpoint `POST /reviewer/applications/from-enquiry/{id}` |
| **B-02** | 🔴 **CRITICAL** | Governance | Missing `authorized_management` role; reviewers can unilaterally approve applications | `app/modules/auth/constants.py`, `app/modules/reviews/router.py` | Add role to `StaffRole` enum; restrict terminal status transitions (`pilot_onboarding`, `rejected`) to Super Admin or Authorized Management |
| **B-03** | 🔴 **CRITICAL** | RBAC | BDM excluded from `/reviewer/applications` and no `assigned_bdm_id` on application model | `app/modules/applications/models.py`, `app/modules/auth/dependencies.py` | Add `assigned_bdm_id` FK to `portal_applications`; update `ReviewerDep` to permit BDM role |
| **B-04** | 🔴 **CRITICAL** | Frontend | Frontend calling deleted `/auth/mfa/*` routes and expecting MFA response fields | Frontend Auth Services | Remove all MFA calls and conditional UI screens in frontend; accept tokens immediately on login |
| **B-05** | 🔴 **CRITICAL** | Deployment | Missing `NEXT_PUBLIC_TURNSTILE_SITE_KEY` in Vercel environment blocking live forms | Frontend Vercel Config | Add `NEXT_PUBLIC_TURNSTILE_SITE_KEY=0x4AAAAAAF_cJue3EvIWbD8f` in Vercel & redeploy |
| **B-06** | 🟠 **HIGH** | Review | Missing dedicated Capability Review structured evaluation API & table | `app/modules/reviews/` | Create `capability_reviews` table (1–5 ratings for infra, domain, team, delivery) & endpoints |
| **B-07** | 🟠 **HIGH** | Review | Missing dedicated Commercial & Legal review sign-off API & table | `app/modules/reviews/` | Create `commercial_legal_reviews` table (scope, terms, NDA, IP acceptance) & endpoints |
| **B-08** | 🟠 **HIGH** | Operations | Missing dual-assignment endpoint & assignment history audit table | `app/modules/reviews/router.py` | Update `POST /reviewer/applications/{id}/assign` to accept `{ bdm_id, reviewer_id }`; create history table |
| **B-09** | 🟡 **MEDIUM** | Performance | Heavy aggregations on `/admin/reports/kpis` hit database directly without caching | `app/modules/admin/router.py` | Integrate Redis caching service with 300s TTL |
| **B-10** | 🟡 **MEDIUM** | Security | ClamAV scanner daemon offline; uploads remain in quarantined status | `app/integrations/scanner.py`, Render Infra | Deploy ClamAV service or maintain approved quarantine fallback (D33) |
| **B-11** | 🟢 **LOW** | OpenAPI | Un-typed dict responses on `/admin/overview` and `/admin/reports/kpis` | `app/modules/admin/router.py` | Define explicit Pydantic response models for strict client generation |

