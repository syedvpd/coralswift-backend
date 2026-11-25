# Redis architecture

Status: implemented and tested locally. **Not yet active on Render**: no Redis service has been
provisioned or connected, and no live connection has been verified (see section 12).

Per-route status: [REDIS-ENDPOINT-COVERAGE.md](REDIS-ENDPOINT-COVERAGE.md) (generated from the
registered routes; a unit test fails if it goes stale).

## 1. Architecture

```
request -> middleware -> FastAPI dependencies (token, role, organisation: always from PostgreSQL)
                              |
                       endpoint wrapper  @cached_read / get_or_set
                              |                    |
                       CacheService  <----> RedisManager (one BlockingConnectionPool per app)
                              |                    ^
                       miss: run endpoint -> PostgreSQL        |
                                                    DistributedLimiter (rate_limit dependency)
commit -> SQLAlchemy after_commit hook -> CacheService.invalidate(namespace)
```

- The app is synchronous FastAPI + synchronous SQLAlchemy, so the client is the synchronous
  `redis-py` client (an async client cannot be called from the existing endpoints).
- Nothing connects at import. `create_app` builds one `RedisManager` per app; the pool connects
  lazily; `lifespan` pings on start and closes the pool on shutdown.
- Files: `app/core/redis.py` (client, circuit breaker), `app/core/cache.py` (cache service),
  `app/core/cache_http.py` (`@cached_read`), `app/core/cache_hooks.py` (invalidation),
  `app/core/protection.py` (`DistributedLimiter`).

## 2. Provider and connection

Render Key Value (Redis-compatible), declared in `render.yaml` (`coralswift-redis`) and
`render.staging.yaml` (`coralswift-redis-staging`): `ipAllowList: []` (private network only),
`maxmemoryPolicy: allkeys-lru`. The web service and the maintenance cron read `REDIS_URL` from the
service (`fromService ... connectionString`); no URL is stored in the repo. Use `rediss://` for any
URL that leaves a private network. Production and staging use separate instances.
Cache data is disposable: persistence is not required.

## 3. Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `REDIS_URL` | unset | Unset = Redis off (no caching, per-process rate limits) |
| `REDIS_KEY_PREFIX` | `cs` | Key prefix (`[a-z0-9_-]`, max 16) |
| `REDIS_MAX_CONNECTIONS` | 20 | Pool size; extra callers wait up to the connect timeout |
| `REDIS_CONNECT_TIMEOUT_SECONDS` | 2 | Connect timeout and pool wait |
| `REDIS_SOCKET_TIMEOUT_SECONDS` | 1 | Per command |
| `REDIS_RETRY_AFTER_FAILURE_SECONDS` | 5 | Circuit-breaker pause after a failure |
| `CACHE_ENABLED` | true | Turns caching off while keeping rate limits on Redis |
| `CACHE_MAX_TTL_SECONDS` | 3600 | Hard cap on every TTL |
| `CACHE_PUBLIC_CONTENT_TTL_SECONDS` | 300 | Public CMS |
| `CACHE_ADMIN_OVERVIEW_TTL_SECONDS` | 30 | Overview, workload |
| `CACHE_ADMIN_LIST_TTL_SECONDS` | 15 | Enquiry and organisation lists |
| `CACHE_ADMIN_REPORT_TTL_SECONDS` | 60 | KPI and report endpoints |
| `CACHE_ADMIN_SETTINGS_TTL_SECONDS` | 60 | Settings list |
| `CACHE_PARTNER_READ_TTL_SECONDS` | 30 | Projects, performance |
| `CACHE_NOTIFICATION_TTL_SECONDS` | 30 | Notification list, unread count |

## 4. Key conventions

- Entry: `<prefix>:v1:<namespace>:<sha256(sorted JSON of key parts)[:32]>`, value
  `{"g": <generation>, "v": <json>}`.
- Generation: `<prefix>:g:<namespace>`. Invalidation replaces it (O(1)); entries of an older
  generation are ignored and expire by TTL. **No SCAN or wildcard delete in production code.**
  A read is one `MGET` (generation + value).
- Namespaces: `public-content`, `admin-overview`, `admin-enquiries`, `admin-orgs`,
  `admin-settings`, `admin-reports`, `po:<organisation id>:projects`,
  `po:<organisation id>:performance`, `notif:<sha256(recipient email)[:24]>`.
- Key parts hold every argument of the endpoint plus the caller identity: staff = user + role;
  partner = user + organisation + membership role. An argument of unknown type disables caching
  for that call.
