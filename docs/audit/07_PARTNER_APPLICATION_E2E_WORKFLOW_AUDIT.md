# Partner Application End-to-End Workflow Audit (Stages 1 – 9)

**Workflow Definition:** Approved CoralSwift PRD v2.0 Section 11 & Section 28  
**Scope:** Complete verification of all 9 stages from public intake to scale-up.

---

## 1. End-to-End Workflow Stage Matrix

| Stage | Expected Business Workflow | Frontend Status | Backend API | Database Persistence | Classification |
|---|---|---|---|---|---|
| **Stage 1: Application Submission** | Company submits full application with org details, turnover, staff count, and 8 required evidence documents. | Exists on Website (`/partner`) | `POST /enquiries/partner` | Saves to `enquiries` table only. | 🟡 **PARTIAL** (Saves enquiry, but does NOT create application) |
| **Stage 2: Super Admin Receipt** | Super Admin monitors new applications, reviews documents, and assigns to BDM. | Exists in Admin Console | `GET /admin/enquiries` | Enquiry queue works, but Reviewer queue lacks the application. | 🟡 **PARTIAL** (Enquiry visible; application queue disconnected) |
| **Stage 3: BDM Assignment & Ownership**| Super Admin assigns BDM. BDM becomes primary owner, coordinates reviewers, adds remarks. | Missing BDM Assignment UI | `POST /reviewer/applications/{id}/assign` | `assigned_reviewer_id` only; no `assigned_bdm_id`. | 🔴 **IMPLEMENTED INCORRECTLY** (Excludes BDM; Reviewer only) |
| **Stage 4: Eligibility Verification** | Reviewer verifies registration, financial statements, employee strength, client references. | Partial Checklist UI | `POST /reviewer/applications/{id}/eligibility` | Recorded in `review_checklist_items` and status transition. | ✅ **COMPLETE** (Functional human review) |
| **Stage 5: Capability Review** | Structured assessment of infrastructure (1–5), domain expertise (1–5), team strength (1–5), references. | Generic Checklist | Generic `PUT /reviewer/applications/{id}/checklist` | No dedicated `capability_reviews` table. | 🟡 **PARTIAL** (Checklist exists; structured rating table missing) |
| **Stage 6: Commercial & Legal Review** | Evaluation of pricing terms, payment milestones, NDA execution, and IP terms. | Generic Checklist | Generic `PUT /reviewer/applications/{id}/checklist` | No dedicated `commercial_legal_reviews` table. | 🟡 **PARTIAL** (Generic status transition; no legal sign-off table) |
| **Stage 7: Final Approval Decision** | Management sign-off. Reviewer recommendation is separate from final decision. | Status Dropdown | `POST /reviewer/applications/{id}/transition` | Direct transition to `pilot_onboarding` by any reviewer. | 🔴 **IMPLEMENTED INCORRECTLY** (Lacks multi-tier approval & segregation) |
| **Stage 8: Pilot Onboarding** | Onboarding record created, milestone tasks provisioned, partner portal access activated. | Onboarding UI exists | `POST /reviewer/onboarding`, `GET /partner/onboarding` | `onboarding_records`, `onboarding_tasks` persisted. | ✅ **COMPLETE** (Template support, progress tracking, partner tasks) |
| **Stage 9: Scale-Up & Performance** | Pilot evaluation, quality scorecards, delivery timeliness, and scale-up transition. | Performance UI exists | `POST /reviewer/.../performance`, `GET /partner/performance` | `performance_entries`, `performance_feedback` persisted. | ✅ **COMPLETE** (Turnaround days & completeness metrics published) |

---

## 2. Technical Evidence & Traceability

### Stage 1: Public Submission Trace
1. Frontend submits form data via `multipart/form-data` to `POST /api/v1/enquiries/partner`.
2. Handled by `app/modules/partners/router.py::submit_partner`.
3. Calls `app/modules/partners/service.py::create_partner_application`.
4. Generates unique reference code `ENQ-YYYY-XXXXX`.
5. Inserts record into `enquiries` table with `enquiry_type = "partner"`.
6. Enqueues background acknowledgement notification to applicant via Brevo adapter.
7. **Break in Flow:** The service does not instantiate a `PartnerOrganization` or `PortalApplication`. The record sits in `enquiries` awaiting manual Super Admin invitation.

### Stage 3: BDM Assignment Defect Trace
1. In `app/modules/applications/models.py`:
   ```python
   class PortalApplication(Base):
       __tablename__ = "portal_applications"
       ...
       assigned_reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
           ForeignKey("users.id", ondelete="SET NULL"), nullable=True
       )
       # ⚠️ Notice: No assigned_bdm_id exists!
   ```
2. In `app/modules/reviews/schemas.py`:
   ```python
   class AssignIn(BaseModel):
       reviewer_id: uuid.UUID
       reason: Short | None = None
       # ⚠️ Notice: Cannot specify bdm_id!
   ```
3. In `app/modules/reviews/router.py`:
   `ReviewerDep` is injected, which explicitly rejects any user whose role is `BUSINESS_DEVELOPMENT_MANAGER` with `403 FORBIDDEN`.

### Stage 7: Final Approval Defect Trace
1. Expected: Partner Reviewer submits `POST /reviewer/applications/{id}/submit-recommendation` -> BDM reviews -> Authorized Management signs off `POST /reviewer/applications/{id}/approve`.
2. Actual: The reviewer executes `POST /reviewer/applications/{id}/transition` with `{ "target_status": "pilot_onboarding", "reason": "Looks good" }`.
3. The backend executes the transition directly, changing the status without requiring Super Admin or executive credentials.

