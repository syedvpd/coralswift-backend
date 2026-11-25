# Partner Application Role & Permission Audit (Report 4)

---

## 1. Existing vs Required Role Matrix

| Role Name | Enum Definition | Implemented in Backend? | Current Responsibilities | Deficiencies & Gaps |
|---|---|---|---|---|
| **Super Administrator** | `StaffRole.SUPER_ADMINISTRATOR` | ✅ YES | Full control, user management, audit logs, exceptions. | Functional. |
| **Business Development Manager** | `StaffRole.BUSINESS_DEVELOPMENT_MANAGER` | ⚠️ PARTIAL | Lead and enquiry assignment, meeting follow-ups. | **Excluded from `/reviewer/applications` (403 Forbidden). Cannot view or manage partner applications.** |
| **Partner Reviewer** | `StaffRole.PARTNER_REVIEWER` | ⚠️ PARTIAL | Reviews applications, runs checklists, requests info. | **Excessive permission: Can unilaterally execute terminal approval to `pilot_onboarding`.** |
| **Authorized Management** | `StaffRole.AUTHORIZED_MANAGEMENT` | ❌ NO | Sole authority to execute final commercial/pilot approval. | **Role does not exist in backend codebase.** |
| **Content Administrator** | `StaffRole.CONTENT_ADMINISTRATOR` | ✅ YES | CMS pages, articles, insights, media library. | Isolated from partner applications. |
| **Partner Owner** | `MembershipRole.OWNER` | ✅ YES | Submits applications, manages team, invites members. | Correctly isolated. |
| **Partner Member** | `MembershipRole.MEMBER` | ✅ YES | Read-only view of organization data. | Correctly restricted. |

---

## 2. Required Permission & Authorization Corrections

1. **Add `AUTHORIZED_MANAGEMENT`:**
   In `app/modules/auth/constants.py`:
   ```python
   class StaffRole(enum.StrEnum):
       SUPER_ADMINISTRATOR = "super_administrator"
       BUSINESS_DEVELOPMENT_MANAGER = "business_development_manager"
       PARTNER_REVIEWER = "partner_reviewer"
       CONTENT_ADMINISTRATOR = "content_administrator"
       AUTHORIZED_MANAGEMENT = "authorized_management"  # <-- ADD
   ```

2. **Permit BDM on Reviewer Queue:**
   In `app/modules/auth/dependencies.py`:
   ```python
   ReviewerDep = Annotated[
       StaffContext,
       Depends(require_staff(
           StaffRole.SUPER_ADMINISTRATOR,
           StaffRole.PARTNER_REVIEWER,
           StaffRole.BUSINESS_DEVELOPMENT_MANAGER,  # <-- ADD
           StaffRole.AUTHORIZED_MANAGEMENT          # <-- ADD
       )),
   ]
   ```

3. **Restrict Terminal Status Transitions:**
   In `app/modules/reviews/router.py`:
   ```python
   TERMINAL_APPROVAL_STATUSES = {PortalStatus.PILOT_ONBOARDING, PortalStatus.SCALE_UP, PortalStatus.REJECTED}
   if payload.target_status in TERMINAL_APPROVAL_STATUSES:
       if staff.role not in (StaffRole.SUPER_ADMINISTRATOR, StaffRole.AUTHORIZED_MANAGEMENT):
           raise AppError("Terminal decision requires Authorized Management approval", status_code=403, code="FORBIDDEN")
   ```