- Rate limits: `<prefix>:rl:<name>:<client ip>`, 60 s window.
- Bump `KEY_VERSION` in `cache.py` after changing a cached payload shape.

## 5. Endpoint cache matrix and TTLs

Authoritative list with all 283 routes: [REDIS-ENDPOINT-COVERAGE.md](REDIS-ENDPOINT-COVERAGE.md).

| Endpoint(s) | Namespace | TTL | Authorization before lookup |
|---|---|---|---|
| `GET /content`, `/content/{slug}`, `/content/sitemap` | `public-content` | 300 s | public (published rows only) |
| `GET /admin/overview`, `/admin/workload` | `admin-overview` | 30 s | staff role (BDM/Super Admin) |
| `GET /admin/enquiries` | `admin-enquiries` | 15 s | staff role; key has user + role + all filters |
| `GET /admin/organizations` | `admin-orgs` | 15 s | staff role |
| `GET /admin/settings` | `admin-settings` | 60 s | Super Admin |
| `GET /admin/reports/kpis`, `follow-ups`, `document-review`, `communications` | `admin-reports` | 60 s | staff roles of each report |
| `GET /partner/notifications`, `/unread-count` | `notif:<recipient>` | 30 s | partner session |
| `GET /partner/projects` | `po:<org>:projects` | 30 s | partner session + organisation |
| `GET /partner/performance/summary`, `/scorecards`, `/trends` | `po:<org>:performance` | 30 s | partner session + organisation |

Deliberately not cached (reasons per route in the coverage document): authentication and session
endpoints, audit log and CSV exports, all file downloads and signed access, private document
metadata, the enquiry-status lookup, partner applications (output derives from several tables),
reviewer/BDM views (assignment-scoped, read-your-writes), partner inbox/discussions/meetings,
profile/team/account endpoints, every write.

## 6. Invalidation matrix

Invalidation runs **after a successful COMMIT** (`after_commit`); a rollback discards the pending
set. ORM changes are mapped automatically; statements that bypass the ORM call `mark_dirty`.

| Event (model change) | Invalidates |
|---|---|
| CMS create/update/submit/approve/publish/unpublish/archive/scheduled publish (`ContentItem`) | `public-content` |
| Enquiry created, assigned, status/priority change, first response (`Enquiry`, `Contact`, `ProjectEnquiry`, `StrategicEnquiry`) | `admin-overview`, `admin-enquiries`, `admin-reports` |
| Follow-up change (`EnquiryFollowUp`) | `admin-reports` |
| Application submission/review/transition (`PortalApplication`) | `admin-overview`, `admin-orgs` |
| Organisation change, profile approval (`PartnerOrganization`) | `admin-orgs` |
| Project create/share/unshare/update (`PartnerProject`) | `po:<org>:projects` |
| Performance entry publish/edit (`PerformanceEntry`) | `po:<org>:performance` |
| Notification queued (`queue_notification`, core INSERT, `mark_dirty`) | `notif:<recipient>`, `admin-reports` |
| Notification status/read/unread (ORM) | `notif:<recipient>`, `admin-reports` |
| Read-all (bulk UPDATE, `mark_dirty`); privacy erasure (bulk UPDATE, `mark_dirty`) | `notif:<recipient>` |
| Setting write (ORM) / delete (bulk DELETE, `mark_dirty`) | `admin-settings` |
| Partner document version review (`PartnerDocumentVersion`) | `admin-reports` |

Stale data that is accepted (bounded by TTL): assignee names in the enquiry list; time-based
counters (overdue, SLA breached) in overview/lists; KPI inputs from tables not watched;
membership/permission changes never serve a stale decision because authorization is always read
from PostgreSQL, and partner keys include the membership role.
If Redis is unreachable at commit time the invalidation is lost and entries age out by TTL
(logged as `cache invalidation failed`).

## 7. Security

- Authentication and authorization run in FastAPI dependencies before the cache wrapper; a warm
  cache never bypasses a 401/403 (tested). Account lockout (database) and the no-MFA design are
  untouched.
- Cross-tenant isolation: organisation id is both in the namespace and in the key.
- Strategic data: staff keys include the role; the overview and lists are scoped by role.
- A payload containing a field named like a secret (`password`, `token`, `secret`, `otp`, `mfa`,
  `signed`, `api_key`, `download_url`, ...; whole words) is refused, logged, and not stored.
