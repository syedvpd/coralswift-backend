"""Benchmark representative read endpoints: cache disabled vs Redis miss vs Redis hit.

Runs in-process (FastAPI TestClient, no network) against a DISPOSABLE local PostgreSQL database
(`coralswift_bench_test`, created on first run, seeded through the public/admin API) and a local
disposable Redis. Refuses any non-local host. Prints a markdown report; nothing is invented:
every number comes from this run.

  TEST_DATABASE_URL=... TEST_REDIS_URL=redis://127.0.0.1:6390/15 python scripts/bench_redis.py
"""

import os
import statistics
import sys
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import redis as redis_lib  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from dotenv import dotenv_values  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pydantic import SecretStr  # noqa: E402
from sqlalchemy import create_engine, event, make_url, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.cache_hooks import (  # noqa: E402
    NS_ADMIN_ENQUIRIES,
    NS_ADMIN_ORGS,
    NS_ADMIN_OVERVIEW,
    NS_ADMIN_REPORTS,
    NS_PUBLIC_CONTENT,
    ns_notif,
    ns_org,
)
from app.core.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.modules.auth.constants import StaffRole  # noqa: E402
from tests import factories  # noqa: E402
from tests.fakes import InMemoryStorage, RecordingEmail  # noqa: E402
from tests.helpers import bearer, login, make_staff, onboard_partner  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
N = int(os.environ.get("BENCH_REQUESTS", "60"))
CONTENT, ENQUIRIES, PROJECTS, NOTIFS = 150, 400, 40, 40
PREFIX = "bench"


def env(name: str) -> str:
    value = os.environ.get(name) or dotenv_values(ROOT / ".env").get(name)
    if not value:
        sys.exit(f"{name} is not set")
    return value


def bench_db_url() -> str:
    url = make_url(env("TEST_DATABASE_URL"))
    if url.host not in ("localhost", "127.0.0.1"):
        sys.exit("refusing non-local database")
    name = "coralswift_bench_test"
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        if not conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname=:n"), {"n": name}
        ).first():
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()
    return url.set(database=name).render_as_string(hide_password=False)


def make_settings(db_url: str, redis_url: str | None) -> Settings:
    return Settings(
        _env_file=None,
        app_env="testing",
        database_url=SecretStr(db_url),
        secret_key=SecretStr("bench-secret-key-not-for-production"),
        allowed_hosts=["testserver"],
        log_level="ERROR",
        rate_limit_per_minute=0,
        password_time_cost=1,
        password_memory_kib=8,
        redis_url=SecretStr(redis_url) if redis_url else None,
        redis_key_prefix=PREFIX,
    )


def seed(
    client: TestClient, session: Session, settings: Settings, mail: RecordingEmail
) -> dict[str, Any]:
    ca = bearer(
        login(client, make_staff(session, settings, StaffRole.CONTENT_ADMINISTRATOR).email)[
            "access_token"
        ]
    )
    sa_user = make_staff(session, settings, StaffRole.SUPER_ADMINISTRATOR)
    sa = bearer(login(client, sa_user.email)["access_token"])
    ad = "/api/v1/admin/content"
    run = uuid.uuid4().hex[:6]
    slugs = []
    for i in range(CONTENT):
        slug = f"bench-{run}-{i}"
        body = {
            "slug": slug,
            "content_type": "faq",
            "title": f"Question {i}?",
            "summary": "Benchmark summary",
            "body": "Benchmark body. " * 40,
            "category": "benchmark",
            "tags": ["bench"],
        }
        iid = client.post(ad, headers=ca, json=body).json()["data"]["id"]
        client.post(f"{ad}/{iid}/submit", headers=ca)
        client.post(f"{ad}/{iid}/approve", headers=sa, json={})
        client.post(f"{ad}/{iid}/publish", headers=ca)
        slugs.append(slug)
    partner = onboard_partner(
        client, session, settings, mail, org_name=f"Bench {run} Ltd", admin=sa_user
    )
    for i in range(ENQUIRIES):
        client.post(
            "/api/v1/enquiries/contact",
            json=factories.contact(business_email=f"lead{i}-{run}@example.com"),
        )
    for _ in range(NOTIFS):
        client.post(
            "/api/v1/enquiries/contact", json=factories.contact(business_email=partner.email)
        )
    for i in range(PROJECTS):
        r = client.post(
            "/api/v1/reviewer/projects",
            headers=sa,
            json={
                "organization_id": partner.organization_id,
                "title": f"Project {i}",
                "category": "it_services",
                "contact_name": "Ravi Kumar",
            },
        )
        client.post(f"/api/v1/reviewer/projects/{r.json()['data']['id']}/share", headers=sa)
    return {"sa": sa, "partner": partner, "slug": slugs[0], "org": partner.organization_id}


def run_endpoint(client: TestClient, url: str, headers: dict[str, str], before: Any) -> list[float]:
    times = []
    for _ in range(N):
        before()
        t0 = time.perf_counter()
        r = client.get(url, headers=headers)
        times.append((time.perf_counter() - t0) * 1000)
        if r.status_code != 200:
            sys.exit(f"{url} -> {r.status_code}: {r.text[:200]}")
    return times


def stats(times: list[float]) -> str:
    s = sorted(times)
    return f"{statistics.mean(s):.1f} / {s[len(s) // 2]:.1f} / {s[int(len(s) * 0.95) - 1]:.1f}"


