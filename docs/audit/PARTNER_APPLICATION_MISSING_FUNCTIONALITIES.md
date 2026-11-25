# Missing Functionalities in Partner Application Workflow (Report 2)

**Scope:** Detailed functional backlog of missing, partial, or incorrectly implemented capabilities.

---

## 1. Detailed Missing Features

### Feature 1: Automatic Ingestion Promotion to Reviewer Applications
- **Expected:** When a user completes the Partner Application form on the Public Website, a `PartnerOrganization` and a `PortalApplication` (in status `submitted`) should be created automatically in the backend.
- **Current Implementation:** Saves only an `Enquiry` record.
- **Affected Portal:** Public Website & Admin Console.
- **Related API:** `POST /api/v1/enquiries/partner`.
- **Database Requirements:** Add `enquiry_id` (UUID, nullable, FK to `enquiries.id`) on `portal_applications`.
- **Priority:** 🔴 **CRITICAL**

### Feature 2: Multi-Tier Approval & Segregation of Duties
- **Expected:** Reviewers make recommendations; Authorized Management or Super Admin approves the final decision to enter `pilot_onboarding` or `rejected`.
- **Current Implementation:** Any reviewer can approve pilot onboarding directly via `/reviewer/applications/{id}/transition`.
- **Affected Portal:** Admin Console / Reviewer Queue.
- **Related API:** `POST /api/v1/reviewer/applications/{id}/submit-recommendation` (missing).
- **Database Requirements:** Create `application_recommendations` table (`id`, `application_id`, `recommender_id`, `recommended_stage`, `justification`, `created_at`). Add `authorized_management` to `StaffRole`.
- **Priority:** 🔴 **CRITICAL**

### Feature 3: BDM Dual Assignment & Application Ownership
- **Expected:** Super Administrator can assign both a BDM (lead owner) and a Reviewer (evaluator). BDMs can view and manage their assigned applications.
- **Current Implementation:** Only reviewer can be assigned; BDM is blocked (403).
- **Affected Portal:** Admin Console.
- **Related API:** `POST /api/v1/reviewer/applications/{id}/assign`.
- **Database Requirements:** Add `assigned_bdm_id` (UUID, FK to `users.id`) on `portal_applications`. Create `application_assignment_history` table.
- **Priority:** 🔴 **CRITICAL**

### Feature 4: Structured Capability Review (Stage 5)
- **Expected:** Reviewers rate infrastructure (1–5), domain expertise (1–5), team strength (1–5), delivery capability (1–5), and attest client reference checks.
- **Current Implementation:** Generic pass/fail checklist items only.
- **Affected Portal:** Admin Console / Reviewer Queue.
- **Related API:** `POST /api/v1/reviewer/applications/{id}/capability-reviews` (missing).
- **Database Requirements:** Create `capability_reviews` table.
- **Priority:** 🟠 **HIGH**

### Feature 5: Structured Commercial & Legal Review (Stage 6)
- **Expected:** Formal recording of scope summary, pricing terms, payment terms, NDA execution, and IP acceptance.
- **Current Implementation:** Generic checklist items only.
- **Affected Portal:** Admin Console / Reviewer Queue.
- **Related API:** `POST /api/v1/reviewer/applications/{id}/commercial-reviews` (missing).
- **Database Requirements:** Create `commercial_legal_reviews` table.
- **Priority:** 🟠 **HIGH**

### Feature 6: Server-Side Application Search & Filtering
- **Expected:** Filter applications by free-text search across legal name, reference number, creation dates, and category.
- **Current Implementation:** Filter by status and pagination only.
- **Affected Portal:** Admin Console / Reviewer Queue.
- **Related API:** `GET /api/v1/reviewer/applications`.
- **Priority:** 🟡 **MEDIUM**