- Never cached: login/refresh/session responses, tokens, document bytes, signed URLs, audit log.
- Logs carry the Redis host and exception class only, never the URL or payload.
- Notification keys use a hash of the recipient address.

## 8. Rate limiting

`rate_limit(name, multiplier)` is unchanged for callers. With `REDIS_URL` set it uses
`DistributedLimiter`: one atomic Lua script (INCR + EXPIRE + TTL) per request, so all workers share
one counter per client and window. Same limits and `429 TOO_MANY_REQUESTS` + `Retry-After`
contract as before. It covers 39 operations (login and other `auth` routes, invitation and
password-reset flows, public enquiry/contact/meeting/newsletter/privacy forms, uploads, content and
media downloads, enquiry status lookup, partner application actions); see the coverage document.
Account lockout stays in PostgreSQL (`failed_login_count`, `locked_until`). There is no MFA.

No distributed locks are used except the per-key lock that prevents cache stampedes
(`SET NX EX 10`); ordinary reads and writes are not locked.

## 9. Failure behaviour

| Failure | Behaviour |
|---|---|
| `REDIS_URL` unset | No Redis use. Reads hit PostgreSQL; limiter is per process |
| Redis down / timeout | Cache lookups are misses (request served from PostgreSQL); after one failure Redis is skipped for 5 s so requests do not each wait for a timeout |
| Redis down, rate limit | Falls back to the per-process limiter: limits stay enforced, never fail open |
| Redis down, authentication/authorization | Not affected: never read from Redis |
| Cached JSON unreadable / wrong generation | Treated as a miss |
| Concurrent misses on one key | One builder (lock); others wait up to 2 s for its result, then build themselves |
| Builder started before an invalidation | Its result carries the old generation and is never served |

`GET /health/ready` adds `"redis": "ok" | "degraded"` only when Redis is configured; Redis never
makes the service unready.

## 10. Tests

`tests/api/test_redis.py` (needs `TEST_REDIS_URL`, local hosts only) covers: hit/miss, TTL expiry
and cap, deterministic keys, namespace invalidation, organisation isolation, secret refusal,
stampede (10 threads, one build), stale-generation write, Redis down fallback, lifecycle and
credential-free logs, rate limit shared across two "workers", atomic limit under 40 threads, no
fail-open, public CMS publish/unpublish invalidation, drafts never cached, rollback vs commit
invalidation, admin overview per user and auth when warm, partner project share/unshare and
isolation, notification queue/read-all invalidation, enquiry list and settings invalidation, and
401/403 on warm caches. With `TEST_REDIS_URL` set, `tests/conftest.py` runs the **entire** suite
with Redis enabled (a fresh namespace per app, flushed per test).

Run: `TEST_REDIS_URL=redis://127.0.0.1:6390/15 pytest` (disposable local Redis, e.g.
`docker run -d --rm -p 127.0.0.1:6390:6379 redis:7-alpine`).

## 11. Benchmark results

Measured by `scripts/bench_redis.py` on a developer machine: in-process `TestClient` (no network),
local PostgreSQL 16 and Redis 7 in Docker, 60 sequential requests per cell. Data: 150 published
content items, 440 enquiries, 40 shared projects, 1 partner organisation. Cells are mean / p50 /
p95 in milliseconds. "Miss" invalidates the namespace before every request. Hit ratio is from the
cache counters during the hit phase.

