# Partner Application Implementation Roadmap (Report 6)

---

## Phase 1: Application Receipt and Ownership Bridge
- **Backend:** Update `create_partner_application` to auto-provision `PartnerOrganization` and `PortalApplication` in status `submitted`.
- **Database:** Add `enquiry_id` (UUID, nullable, FK to `enquiries.id`) on `portal_applications`.
- **API:** Add `POST /api/v1/reviewer/applications/from-enquiry/{enquiry_id}` for manual elevation.

## Phase 2: BDM Assignment and Reviewer Management
- **Database:** Add `assigned_bdm_id` (UUID, nullable, FK to `users.id`) on `portal_applications`.
- **Database:** Create `application_assignment_history` table (`id`, `application_id`, `role_type`, `previous_user_id`, `new_user_id`, `assigned_by`, `assigned_at`, `reason`).
- **RBAC:** Permit `StaffRole.BUSINESS_DEVELOPMENT_MANAGER` on `/api/v1/reviewer/applications*`.
- **API:** Update `POST /api/v1/reviewer/applications/{id}/assign` to accept `{ bdm_id, reviewer_id, reason }`.

## Phase 3: Eligibility and Capability Assessment (Stage 5)
- **Database:** Create `capability_reviews` table (`id`, `application_id`, `infrastructure_rating`, `domain_expertise_rating`, `team_strength_rating`, `delivery_capability_rating`, `client_references_verified`, `operational_readiness`, `assessed_by`, `notes`, `created_at`).
- **API:** Add `POST /api/v1/reviewer/applications/{id}/capability-reviews` and `GET /api/v1/reviewer/applications/{id}/capability-reviews`.

## Phase 4: Commercial and Legal Review (Stage 6)
- **Database:** Create `commercial_legal_reviews` table (`id`, `application_id`, `scope_summary`, `pricing_terms`, `payment_terms`, `nda_executed`, `ip_terms_accepted`, `legal_notes`, `signed_off_by`, `signed_off_at`).
- **API:** Add `POST /api/v1/reviewer/applications/{id}/commercial-reviews` and `POST /api/v1/reviewer/applications/{id}/legal-reviews`.

## Phase 5: Final Approval and Multi-Tier Authorization (Stage 7)
- **RBAC:** Add `AUTHORIZED_MANAGEMENT = "authorized_management"` to `StaffRole`.
- **Database:** Create `application_recommendations` table (`id`, `application_id`, `recommender_id`, `recommended_stage`, `justification`, `created_at`).
- **API:** Add `POST /api/v1/reviewer/applications/{id}/submit-recommendation`.
- **Authorization Guard:** Restrict terminal decisions (`pilot_onboarding`, `scale_up`, `rejected`) to Super Admin or Authorized Management.

## Phase 6: Partner Portal & Onboarding Synchronization
- **API:** Guarantee `/partner/onboarding` tasks and milestone sync.
- **Contract:** Maintain existing `/partner/team` multi-user invite and role hierarchy.

## Phase 7: Search, Sorting & Schema Enhancements
- **API:** Add `q` (search), `created_from`, `created_to`, `sort` query parameters to `GET /api/v1/reviewer/applications`.
- **OpenAPI:** Provide explicit Pydantic response models for `/admin/overview` and `/admin/reports/kpis`.

