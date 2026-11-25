# Recommended Implementation & Handover Roadmap

**Target Goal:** Bridge critical workflow gaps, establish segregation of duties, align frontend contracts, and achieve full production handover readiness.

---

## Sprint 1: Critical Workflow Ingestion & Handover Alignments (Days 1–3)

### Task 1.1: Frontend MFA & Turnstile Alignment (Immediate)
- **Frontend Actions:**
  - Add `NEXT_PUBLIC_TURNSTILE_SITE_KEY=0x4AAAAAAF_cJue3EvIWbD8f` in Vercel settings and redeploy `https://coral-swift.vercel.app`.
  - Delete all frontend calls to `/api/v1/auth/mfa/*` and remove MFA verification modal.
  - On `POST /api/v1/auth/login`, immediately extract `{ access_token, refresh_token }` and route to authenticated view.
- **Backend Actions:**
  - Ensure `https://coral-swift.vercel.app` is in `CORS_ALLOWED_ORIGINS` on Render.

### Task 1.2: Public Intake to Reviewer Queue Bridge
- **Backend Implementation:**
  - Update `app/modules/partners/service.py::create_partner_application`:
    - After inserting `Enquiry`, auto-create a `PartnerOrganization` record with `source_enquiry_id = enquiry.id`.
    - Auto-create a `PortalApplication` in status `submitted`.
  - Add manual promotion endpoint: `POST /api/v1/reviewer/applications/from-enquiry/{enquiry_id}` for Super Admins.
  - Migration: Add `enquiry_id` (UUID, nullable, FK to `enquiries.id`) on `portal_applications`.

---

## Sprint 2: Segregation of Duties & BDM Ownership (Days 4–6)

### Task 2.1: Multi-Tier Approval & Authorized Management
- Add `AUTHORIZED_MANAGEMENT = "authorized_management"` to `StaffRole` enum.
- Update `POST /api/v1/reviewer/applications/{id}/transition`:
  - Reviewers can only transition between evaluation stages (`eligibility_verification`, `capability_review`, `commercial_legal_review`, `information_requested`).
  - Terminal statuses (`pilot_onboarding`, `scale_up`, `rejected`) strictly require `SUPER_ADMINISTRATOR` or `AUTHORIZED_MANAGEMENT`.
- Create recommendation endpoint:
  - `POST /api/v1/reviewer/applications/{id}/submit-recommendation` accepting `{ target_stage, justification }`.
  - Create table `application_recommendations` (`id`, `application_id`, `recommender_id`, `recommended_stage`, `justification`, `created_at`).

### Task 2.2: BDM Application Ownership & Dual Assignment
- Migration: Add `assigned_bdm_id` (UUID, nullable, FK to `users.id`) on `portal_applications`.
- Update `ReviewerDep` in `app/modules/auth/dependencies.py` to include `StaffRole.BUSINESS_DEVELOPMENT_MANAGER`.
- Update assignment endpoint `POST /api/v1/reviewer/applications/{id}/assign` to accept:
  ```json
  {
    "bdm_id": "uuid-optional",
    "reviewer_id": "uuid-optional",
    "reason": "Initial operational allocation"
  }
  ```
- Create table `application_assignment_history` and endpoint `GET /api/v1/reviewer/applications/{id}/assignment-history`.

---

## Sprint 3: Evaluation Domain Schemas & Redis Activation (Days 7–9)

### Task 3.1: Capability Review (Stage 5) & Commercial/Legal Review (Stage 6)
- Create table `capability_reviews`:
  - `id`, `application_id` (FK), `infrastructure_rating` (1–5), `domain_expertise_rating` (1–5), `team_strength_rating` (1–5), `delivery_capability_rating` (1–5), `client_references_verified` (bool), `operational_readiness` (string), `assessed_by` (FK), `notes` (text), `created_at`.
  - Endpoints: `POST` & `GET /api/v1/reviewer/applications/{id}/capability-reviews`.
- Create table `commercial_legal_reviews`:
  - `id`, `application_id` (FK), `scope_summary` (text), `pricing_terms` (text), `payment_terms` (text), `nda_executed` (bool), `ip_terms_accepted` (bool), `legal_notes` (text), `signed_off_by` (FK), `signed_off_at`.
  - Endpoints: `POST` & `GET /api/v1/reviewer/applications/{id}/commercial-reviews`.

### Task 3.2: Centralized Redis Caching & Rate Limiting
- Connect async Redis client to `REDIS_URL` in `app/main.py::lifespan`.
- Replace in-memory `FixedWindowLimiter` with distributed Redis Lua atomic rate limiter.
- Cache public CMS endpoints and `/admin/reports/kpis` with TTL.

---

## Sprint 4: Final Handover, E2E Verification & Sign-Off (Day 10)
- Run complete test suite (400+ tests).
- Generate and publish finalized `openapi.json`.
- Execute live smoke test covering: Public Submit -> BDM Review -> Reviewer Assessment -> Management Approval -> Partner Onboarding.
- Complete official handover to Frontend and Business Operations teams.