| Audience | Endpoint | Cache disabled | Cache miss (Redis on) | Cache hit | DB queries miss | DB queries hit | Hit ratio |
|---|---|---|---|---|---|---|---|
| Public | `GET /content?page_size=20` | 40.8 / 28.2 / 33.2 | 38.5 / 38.8 / 40.8 | 16.0 / 15.4 / 18.7 | 2.0 | 0.0 | 100% |
| Public | `GET /content/{slug}` | 27.6 / 27.3 / 35.0 | 32.5 / 31.9 / 36.7 | 13.7 / 13.2 / 14.6 | 2.0 | 0.0 | 100% |
| Public | `GET /content/sitemap` | 30.1 / 29.4 / 35.9 | 50.3 / 44.9 / 58.6 | 18.5 / 18.4 / 22.3 | 1.0 | 0.0 | 100% |
| Admin | `GET /admin/overview` | 42.8 / 41.5 / 47.1 | 50.1 / 48.8 / 56.4 | 20.8 / 20.8 / 23.7 | 9.0 | 1.0 | 100% |
| Admin | `GET /admin/workload` | 24.8 / 24.4 / 28.5 | 33.4 / 33.4 / 38.0 | 20.4 / 20.2 / 23.1 | 2.0 | 1.0 | 100% |
| Admin | `GET /admin/enquiries?page_size=50` | 52.6 / 52.0 / 57.8 | 73.4 / 70.6 / 88.1 | 31.7 / 31.6 / 37.6 | 5.0 | 1.0 | 100% |
| Admin | `GET /admin/enquiries?q=lead1` | 57.7 / 55.2 / 71.4 | 80.7 / 74.0 / 85.9 | 27.9 / 26.6 / 33.7 | 5.0 | 1.0 | 100% |
| Admin | `GET /admin/organizations` | 29.2 / 29.1 / 32.8 | 37.0 / 34.9 / 44.8 | 21.9 / 21.5 / 25.4 | 4.0 | 1.0 | 100% |
| Admin | `GET /admin/reports/kpis` | 58.7 / 56.4 / 68.6 | 64.1 / 62.7 / 69.7 | 22.3 / 21.8 / 25.5 | 13.0 | 1.0 | 100% |
| Partner | `GET /partner/projects` | 55.6 / 39.8 / 47.0 | 58.1 / 49.5 / 62.3 | 36.4 / 31.0 / 40.0 | 4.0 | 2.0 | 100% |
| Partner | `GET /partner/notifications` | 39.8 / 38.7 / 47.0 | 51.7 / 49.9 / 59.9 | 29.0 / 28.9 / 32.3 | 5.0 | 2.0 | 100% |
| Partner | `GET /partner/notifications/unread-count` | 28.3 / 28.3 / 31.0 | 36.2 / 35.6 / 40.9 | 26.2 / 25.8 / 29.3 | 3.0 | 2.0 | 100% |
| Partner | `GET /partner/performance/summary` | 31.4 / 30.5 / 37.4 | 36.6 / 36.1 / 41.6 | 27.3 / 27.1 / 30.1 | 3.0 | 2.0 | 100% |

Redis errors during the run: 0. Redis `used_memory` after the run: 1.30M.

Reading the numbers: a hit still pays the authentication queries (1 for staff, 2 for partners),
which is why hit queries are not 0 for protected endpoints. The gain is large where the query work
is large (KPIs: 58.7 -> 22.3 ms mean, 13 -> 1 query; enquiry list; public content). It is small for
`unread-count` and `performance/summary`, whose queries are already cheap on this data set; the
cost of a miss on Redis (extra round trips) is visible there (28.3 -> 36.2 ms). These are local,
single-client numbers: they do not include network latency to a hosted Redis/PostgreSQL, and
concurrency was not measured. Slow-query and index review was not performed in this change.

## 12. Deployment

1. Review both blueprints (`render.yaml`, `render.staging.yaml`): each declares a Key Value service
   and gives the web service and the cron `REDIS_URL` from it.
2. Apply the **staging** blueprint first (it adds a billed Key Value instance). Confirm the web
   service and cron both received `REDIS_URL`.
3. Verify live: `GET https://<staging host>/health/ready` must return `"redis": "ok"`; then call
   a cached endpoint twice and confirm the second is faster / `redis` stays `ok`; in the Render
   dashboard check the Key Value instance's connection and memory graphs.
4. Repeat for production after staging is accepted. Do not call the deployment complete before step
   3 passes on production.
5. Rollback: remove `REDIS_URL` from the service; the app returns to PostgreSQL-only reads and
   per-process limits with no code change.

**Current status: none of the above has been done.** No Redis service exists on Render for this
project from this change, and no live connection has been verified. The automated tests ran only
against a local disposable Redis (`redis://127.0.0.1:6390/15`); production Redis is never used by
tests.

## 13. Monitoring and troubleshooting

- `/health/ready` -> `redis` field (`ok` / `degraded`).
- Logs (JSON): `redis unavailable` (host + exception class), `cache invalidation failed`,
  `refused to cache payload`, `uncacheable argument`.
- `app.state.cache.stats()` -> hits, misses, bypassed, errors (per process).
- Stale data suspected: check TTL table (section 5), then whether the change went through a path
  that bypasses the ORM (needs `mark_dirty`).
- Latency after enabling Redis: check the Key Value instance region equals the web service region
  and that `REDIS_URL` is the internal URL.
- Memory: `allkeys-lru` evicts cache entries first; the generation keys are tiny. Eviction of a
  generation key is safe (a fresh generation is created, old entries are ignored).
