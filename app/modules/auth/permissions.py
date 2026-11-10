"""Role-to-endpoint permission matrix, derived from the guards that actually protect each route.

Nothing here is a second source of truth: a route is listed for a role only if the route's own
`require_staff(...)` / `require_partner` dependency admits that role."""

from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.modules.auth.constants import StaffRole, UserType
from app.modules.auth.dependencies import require_partner

API_PREFIX_SKIP = ("/openapi.json", "/docs", "/redoc")


def _iter_routes(router: Any, prefix: str = "") -> Any:
    for route in router.routes:
        if isinstance(route, APIRoute):
            yield prefix + route.path, route
        elif hasattr(route, "original_router") and hasattr(route, "include_context"):
            yield from _iter_routes(
                route.original_router, prefix + (route.include_context.prefix or "")
            )


def _calls(dependant: Any) -> Any:
    for dep in dependant.dependencies:
        yield dep.call
        yield from _calls(dep)


def _guard(route: APIRoute) -> tuple[str, frozenset[StaffRole]]:
    """('staff', roles) | ('partner', {}) | ('authenticated', {}) | ('public', {})"""
    kind = "public"
    roles: frozenset[StaffRole] = frozenset()
    for call in _calls(route.dependant):
        allowed = getattr(call, "allowed_roles", None)
        if allowed is not None:
            return "staff", allowed or frozenset(StaffRole)
        if call is require_partner:
            return "partner", frozenset()
        if getattr(call, "__name__", "") in ("get_auth", "get_auth_pending_mfa"):
            kind = "authenticated"
    return kind, roles


def endpoint_table(app: FastAPI) -> list[dict[str, Any]]:
    cached = getattr(app.state, "permission_table", None)
    if cached is not None:
        return list(cached)
    table: list[dict[str, Any]] = []
    for path, route in _iter_routes(app.router, ""):
        kind, roles = _guard(route)
        if kind == "public":
            continue
        parts = [p for p in path.split("/") if p and p not in ("api", "v1")]
        module = "/".join(parts[:2]) if parts and parts[0] in ("admin", "reviewer") else parts[0]
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            table.append(
                {
                    "method": method,
                    "path": path,
                    "module": module,
                    "kind": kind,
                    "roles": sorted(r.value for r in roles),
                }
            )
    table.sort(key=lambda e: (e["module"], e["path"], e["method"]))
    app.state.permission_table = table
    return table


def permissions_for(app: FastAPI, user_type: UserType, role: StaffRole | None) -> dict[str, Any]:
    modules: dict[str, list[dict[str, str]]] = {}
    for e in endpoint_table(app):
        allowed = (
            e["kind"] == "authenticated"
            or (e["kind"] == "partner" and user_type is UserType.PARTNER)
            or (
                e["kind"] == "staff"
                and user_type is UserType.STAFF
                and role is not None
                and role.value in e["roles"]
            )
        )
        if allowed:
            modules.setdefault(e["module"], []).append({"method": e["method"], "path": e["path"]})
    out: dict[str, Any] = {
        "account_type": user_type.value,
        "staff_role": role.value if role else None,
        "modules": [{"module": m, "endpoints": eps} for m, eps in sorted(modules.items())],
    }
    return out


def role_matrix(app: FastAPI) -> dict[str, list[str]]:
    """role -> modules with at least one endpoint it may call (staff roles only)."""
    matrix: dict[str, set[str]] = {r.value: set() for r in StaffRole}
    for e in endpoint_table(app):
        if e["kind"] == "staff":
            for r in e["roles"]:
                matrix[r].add(e["module"])
    return {r: sorted(m) for r, m in matrix.items()}
