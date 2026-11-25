"""Redis infrastructure: cache, invalidation, distributed rate limit, failure fallback.

Needs a DISPOSABLE Redis: TEST_REDIS_URL (env or .env) on localhost, e.g.
redis://127.0.0.1:6390/15. Each test uses its own key prefix and deletes only its own keys.
"""

import os
import threading
import time
import uuid
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlsplit

import pytest
import redis as redis_lib
from dotenv import dotenv_values
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.cache import CacheService
from app.core.config import Settings
from app.core.protection import DistributedLimiter, FixedWindowLimiter
from app.core.redis import RedisManager
from app.modules.auth.constants import StaffRole
from app.modules.content.models import ContentItem
from tests import factories
from tests.api.test_content_engagement import AC, PC, new_item, staff
from tests.conftest import ROOT, AppFactory
from tests.fakes import RecordingEmail
from tests.helpers import make_staff, onboard_partner, staff_headers


@pytest.fixture(scope="module")
def redis_url() -> str:
    url = os.environ.get("TEST_REDIS_URL") or dotenv_values(ROOT / ".env").get("TEST_REDIS_URL")
    if not url:
        pytest.skip("TEST_REDIS_URL not set")
    # Guard: never run against a non-local Redis.
    assert urlsplit(url).hostname in ("localhost", "127.0.0.1", "::1"), (
        "TEST_REDIS_URL must be local"
    )
    return url


@pytest.fixture
def prefix(redis_url: str) -> Iterator[str]:
    p = f"t{uuid.uuid4().hex[:10]}"
    yield p
    raw: Any = redis_lib.Redis.from_url(redis_url, decode_responses=True)
    for key in raw.scan_iter(f"{p}:*"):
        raw.delete(key)
    raw.close()


@pytest.fixture
def rsettings(settings: Settings, redis_url: str, prefix: str) -> Settings:
    return settings.model_copy(
        update={"redis_url": SecretStr(redis_url), "redis_key_prefix": prefix}
    )


@pytest.fixture
def cache(rsettings: Settings) -> Iterator[CacheService]:
    manager = RedisManager(rsettings)
    yield CacheService(manager, rsettings)
    manager.close()


@pytest.fixture
def rapp(app_factory: AppFactory, redis_url: str, prefix: str) -> FastAPI:
    return app_factory(redis_url=SecretStr(redis_url), redis_key_prefix=prefix)


