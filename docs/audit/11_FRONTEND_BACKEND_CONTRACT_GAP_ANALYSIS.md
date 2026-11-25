# Frontend-Backend Contract Gap Analysis

**Audited Frontends:** Public Website (`coral-swift.vercel.app`), Admin Console, Partner Portal  
**Source Contract:** `docs/api/openapi.json` (251 paths, 435 schemas)

---

## 1. Authentication & MFA Contract Gap

| Item | Frontend Expectation | Backend Reality | Fix Required in Frontend |
|---|---|---|---|
| **MFA Verification** | Calls `/auth/mfa/verify` after login | Endpoints deleted; returns 404 | Remove verification step entirely |
| **Login Response** | Expects `mfa_required: true/false` | Field removed; returns `TokenOut` with access & refresh tokens | Directly store tokens and navigate to dashboard |
| **User Profile** | Expects `mfa_enabled` on `GET /auth/me` | Field removed from response | Remove MFA toggle from profile UI |
| **Admin Policy** | Expects `staff_mfa_required` on policy | Setting removed | Remove MFA policy toggles from Admin |

---

## 2. Public Submission & Turnstile Anti-Bot Gap

| Item | Frontend Expectation | Backend Reality | Fix Required |
|---|---|---|---|
| **Turnstile Site Key**| Reads `NEXT_PUBLIC_TURNSTILE_SITE_KEY` | Key not provided in Vercel environment | Add `0x4AAAAAAF_cJue3EvIWbD8f` to Vercel env |
| **CORS Origin** | Origin `https://coral-swift.vercel.app` allowed | Was missing from backend `CORS_ALLOWED_ORIGINS` | Add URL to Render backend config |
| **Anti-Bot Header** | Header `X-Bot-Token` sent on POST | Backend requires valid token when `CAPTCHA_ENABLED=true` | Frontend must pass token obtained from widget |

---

## 3. Partner Application Review & Management Gap

| Item | Frontend Expectation | Backend Reality | Impact / Resolution |
|---|---|---|---|
| **Public Intake Bridge**| Submitting `/enquiries/partner` appears in reviewer queue | Saves to `enquiries` table only | Backend must auto-promote or provide elevation endpoint |
| **BDM Access to Review**| BDM views applications in reviewer queue | Backend returns `403 Forbidden` to BDM role | Update backend RBAC to include `business_development_manager` |
| **Dual Assignment** | Admin assigns both BDM and Reviewer | Only `assigned_reviewer_id` exists in schema | Add `assigned_bdm_id` to `PortalApplication` model |
| **Recommendation vs Approval** | Reviewer submits recommendation; Manager approves | Any reviewer can unilaterally execute `pilot_onboarding` | Add `authorized_management` role & recommendation endpoint |
| **Capability Review Form** | Frontend submits structured 1–5 ratings | Backend only has generic text checklist items | Create dedicated `capability_reviews` endpoint & table |
| **Commercial/Legal Form** | Frontend submits legal sign-off & NDA acceptance | Backend only has generic checklist items | Create dedicated `commercial_legal_reviews` endpoint & table |

---

## 4. Response Envelope & Pagination Standards

All frontend API client wrappers must conform to the standard backend JSON envelope:

### Success Response Envelope:
```json
{
  "success": true,
  "message": "Action completed successfully",
  "data": { ... },
  "meta": {
    "page": 1,
    "page_size": 20,
    "total": 142,
    "pages": 8
  }
}
```

### Error Response Envelope:
```json
{
  "success": false,
  "message": "Validation error or business failure description",
  "error": {
    "code": "VALIDATION_ERROR",
    "details": [
      {
        "field": "business_email",
        "message": "Must be a valid corporate email address"
      }
    ]
  }
}
```

