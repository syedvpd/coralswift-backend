"""Optional Redis cache for slow reads. No client = no caching; Redis errors never fail a request"""

import json
import logging
from collections.abc import Callable
from typing import Any, Protocol

from fastapi.encoders import jsonable_encoder

logger = logging.getLogger("app.cache")


class RedisLike(Protocol):
    def get(self, key: str) -> Any: ...
    def set(self, key: str, value: str, ex: int) -> Any: ...


class Cache:
    def __init__(self, client: RedisLike | None, prefix: str) -> None:
        self._client = client
        self._prefix = prefix

    def get_or_set(self, key: str, ttl_seconds: int, build: Callable[[], Any]) -> Any:
        """Return the cached JSON value, else build, store and return it."""
        if self._client is None:
            return build()
        full_key = f"{self._prefix}:{key}"
        try:
            hit = self._client.get(full_key)
            if hit is not None:
                return json.loads(hit)
        except Exception:  # noqa: BLE001 - a cache outage must not break the endpoint
            logger.warning("cache read failed", exc_info=True)
        value = jsonable_encoder(build())
        try:
            self._client.set(full_key, json.dumps(value), ex=ttl_seconds)
        except Exception:  # noqa: BLE001
            logger.warning("cache write failed", exc_info=True)
        return value