@pytest.fixture
def rclient(rapp: FastAPI) -> Iterator[TestClient]:
    with TestClient(rapp, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def rdb(rapp: FastAPI) -> Iterator[Session]:
    s: Session = rapp.state.sessionmaker()
    yield s
    s.close()


R = "/api/v1/reviewer"
P = "/api/v1/partner"


# ------------------------------------------------------------ cache service
def test_hit_miss_and_deterministic_key(cache: CacheService) -> None:
    calls: list[int] = []

    def build() -> dict[str, Any]:
        calls.append(1)
        return {"n": len(calls)}

    assert cache.get_or_set("ns", {"a": 1, "b": 2}, 60, build) == {"n": 1}
    assert cache.get_or_set("ns", {"b": 2, "a": 1}, 60, build) == {"n": 1}  # same key, any order
    assert len(calls) == 1 and cache.stats()["hits"] == 1 and cache.stats()["misses"] == 1
    assert cache.key("ns", {"a": 1, "b": 2}) == cache.key("ns", {"b": 2, "a": 1})


def test_ttl_expiry(cache: CacheService) -> None:
    n = [0]

    def build() -> int:
        n[0] += 1
        return n[0]

    assert cache.get_or_set("ns", {}, 1, build) == 1
    time.sleep(1.2)
    assert cache.get_or_set("ns", {}, 1, build) == 2


def test_ttl_is_capped(rsettings: Settings, cache: CacheService, redis_url: str) -> None:
    cache.get_or_set("ns", {}, 10**9, lambda: 1)
    raw: Any = redis_lib.Redis.from_url(redis_url)
    assert 0 < raw.ttl(cache.key("ns", {})) <= rsettings.cache_max_ttl_seconds
    raw.close()


def test_invalidate_namespace_only(cache: CacheService) -> None:
    cache.get_or_set("a", {}, 60, lambda: "old")
    cache.get_or_set("b", {}, 60, lambda: "keep")
    cache.invalidate("a")
    assert cache.get_or_set("a", {}, 60, lambda: "new") == "new"
    assert cache.get_or_set("b", {}, 60, lambda: "changed") == "keep"


def test_delete_and_exists(cache: CacheService) -> None:
    cache.get_or_set("a", {"k": 1}, 60, lambda: 1)
    assert cache.exists("a", {"k": 1})
    cache.delete("a", {"k": 1})
    assert not cache.exists("a", {"k": 1})


def test_organisation_keys_are_isolated(cache: CacheService) -> None:
    org_a, org_b = str(uuid.uuid4()), str(uuid.uuid4())
    assert cache.get_or_set("partner", {"org": org_a}, 60, lambda: "A-data") == "A-data"
    assert cache.get_or_set("partner", {"org": org_b}, 60, lambda: "B-data") == "B-data"
    assert cache.get_or_set("partner", {"org": org_a}, 60, lambda: "x") == "A-data"


def test_secret_payload_is_refused(cache: CacheService) -> None:
    calls = [0]

    def build() -> dict[str, Any]:
        calls[0] += 1
        return {"data": {"access_token": "abc"}}

    cache.get_or_set("auth", {}, 60, build)
    cache.get_or_set("auth", {}, 60, build)
    assert calls[0] == 2 and not cache.exists("auth", {})


def test_secret_field_detection() -> None:
    from app.core.cache import _secret_name

    for bad in ("access_token", "refreshToken", "signed_url", "Password", "mfa_secret", "api_key"):
        assert _secret_name(bad), bad
    for ok_name in ("unassigned_enquiries", "unassigned_applications", "status", "title"):
        assert not _secret_name(ok_name), ok_name


def test_stampede_single_builder(cache: CacheService) -> None:
    calls = [0]
    lock = threading.Lock()

    def build() -> str:
        with lock:
            calls[0] += 1
        time.sleep(0.4)
        return "v"

    results: list[Any] = []
    threads = [
        threading.Thread(target=lambda: results.append(cache.get_or_set("s", {}, 60, build)))
        for _ in range(10)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == ["v"] * 10 and calls[0] == 1


def test_stale_generation_write_is_ignored(cache: CacheService) -> None:
    """A builder that started before an invalidation must not poison the new generation."""

    def build() -> str:
        cache.invalidate("g")  # commit lands while the builder is running
        return "stale"

    cache.get_or_set("g", {}, 60, build)
    assert cache.get_or_set("g", {}, 60, lambda: "fresh") == "fresh"


def test_redis_down_falls_back_to_build(rsettings: Settings) -> None:
    dead = rsettings.model_copy(update={"redis_url": SecretStr("redis://127.0.0.1:1/0")})
    manager = RedisManager(dead)
    svc = CacheService(manager, dead)
    assert svc.get_or_set("ns", {}, 60, lambda: {"ok": 1}) == {"ok": 1}
    assert svc.errors == 1 and not manager.ping()
    svc.invalidate("ns")  # must not raise
    manager.close()


def test_disabled_without_url(settings: Settings) -> None:
    plain = settings.model_copy(update={"redis_url": None})
    manager = RedisManager(plain)
    svc = CacheService(manager, plain)
    assert not manager.enabled and svc.get_or_set("ns", {}, 60, lambda: 7) == 7
    assert svc.stats()["bypassed"] == 1


def test_lifecycle_and_logs_hide_credentials(
    rsettings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    secret = rsettings.model_copy(
        update={"redis_url": SecretStr("redis://user:s3cr3tpw@127.0.0.1:1/0")}
    )
    manager = RedisManager(secret)
    with caplog.at_level("INFO"):
        manager.start()
    assert "s3cr3tpw" not in caplog.text
    manager.close()
    healthy = RedisManager(rsettings)
    assert healthy.ping()
    healthy.close()
    assert healthy._client is None  # noqa: SLF001


# ----------------------------------------------------------- rate limiting
def test_distributed_limit_is_shared_across_workers(rsettings: Settings) -> None:
    w1, w2 = RedisManager(rsettings), RedisManager(rsettings)
    a = DistributedLimiter(w1, FixedWindowLimiter())
    b = DistributedLimiter(w2, FixedWindowLimiter())
    assert [
        a.check("login:1.2.3.4", 3),
        b.check("login:1.2.3.4", 3),
        a.check("login:1.2.3.4", 3),
    ] == [
        None,
        None,
        None,
    ]
    retry = b.check("login:1.2.3.4", 3)
    assert retry is not None and 1 <= retry <= 60
    assert a.check("login:9.9.9.9", 3) is None  # other client unaffected
    w1.close()
    w2.close()


def test_distributed_limit_is_atomic_under_concurrency(rsettings: Settings) -> None:
    manager = RedisManager(rsettings)
    limiter = DistributedLimiter(manager, FixedWindowLimiter())
    out: list[int | None] = []
    threads = [
        threading.Thread(target=lambda: out.append(limiter.check("burst", 5))) for _ in range(40)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert out.count(None) == 5
    manager.close()


def test_limiter_does_not_fail_open_when_redis_down(rsettings: Settings) -> None:
    dead = RedisManager(
        rsettings.model_copy(update={"redis_url": SecretStr("redis://127.0.0.1:1/0")})
    )
    limiter = DistributedLimiter(dead, FixedWindowLimiter())
    assert [limiter.check("k", 2) for _ in range(3)][2] is not None


# ------------------------------------------------------------ API behaviour
def _publish(
    client: TestClient, db: Session, settings: Settings, slug: str
) -> tuple[str, dict[str, str]]:
    ca = staff(client, db, settings, StaffRole.CONTENT_ADMINISTRATOR)
    sa = staff(client, db, settings, StaffRole.SUPER_ADMINISTRATOR)
    item = new_item(client, ca, slug=slug)
    assert client.post(f"{AC}/{item}/submit", headers=ca).status_code == 200
    assert client.post(f"{AC}/{item}/approve", headers=sa, json={}).status_code == 200
    assert client.post(f"{AC}/{item}/publish", headers=ca).status_code == 200
    return item, ca


def test_readiness_reports_redis(rclient: TestClient, app_factory: AppFactory) -> None:
    assert rclient.get("/health/ready").json()["data"]["redis"] == "ok"
    with TestClient(app_factory(redis_url=None)) as plain:
        assert "redis" not in plain.get("/health/ready").json()["data"]  # contract unchanged


def test_public_content_cached_and_invalidated_on_unpublish(
    rclient: TestClient, rapp: FastAPI, rdb: Session, settings: Settings
) -> None:
    item, ca = _publish(rclient, rdb, settings, "cache-me")
    cache: CacheService = rapp.state.cache
    first = rclient.get(f"{PC}/cache-me")
    base = cache.stats()["hits"]
    second = rclient.get(f"{PC}/cache-me")
    assert first.json() == second.json() and cache.stats()["hits"] == base + 1
    assert rclient.get(PC).json()["data"][0]["slug"] == "cache-me"
    assert rclient.post(f"{AC}/{item}/unpublish", headers=ca).status_code == 200
    assert rclient.get(f"{PC}/cache-me").status_code == 404  # gone immediately, not after TTL
    assert rclient.get(PC).json()["data"] == []
    assert rclient.get(f"{PC}/sitemap").json()["data"] == []


def test_drafts_never_enter_public_cache(
    rclient: TestClient, rdb: Session, settings: Settings, redis_url: str, prefix: str
) -> None:
    ca = staff(rclient, rdb, settings, StaffRole.CONTENT_ADMINISTRATOR)
    new_item(rclient, ca, slug="draft-only")
    assert rclient.get(f"{PC}/draft-only").status_code == 404
    assert rclient.get(PC).json()["data"] == []
    raw: Any = redis_lib.Redis.from_url(redis_url, decode_responses=True)
    values = [
        raw.get(k)
        for k in raw.scan_iter(f"{prefix}:v1:public-content:*")
        if not k.endswith(":lock")
    ]
    raw.close()
    assert not any("draft-only" in (v or "") for v in values)


def test_rollback_does_not_invalidate_commit_does(
    rclient: TestClient,
    rapp: FastAPI,
    rdb: Session,
    settings: Settings,
    redis_url: str,
    prefix: str,
) -> None:
    item, _ = _publish(rclient, rdb, settings, "tx-check")
    rclient.get(f"{PC}/tx-check")
    raw: Any = redis_lib.Redis.from_url(redis_url, decode_responses=True)
    gen_key = f"{prefix}:g:public-content"
    before = raw.get(gen_key)
    row = rdb.execute(select(ContentItem).where(ContentItem.slug == "tx-check")).scalar_one()
    row.title = "changed"
    rdb.flush()
    rdb.rollback()
    assert raw.get(gen_key) == before
    row = rdb.execute(select(ContentItem).where(ContentItem.slug == "tx-check")).scalar_one()
    row.title = "changed"
    rdb.commit()
    assert raw.get(gen_key) != before
    raw.close()


def test_admin_overview_cached_per_user_and_auth_still_enforced(
    rclient: TestClient, rapp: FastAPI, rdb: Session, settings: Settings
) -> None:
    h1 = staff_headers(rclient, make_staff(rdb, settings, StaffRole.SUPER_ADMINISTRATOR))
    h2 = staff_headers(rclient, make_staff(rdb, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER))
    cache: CacheService = rapp.state.cache
    url = "/api/v1/admin/overview"
    assert rclient.get(url, headers=h1).status_code == 200
    base = cache.stats()["hits"]
    assert rclient.get(url, headers=h1).status_code == 200
    assert cache.stats()["hits"] == base + 1
    sa_view = rclient.get(url, headers=h1).json()["data"]
    reviewer_view = rclient.get(url, headers=h2).json()["data"]
    assert "failed_notifications" in sa_view and reviewer_view.get("failed_notifications") is None
    assert rclient.get(url).status_code == 401  # warm cache does not bypass authentication


def test_auth_responses_are_never_cached(
    rclient: TestClient, rdb: Session, settings: Settings, redis_url: str, prefix: str
) -> None:
    user = make_staff(rdb, settings, StaffRole.SUPER_ADMINISTRATOR)
    staff_headers(rclient, user)
    raw: Any = redis_lib.Redis.from_url(redis_url, decode_responses=True)
    keys = [k for k in raw.scan_iter(f"{prefix}:v1:*")]
    raw.close()
    assert keys == []


def test_redis_outage_serves_from_database(
    app_factory: AppFactory, rdb: Session, settings: Settings
) -> None:
    app = app_factory(redis_url=SecretStr("redis://127.0.0.1:1/0"))
    with TestClient(app, raise_server_exceptions=False) as c:
        sess: Session = app.state.sessionmaker()
        _publish(c, sess, settings, "no-redis")
        assert c.get(f"{PC}/no-redis").status_code == 200
        assert c.get("/health/ready").json()["data"]["redis"] == "degraded"
        sess.close()


# ------------------------------------------------- wider coverage (partner/admin)
def _hits(app: FastAPI) -> int:
    cache: CacheService = app.state.cache
    return cache.stats()["hits"]


def _new_project(client: TestClient, sa: dict[str, str], org_id: str) -> str:
    r = client.post(
        f"{R}/projects",
        headers=sa,
        json={
            "organization_id": org_id,
            "title": "Pilot dispatch",
            "category": "it_services",
            "contact_name": "Ravi Kumar",
        },
    )
    assert r.status_code == 201, r.text
    return str(r.json()["data"]["id"])


def test_partner_project_list_cached_isolated_and_invalidated_on_share(
    rclient: TestClient, rapp: FastAPI, rdb: Session, settings: Settings, email: RecordingEmail
) -> None:
    sa = staff_headers(rclient, make_staff(rdb, settings, StaffRole.SUPER_ADMINISTRATOR))
    a = onboard_partner(rclient, rdb, settings, email, org_name="Alpha Ltd")
    b = onboard_partner(rclient, rdb, settings, email, org_name="Bravo Ltd")
    pid = _new_project(rclient, sa, a.organization_id)
    assert rclient.get(f"{P}/projects", headers=a.headers).json()["data"] == []
    base = _hits(rapp)
    assert rclient.get(f"{P}/projects", headers=a.headers).json()["data"] == []
    assert _hits(rapp) == base + 1  # served from Redis
    assert rclient.post(f"{R}/projects/{pid}/share", headers=sa).status_code == 200
    mine = rclient.get(f"{P}/projects", headers=a.headers).json()
    assert mine["meta"]["total"] == 1  # share invalidated the cached empty list at once
    assert rclient.get(f"{P}/projects", headers=b.headers).json()["data"] == []  # other org
    assert rclient.get(f"{P}/projects", headers=b.headers).json()["data"] == []  # cached, still b's
    assert rclient.post(f"{R}/projects/{pid}/unshare", headers=sa).status_code == 200
    assert rclient.get(f"{P}/projects", headers=a.headers).json()["data"] == []


def test_notification_counts_invalidate_and_isolate(
    rclient: TestClient, rapp: FastAPI, rdb: Session, settings: Settings, email: RecordingEmail
) -> None:
    a = onboard_partner(rclient, rdb, settings, email, org_name="Inbox A Ltd")
    b = onboard_partner(rclient, rdb, settings, email, org_name="Inbox B Ltd")
    url = f"{P}/notifications/unread-count"

    def count(who: Any) -> int:
        return int(rclient.get(url, headers=who.headers).json()["data"]["unread"])

    start = count(a)
    base = _hits(rapp)
    assert count(a) == start and _hits(rapp) == base + 1
    rclient.post("/api/v1/enquiries/contact", json=factories.contact(business_email=a.email))
    assert count(a) == start + 1  # queue_notification (core INSERT) invalidated the cache
    assert count(b) == 0  # never a's count
    assert rclient.post(f"{P}/notifications/read-all", headers=a.headers).status_code == 200
    assert count(a) == 0  # bulk UPDATE invalidated the cache
    assert rclient.get(url).status_code == 401


def test_admin_enquiry_list_and_settings_invalidate_on_change(
    rclient: TestClient, rapp: FastAPI, rdb: Session, settings: Settings
) -> None:
    sa = staff_headers(rclient, make_staff(rdb, settings, StaffRole.SUPER_ADMINISTRATOR))
    listing = "/api/v1/admin/enquiries"
    assert rclient.get(listing, headers=sa).json()["meta"]["total"] == 0
    base = _hits(rapp)
    assert rclient.get(listing, headers=sa).json()["meta"]["total"] == 0
    assert _hits(rapp) == base + 1
    assert rclient.post("/api/v1/enquiries/contact", json=factories.contact()).status_code == 201
    assert rclient.get(listing, headers=sa).json()["meta"]["total"] == 1  # new enquiry visible now

    key = "security.login_lockout_minutes"
    first = rclient.get("/api/v1/admin/settings", headers=sa).json()["data"]["values"]
    assert key not in first
    rclient.get("/api/v1/admin/settings", headers=sa)  # warm
    assert (
        rclient.put(f"/api/v1/admin/settings/{key}", headers=sa, json={"value": "20"}).status_code
        == 200
    )
    assert rclient.get("/api/v1/admin/settings", headers=sa).json()["data"]["values"][key] == "20"
    assert rclient.delete(f"/api/v1/admin/settings/{key}", headers=sa).status_code == 200
    assert key not in rclient.get("/api/v1/admin/settings", headers=sa).json()["data"]["values"]


def test_cached_endpoints_enforce_auth_and_role_even_when_warm(
    rclient: TestClient, rdb: Session, settings: Settings, email: RecordingEmail
) -> None:
    sa = staff_headers(rclient, make_staff(rdb, settings, StaffRole.SUPER_ADMINISTRATOR))
    partner = onboard_partner(rclient, rdb, settings, email, org_name="Warm Ltd")
    cases = [
        (f"{P}/projects", partner.headers, sa),
        (f"{P}/notifications", partner.headers, sa),
        ("/api/v1/admin/enquiries", sa, partner.headers),
        ("/api/v1/admin/settings", sa, partner.headers),
    ]
    for url, allowed, wrong in cases:
        assert rclient.get(url, headers=allowed).status_code == 200  # warm
        assert rclient.get(url, headers=allowed).status_code == 200
        assert rclient.get(url).status_code == 401
        assert rclient.get(url, headers=wrong).status_code == 403