def main() -> None:
    redis_url = env("TEST_REDIS_URL")
    if urlsplit(redis_url).hostname not in ("localhost", "127.0.0.1"):
        sys.exit("refusing non-local Redis")
    db_url = bench_db_url()
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    os.environ["DATABASE_URL"] = db_url
    os.environ["SECRET_KEY"] = "bench-secret-key-not-for-production"  # noqa: S105
    command.upgrade(cfg, "head")

    raw = redis_lib.Redis.from_url(redis_url, decode_responses=True)
    for k in raw.scan_iter(f"{PREFIX}:*"):
        raw.delete(k)

    mail = RecordingEmail()

    def build(with_redis: bool) -> Any:
        s = make_settings(db_url, redis_url if with_redis else None)
        app = create_app(s, storage=InMemoryStorage(), email_sender=mail)
        return s, app

    s_on, app_on = build(True)
    queries = [0]
    event.listen(
        app_on.state.engine,
        "before_cursor_execute",
        lambda *a: queries.__setitem__(0, queries[0] + 1),
    )
    s_off, app_off = build(False)
    ctx: dict[str, Any] = {}
    with TestClient(app_on) as c_on, TestClient(app_off) as c_off:
        sess = app_on.state.sessionmaker()
        ctx = seed(c_on, sess, s_on, mail)
        sess.close()
        sa, partner = ctx["sa"], ctx["partner"].headers
        # logins happened above on app_on; the same bearer tokens are valid on app_off (same DB)
        cache = app_on.state.cache
        pemail = ctx["partner"].email
        eps = [
            (
                "Public",
                "GET /content?page_size=20",
                "/api/v1/content?page_size=20",
                {},
                [NS_PUBLIC_CONTENT],
            ),
            (
                "Public",
                "GET /content/{slug}",
                f"/api/v1/content/{ctx['slug']}",
                {},
                [NS_PUBLIC_CONTENT],
            ),
            ("Public", "GET /content/sitemap", "/api/v1/content/sitemap", {}, [NS_PUBLIC_CONTENT]),
            ("Admin", "GET /admin/overview", "/api/v1/admin/overview", sa, [NS_ADMIN_OVERVIEW]),
            ("Admin", "GET /admin/workload", "/api/v1/admin/workload", sa, [NS_ADMIN_OVERVIEW]),
            (
                "Admin",
                "GET /admin/enquiries?page_size=50",
                "/api/v1/admin/enquiries?page_size=50",
                sa,
                [NS_ADMIN_ENQUIRIES],
            ),
            (
                "Admin",
                "GET /admin/enquiries?q=lead1",
                "/api/v1/admin/enquiries?q=lead1&page_size=50",
                sa,
                [NS_ADMIN_ENQUIRIES],
            ),
            (
                "Admin",
                "GET /admin/organizations",
                "/api/v1/admin/organizations",
                sa,
                [NS_ADMIN_ORGS],
            ),
            (
                "Admin",
                "GET /admin/reports/kpis",
                "/api/v1/admin/reports/kpis",
                sa,
                [NS_ADMIN_REPORTS],
            ),
            (
                "Partner",
                "GET /partner/projects",
                "/api/v1/partner/projects?page_size=50",
                partner,
                [ns_org(ctx["org"], "projects")],
            ),
            (
                "Partner",
                "GET /partner/notifications",
                "/api/v1/partner/notifications",
                partner,
                [ns_notif(pemail)],
            ),
            (
                "Partner",
                "GET /partner/notifications/unread-count",
                "/api/v1/partner/notifications/unread-count",
                partner,
                [ns_notif(pemail)],
            ),
            (
                "Partner",
                "GET /partner/performance/summary",
                "/api/v1/partner/performance/summary",
                partner,
                [ns_org(ctx["org"], "performance")],
            ),
        ]
        rows = []
        for audience, label, url, headers, nss in eps:
            off = run_endpoint(c_off, url, headers, lambda: None)
            queries[0] = 0
            miss = run_endpoint(
                c_on, url, headers, lambda nss=nss: [cache.invalidate(n) for n in nss]
            )
            q_miss = queries[0] / N
            c_on.get(url, headers=headers)  # warm
            queries[0] = 0
            before = dict(cache.stats())
            hit = run_endpoint(c_on, url, headers, lambda: None)
            q_hit = queries[0] / N
            after = cache.stats()
            ratio = (after["hits"] - before["hits"]) / N
            rows.append(
                (audience, label, stats(off), stats(miss), stats(hit), q_miss, q_hit, ratio)
            )
        errors = cache.stats()["errors"]
    info: Any = raw.info("memory")
    mem = info["used_memory_human"]
    print(
        f"Benchmark run: {time.strftime('%Y-%m-%d %H:%M')} UTC-local, {N} sequential requests per cell, in-process TestClient."
    )
    print(
        f"Data: {CONTENT} published content items, {ENQUIRIES + NOTIFS} enquiries, {PROJECTS} shared projects, 1 partner org."
    )
    print(
        "Latency cells are mean / p50 / p95 in ms. DB queries are statements per request (app engine).\n"
    )
    print(
        "| Audience | Endpoint | Cache disabled | Cache miss (Redis on) | Cache hit | DB queries miss | DB queries hit | Hit ratio (hit phase) |"
    )
    print("|---|---|---|---|---|---|---|---|")
    for a, lbl, lat_off, lat_miss, lat_hit, qm, qh, ratio in rows:
        print(
            f"| {a} | `{lbl}` | {lat_off} | {lat_miss} | {lat_hit} | {qm:.1f} | {qh:.1f} | {ratio:.0%} |"
        )
    print(f"\nRedis errors during run: {errors}. Redis used_memory after run: {mem}.")
    for k in raw.scan_iter(f"{PREFIX}:*"):
        raw.delete(k)


if __name__ == "__main__":
    main()
