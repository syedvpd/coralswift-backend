# Authentication, RBAC & Security Audit

**Approved Design Profile:** Email + Password Authentication, Argon2id, Bearer JWT, Role-Based Access Control, Account Lockout. **MFA Removed.**

---

## 1. Authentication Lifecycle Audit

| Security Feature | Implementation Mechanism | Verification Result |
|---|---|---|
| **Password Hashing** | Argon2id (`time_cost=2`, `memory_kib=19456`, OWASP recommended profile) | ✅ Verified secure |
| **Password Complexity** | Minimum 12 characters enforced by Pydantic schema | ✅ Enforced |
| **Token Architecture** | JWT Bearer tokens: Access (30 min), Refresh (7 days) | ✅ Symmetric secret signing |
| **Token Rotation** | Strict refresh rotation with token-family reuse detection (replay revokes entire family) | ✅ Cryptographically verified |
| **Brute-Force Protection**| Account locked for 15 minutes after 5 consecutive failed password attempts | ✅ Persisted in database |
| **Generic Auth Errors** | 401 returns identical `"INVALID_CREDENTIALS"` message for unknown email, wrong password, or inactive account | ✅ Prevents user enumeration |
| **MFA Status** | **REMOVED COMPLETELY.** Sign-in returns active tokens immediately without 2-step verification | ⚠️ **Frontend must stop calling MFA** |
| **Account Lifecycle** | States: `invited`, `active`, `suspended`, `deactivated` | ✅ Enforced across all routes |

---

## 2. Role-Based Access Control (RBAC) Matrix

### Staff Roles (`StaffRole` Enum)
1. **`super_administrator`**: Unrestricted platform-wide access, user creation, security policy management, audit log access.
2. **`business_development_manager`**: Lead and enquiry management, partner collaboration, meeting coordination.
3. **`partner_reviewer`**: Application checklist reviews, eligibility assessment, information requests.
4. **`content_administrator`**: CMS pages, articles, insights, and media library management.
5. ⚠️ **`authorized_management`**: **MISSING.** Required for multi-tier final approvals.

### Partner Roles (`MembershipRole` Enum)
1. **`owner`**: Primary corporate contact, manages team members, submits/withdraws applications, edits profile.
2. **`member`**: Read-only access to organization profile, applications, performance metrics, and discussions.

### Route-Level Enforcement Audit
```
┌─────────────────────────────────┬───────────────────────────────────────────────────────┐
│ Endpoint Prefix                 │ Allowed Roles                                         │
├─────────────────────────────────┼───────────────────────────────────────────────────────┤
│ `/api/v1/admin/settings/*`      │ Super Administrator ONLY                              │
│ `/api/v1/admin/audit-log`       │ Super Administrator ONLY                              │
│ `/api/v1/admin/users/*`         │ Super Administrator ONLY                              │
│ `/api/v1/admin/enquiries/*`     │ Super Administrator, Business Development Manager     │
│ `/api/v1/reviewer/*`            │ Super Administrator, Partner Reviewer ❌ (No BDM)     │
│ `/api/v1/partner/team/*`        │ Partner Owner ONLY (Member gets 403)                  │
│ `/api/v1/partner/*`             │ Authenticated Partner Context                         │
└─────────────────────────────────┴───────────────────────────────────────────────────────┘
```

---

## 3. Security Hardening & Defenses

- **Trusted Host Middleware:** Configured with `ALLOWED_HOSTS` (`coralswift-backend.onrender.com`).
- **Security Headers Middleware:** Emits `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, and `Content-Security-Policy`.
- **Payload Size Limiter:** Enforces 12 MiB maximum request body (`BodySizeLimitMiddleware`).
- **Request ID Tracing:** Every HTTP transaction generates a unique UUID stamped in `X-Request-Id` and structured logs.
- **Secret Redaction:** `app/core/logging.py` automatically scrubs passwords, bearer tokens, connection strings, and API keys before writing to console/log sinks.

