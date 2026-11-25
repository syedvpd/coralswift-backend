"""List every registered route with audience, auth, role and Redis status (read-only).

Usage: python scripts/route_inventory.py [--json | --markdown]
Builds the app with dummy settings; opens no database or Redis connection.
`--markdown` is the source of docs/REDIS-ENDPOINT-COVERAGE.md.
"""

import inspect
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.routing import APIRoute, _IncludedRouter  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

# function name -> (namespace, invalidated by). Every @cached_read function must be listed here.
CACHED: dict[str, tuple[str, str]] = {
    "list_public": ("public-content", "any ContentItem commit (publish/update/unpublish/archive)"),
    "sitemap": ("public-content", "any ContentItem commit"),
    "get_public": (
        "public-content",
        "any ContentItem commit; unpublished slug = 404, never stored",
    ),
    "overview": ("admin-overview", "Enquiry or PortalApplication commit; TTL"),
    "workload": ("admin-overview", "Enquiry or PortalApplication commit; TTL"),
    "list_enquiries": (
        "admin-enquiries",
        "Enquiry/Contact/ProjectEnquiry/StrategicEnquiry commit; TTL (assignee names: TTL only)",
    ),
    "list_orgs": ("admin-orgs", "PartnerOrganization or PortalApplication commit; TTL"),
    "list_settings": ("admin-settings", "SystemSetting write/delete (explicit mark_dirty)"),
    "kpis": (
        "admin-reports",
        "Enquiry/EnquiryFollowUp/PartnerDocumentVersion/Notification commit; TTL",
    ),
    "follow_up_report": ("admin-reports", "Enquiry/EnquiryFollowUp commit; TTL"),
    "document_review_report": ("admin-reports", "PartnerDocumentVersion commit; TTL"),
    "communication_report": ("admin-reports", "Notification queue/status change; TTL"),
    "my_notifications": (
        "notif:<recipient hash>",
        "Notification created (queue_notification), read/unread, read-all, erasure",
    ),
    "unread_count": ("notif:<recipient hash>", "same as my_notifications"),
    "list_projects": (
        "po:<org>:projects",
        "PartnerProject commit for that org (create/share/unshare/update)",
    ),
    "summary": ("po:<org>:performance", "PerformanceEntry commit for that org (publish/edit)"),
    "trends": ("po:<org>:performance", "PerformanceEntry commit for that org"),
    "scorecards": ("po:<org>:performance", "PerformanceEntry commit for that org"),
}
MANUAL_CACHED = {"list_public", "sitemap", "get_public", "overview"}  # hand-written cache calls

_STATIC = r"^/api/v1/(catalog|site)/|^/api/v1/meta$|^/$"
RULES: list[tuple[str, str]] = [
    (r"^/health", "Liveness/readiness reflect live state; /health/ready pings Redis (never fails)"),
    (r"(download|/file)$|\.csv$", "File/export bytes: private or streamed; never stored in Redis"),
    (r"^/api/v1/auth", "Session/token/identity state; never cached (no cached authorization)"),
    (r"/audit", "Audit trail must show new events immediately (explicitly excluded)"),
    (_STATIC, "Static in-process data, no database query; HTTP Cache-Control only"),
    (r"/enquiries/\{reference_number\}/status", "Private lookup by reference + token; not shared"),
    (
        r"documents|document-requests",
        "Private document metadata: permissions/scan status per request",
    ),
    (r"^/api/v1/reviewer/", "Reviewer/BDM views are assignment-scoped (D45) and review-critical"),
    (
        r"^/api/v1/partner/(messages|discussions|meetings|follow-ups)",
        "Mutable shared inbox, many writers",
    ),
    (
        r"^/api/v1/partner/applications",
        "Derived from several tables (requests, history, decision text); invalidation not provably complete",
    ),
    (
        r"^/api/v1/partner/(organization|team|onboarding|privacy-requests|"
        r"notification-preferences|account-closure|performance|enquiries|projects/)",
        "Profile/account/permission state or multi-table detail; freshness over hit rate",
    ),
    (
        r"^/api/v1/admin/.*\{",
        "Admin detail joining notes/activity/documents; read-your-writes expected",
    ),
    (r"^/api/v1/admin/", "Admin working list/config: low repetition or read-your-writes expected"),
]
DEFAULT_REASON = (
    "Evaluated, not cached: per-request authorization/ownership checks, correctness first"
)
WRITE_REASON = "State-changing: never cached; commits invalidate via the ORM hook (watched models)"


def _walk(dep: Any, out: list[Any]) -> None:
    for sub in dep.dependencies:
        if sub.call is not None:
            out.append(sub.call)
        _walk(sub, out)


def _walk_routes(router: Any, prefix: str = "") -> list[tuple[str, APIRoute]]:
    """Flatten nested includes (FastAPI includes routers lazily)."""
    found: list[tuple[str, APIRoute]] = []
    for route in router.routes:
        if isinstance(route, _IncludedRouter):
            found += _walk_routes(route.original_router, prefix + route.include_context.prefix)
        elif isinstance(route, APIRoute):
            found.append((prefix + route.path, route))
    return found


