# Partner Application API & Database Gap Analysis (Report 3)

---

## 1. Existing vs Missing API Endpoints

| Category | Endpoint Route | HTTP Method | Existing in Codebase? | Implementation Status | Gap Description |
|---|---|---|---|---|---|
| **Intake** | `/api/v1/enquiries/partner` | POST | ✅ YES | Operational | Saves only to `enquiries` table |
| **Promotion** | `/api/v1/reviewer/applications/from-enquiry/{id}` | POST | ❌ NO | Missing | Manual elevation of public enquiry to application |
| **List Applications** | `/api/v1/reviewer/applications` | GET | ✅ YES | Partial | 403 to BDMs; missing search/date filters |
| **Dual Assignment** | `/api/v1/reviewer/applications/{id}/assign` | POST | ⚠️ PARTIAL | Incomplete | Accepts only `reviewer_id`; needs `bdm_id` |
| **Assignment History**| `/api/v1/reviewer/applications/{id}/assignment-history`| GET | ❌ NO | Missing | No audit trail of reassignments |
| **Recommendation** | `/api/v1/reviewer/applications/{id}/submit-recommendation`| POST | ❌ NO | Missing | Structured reviewer recommendation |
| **Capability Review** | `/api/v1/reviewer/applications/{id}/capability-reviews` | POST / GET | ❌ NO | Missing | 1–5 structured rating persistence |
| **Commercial Review**| `/api/v1/reviewer/applications/{id}/commercial-reviews` | POST / GET | ❌ NO | Missing | Commercial terms sign-off |
| **Legal Review** | `/api/v1/reviewer/applications/{id}/legal-reviews` | POST / GET | ❌ NO | Missing | NDA & IP legal sign-off |
| **Partner Team** | `/api/v1/partner/team` | GET / POST | ✅ YES | Complete | Full team invite, role, deactivation |
| **Onboarding Tasks** | `/api/v1/partner/onboarding` | GET | ✅ YES | Complete | Task view and completion endpoints |
| **Performance** | `/api/v1/partner/performance/*` | GET | ✅ YES | Complete | Summary, scorecards, trends |

---

## 2. Database Schema Gap Analysis

### A. Missing Foreign Keys on Existing Tables:
- Table `portal_applications`:
  - ❌ Missing: `enquiry_id` (UUID, nullable, FK to `enquiries.id`)
  - ❌ Missing: `assigned_bdm_id` (UUID, nullable, FK to `users.id`)

### B. Missing Database Tables:
1. **`application_recommendations`**:
   - `id`: UUID (PK)
   - `application_id`: UUID (FK to `portal_applications.id`, cascade)
   - `recommender_id`: UUID (FK to `users.id`)
   - `recommended_stage`: VARCHAR
   - `justification`: TEXT
   - `created_at`: TIMESTAMPTZ
2. **`application_assignment_history`**:
   - `id`: UUID (PK)
   - `application_id`: UUID (FK to `portal_applications.id`)
   - `role_type`: VARCHAR (`bdm` or `reviewer`)
   - `previous_user_id`: UUID (FK to `users.id`, nullable)
   - `new_user_id`: UUID (FK to `users.id`)
   - `assigned_by`: UUID (FK to `users.id`)
   - `reason`: TEXT
   - `assigned_at`: TIMESTAMPTZ
3. **`capability_reviews`**:
   - `id`: UUID (PK)
   - `application_id`: UUID (FK to `portal_applications.id`)
   - `infrastructure_rating`: INTEGER (1–5)
   - `domain_expertise_rating`: INTEGER (1–5)
   - `team_strength_rating`: INTEGER (1–5)
   - `delivery_capability_rating`: INTEGER (1–5)
   - `client_references_verified`: BOOLEAN
   - `operational_readiness`: VARCHAR
   - `assessed_by`: UUID (FK to `users.id`)
   - `notes`: TEXT
   - `created_at`: TIMESTAMPTZ
4. **`commercial_legal_reviews`**:
   - `id`: UUID (PK)
   - `application_id`: UUID (FK to `portal_applications.id`)
   - `scope_summary`: TEXT
   - `pricing_terms`: TEXT
   - `payment_terms`: TEXT
   - `nda_executed`: BOOLEAN
   - `ip_terms_accepted`: BOOLEAN
   - `legal_notes`: TEXT
   - `signed_off_by`: UUID (FK to `users.id`)
   - `signed_off_at`: TIMESTAMPTZ

