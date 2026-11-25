# Centralized Redis Infrastructure & Caching Audit

**Package:** `redis 6.4.0` (present in `.venv/Lib/site-packages`)  
**Deployment Plan:** Render / Upstash Redis via `REDIS_URL`  
**Architecture Spec:** `docs/REDIS-ARCHITECTURE.md` & `docs/REDIS-ENDPOINT-COVERAGE.md`

---

## 1. Redis Infrastructure Status

| Architecture Requirement | Implementation Status | Evidence / Location |
|---|---|---|
| **Redis Dependency** | Installed in venv (`redis==6.4.0`) | `site-packages/redis` dist-info confirmed |
| **Shared Lifespan Lifecycle**| Ready for integration | Defined in `app/main.py::lifespan` |
| **Connection Pooling** | Defined in Architecture | Async client pool (`max_connections=20`) |
| **Rate Limiter Integration** | Per-process in place | `app/core/protection.py::FixedWindowLimiter` |
| **Fail-Safe Fallback** | Required | On Redis connection failure, bypass cache to PostgreSQL |
| **Render Deployment Variable**| Configured in Render | `REDIS_URL=redis://red-dbr9m46tlv9c73fsk2jg:6379` |

---

## 2. Caching Strategy & Endpoint Classification

### A. High-Priority Cache Candidates (Safe Reads)
1. **Public CMS Content (`/api/v1/content`):**
   - Cache Key: `cms:content:{slug}` or `cms:list:p{page}:l{limit}`
   - TTL: 300 seconds (5 minutes)
   - Invalidation: On CMS publish/update/delete by Content Administrator.
2. **Public Catalogs (`/api/v1/catalog/*`):**
   - Cache Key: `catalog:partner-criteria`, `catalog:project-categories`
   - TTL: 86400 seconds (24 hours) - Static reference enums.
3. **Admin KPI Aggregations (`/api/v1/admin/reports/kpis`):**
   - Cache Key: `admin:kpis:overview`
   - TTL: 300 seconds (5 minutes)
   - Reason: Protects PostgreSQL from repeated expensive multi-table aggregations.

### B. Tenant-Scoped Conditionally Cacheable Reads
1. **Partner Profile (`/api/v1/partner/organization`):**
   - Cache Key: `org:{org_id}:profile`
   - TTL: 600 seconds
   - Invalidation: Immediately upon profile edit or approved change request.
2. **Partner Onboarding Progress (`/api/v1/partner/onboarding`):**
   - Cache Key: `org:{org_id}:onboarding`
   - TTL: 120 seconds
   - Invalidation: On task status update.

### C. Strictly Non-Cacheable Operations
- `POST /api/v1/auth/*` — Tokens, credentials, and passwords must **never** be cached.
- `GET /api/v1/partner/documents/{id}/download` — Document blobs and signed URLs must **never** be cached in Redis.
- Authorization decisions — Permissions must always evaluate live against DB/token state.

---

## 3. Distributed Rate Limiting Design

Currently, rate limiting uses an in-memory `FixedWindowLimiter` in `app/core/protection.py`. When deploying multiple uvicorn workers or horizontal instances on Render, in-memory limits allow traffic multiplying by worker count.

### Redis INCR + EXPIRE Pattern (To be activated):
```lua
-- Atomic Fixed-Window Rate Limiter
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
if current > tonumber(ARGV[2]) then
    return redis.call('TTL', KEYS[1]) -- Exceeded; return retry-after seconds
else
    return 0 -- Allowed
end
```
- **Public Submissions:** 10 requests / minute / client IP.
- **Status Lookups:** 30 requests / minute / client IP.
- **Login Endpoint:** 10 requests / minute / client IP (defends against distributed brute force).