def _row(path: str, route: APIRoute, method: str) -> dict[str, Any]:
    calls: list[Any] = []
    _walk(route.dependant, calls)
    names = [getattr(c, "__name__", "") for c in calls]
    quals = [getattr(c, "__qualname__", "") for c in calls]
    roles: set[str] = set()
    for c in calls:
        allowed = getattr(c, "allowed_roles", None)
        if allowed:
            roles |= {r.value for r in allowed}
    if "require_partner" in names:
        auth, audience = "partner session", "partner"
    elif any(n == "dependency" and "require_staff" in q for n, q in zip(names, quals, strict=True)):
        auth, audience = "staff session", "admin"
    elif "get_auth" in names:
        auth = "any session"
        audience = "admin" if path.startswith("/api/v1/admin") else "authenticated"
    else:
        auth, audience = "none", "public"
    return {
        "method": method,
        "path": path,
        "module": route.endpoint.__module__.removeprefix("app.modules."),
        "audience": audience,
        "auth": auth,
        "roles": sorted(roles) or ("any staff" if audience == "admin" else "-"),
        "org_scoped": "require_partner" in names,
        "rate_limited": any(q.startswith("rate_limit.") for q in quals),
        "bot_check": "require_human" in names,
        "function": route.endpoint.__name__,
        "doc": (inspect.getdoc(route.endpoint) or route.summary or "").split("\n")[0],
    }


def _classify(row: dict[str, Any], fn: Any) -> dict[str, str]:
    caps = ["rate limit (Redis, shared)"] if row["rate_limited"] else []
    if row["path"] == "/health/ready":
        caps.append("ping")
    cap = ", ".join(caps) or "-"
    name = row["function"]
    wrapped = hasattr(fn, "cache_meta") or name in MANUAL_CACHED
    if row["method"] == "GET" and wrapped:
        ns, inval = CACHED[name]
        setting: str = getattr(fn, "cache_meta", {}).get("ttl_setting", "")
        if name in ("list_public", "sitemap", "get_public"):
            setting = "cache_public_content_ttl_seconds"
        elif name == "overview":
            setting = "cache_admin_overview_ttl_seconds"
        ttl = Settings.model_fields[setting].default
        return {
            "redis": "cached",
            "cap": ", ".join(["cache " + ns, *caps]),
            "ttl": f"{ttl}s",
            "inval": inval,
            "reason": "-",
        }
    if row["method"] != "GET":
        reason = WRITE_REASON
    else:
        reason = next((r for pat, r in RULES if re.search(pat, row["path"])), DEFAULT_REASON)
    return {"redis": "no-cache", "cap": cap, "ttl": "-", "inval": "-", "reason": reason}


def inventory() -> list[dict[str, Any]]:
    settings = Settings(
        _env_file=None,
        app_env="testing",
        database_url="postgresql+psycopg://x:x@localhost/x_test",
        secret_key="inventory-only",  # noqa: S106
    )
    app = create_app(settings)
    found = _walk_routes(app.router)
    rows = []
    for path, route in found:
        for method in sorted((route.methods or set()) - {"HEAD", "OPTIONS"}):
            row = _row(path, route, method)
            row["c"] = _classify(row, route.endpoint)
            rows.append(row)
    return sorted(rows, key=lambda r: (r["path"], r["method"]))


def markdown() -> str:
    rows = inventory()
    cached = sum(r["c"]["redis"] == "cached" for r in rows)
    out = [
        "# Redis endpoint coverage",
        "",
        "Generated: `python scripts/route_inventory.py --markdown > docs/REDIS-ENDPOINT-COVERAGE.md`.",
        "`tests/unit/test_route_inventory.py` fails if this file is stale or an endpoint is unclassified.",
        "",
        f"Routes: {len(rows)}. Cached: {cached}. "
        f"Redis rate-limited: {sum(r['rate_limited'] for r in rows)}.",
        "",
        "Cache classification is per request: authentication, role and organisation checks run "
        "before any cache lookup. Partner keys include user + organisation + membership role; "
        "staff keys include user + role.",
        "",
        "| Method | Path | Module | Audience | Auth | Roles | Org-isolated | Redis | Capability "
        "| TTL | Invalidation | Reason not cached |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        c = r["c"]
        roles = ", ".join(r["roles"]) if isinstance(r["roles"], list) else r["roles"]
        cells = [
            r["method"],
            f"`{r['path']}`",
            r["module"],
            r["audience"],
            r["auth"],
            roles,
            "yes" if r["org_scoped"] else "-",
            c["redis"],
            c["cap"],
            c["ttl"],
            c["inval"],
            c["reason"],
        ]
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    if "--markdown" in sys.argv:
        print(markdown(), end="")
    elif "--json" in sys.argv:
        print(json.dumps(inventory(), indent=1, default=str))
    else:
        for r in inventory():
            print(f"{r['method']:6} {r['path']:70} {r['audience']:13} {r['c']['redis']}")
