"""`@cached_read`: Redis-cache the JSON body of a read endpoint.

Safety by construction:
* The decorator wraps the endpoint function, so FastAPI dependencies (authentication, role and
  organisation checks) have ALREADY run when the cache is consulted.
* The cache key is built from every endpoint argument (query filters, page, path ids) plus the
  caller's identity: staff user + role, or partner user + organisation + membership role.
  An argument of a type the key builder does not know disables caching for that call (fail safe).
* Only the response model's JSON is stored; ORM objects never are.
"""

import functools
import logging
import uuid
from collections.abc import Callable
from datetime import date, datetime
from enum import Enum
from typing import Any

from fastapi import Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.common.pagination import PageParams
from app.modules.auth.dependencies import PartnerContext, StaffContext

logger = logging.getLogger("app.cache")
_SKIP = ("request", "response", "db", "background", "background_tasks", "settings")


class _Unkeyable(Exception):
    pass


def _ident(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, uuid.UUID | datetime | date):
        return str(value)
    if isinstance(value, StaffContext):
        role = value.user.staff_role
        return {"staff": str(value.user.id), "role": role.value if role else None}
    if isinstance(value, PartnerContext):
        return {
            "partner": str(value.user.id),
            "org": str(value.organization_id),
            "member_role": value.role.value,
        }
    if isinstance(value, PageParams):
        return {"page": value.page, "size": value.page_size}
    values = getattr(value, "values", None)  # filter dependency classes expose their values
    if isinstance(values, dict):
        return {k: _ident(v) for k, v in sorted(values.items())}
    if isinstance(value, list | tuple):
        return [_ident(v) for v in value]
    raise _Unkeyable(type(value).__name__)


def cached_read[R: BaseModel](
    namespace: str | Callable[[dict[str, Any]], str],
    ttl_setting: str,
    model: type[R],
) -> Callable[[Callable[..., R]], Callable[..., R]]:
    """`namespace` is fixed or computed from the endpoint kwargs (e.g. per organisation).
    `ttl_setting` names the Settings field holding the TTL. The endpoint must take `request`."""

    def decorator(fn: Callable[..., R]) -> Callable[..., R]:
        ident = f"{fn.__module__}.{fn.__qualname__}"

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> R:
            request: Request = kwargs["request"]
            try:
                parts = {
                    k: _ident(v)
                    for k, v in kwargs.items()
                    if k not in _SKIP and not isinstance(v, Session)
                }
                ns = namespace(kwargs) if callable(namespace) else namespace
            except _Unkeyable as exc:
                logger.warning("uncacheable argument %s on %s", exc, ident)
                return fn(*args, **kwargs)
            ttl = getattr(request.app.state.settings, ttl_setting)
            data = request.app.state.cache.get_or_set(
                ns, {"fn": ident, **parts}, ttl, lambda: fn(*args, **kwargs).model_dump(mode="json")
            )
            return model.model_validate(data)

        wrapper.cache_meta = {"ttl_setting": ttl_setting}  # type: ignore[attr-defined]
        return wrapper

    return decorator
