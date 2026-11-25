"""Response cache on the shared Redis client.

Keys:    <prefix>:v1:<namespace>:<sha256(parts)>        value = {"g": <generation>, "v": <json>}
         <prefix>:g:<namespace>                          generation, replaced on invalidation
Invalidation replaces the namespace generation (O(1), no SCAN/wildcard delete); entries of an
older generation are ignored and expire by TTL. A read is one MGET (generation + value).
Callers pass JSON-able data (never ORM objects). Payloads containing secret-looking keys are
refused, so tokens and signed URLs cannot land here by accident. Any Redis error is a miss.
"""

import hashlib
import json
import logging
import re
import threading
import time
from collections.abc import Callable
from typing import Any

from fastapi.encoders import jsonable_encoder

from app.core.config import Settings
from app.core.redis import REDIS_ERRORS, RedisManager

logger = logging.getLogger("app.cache")

KEY_VERSION = "v1"  # bump to orphan every cached entry after a payload-shape change
# Whole words of a field name (split on non-alphanumerics), so "unassigned" is not "signed".
FORBIDDEN_WORDS = frozenset(
    {
        "password", "passwd", "token", "tokens", "secret", "secrets", "otp", "mfa", "signed",
        "presigned", "authorization", "cookie", "cookies", "apikey", "credential", "credentials",
    }
)  # fmt: skip
FORBIDDEN_PAIRS = ("api_key", "download_url", "signed_url")
LOCK_SECONDS = 10
WAIT_SECONDS = 2.0
_MISS = object()


class UncacheableError(ValueError):
    """The payload holds a secret-looking field and must not be cached."""


def _secret_name(name: str) -> bool:
    low = re.sub(r"([a-z0-9])([A-Z])", lambda m: m[1] + "_" + m[2], name).lower()
    return bool(set(re.split(r"[^a-z0-9]+", low)) & FORBIDDEN_WORDS) or any(
        pair in low for pair in FORBIDDEN_PAIRS
    )


def _assert_cacheable(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if _secret_name(str(key)):
                raise UncacheableError(f"field {key!r} must not be cached")
            _assert_cacheable(item)
    elif isinstance(value, list):
        for item in value:
            _assert_cacheable(item)


def _dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


class CacheService:
    def __init__(self, manager: RedisManager, settings: Settings) -> None:
        self._m = manager
        self._enabled = settings.cache_enabled
        self._max_ttl = settings.cache_max_ttl_seconds
        self.hits = 0
        self.misses = 0
        self.bypassed = 0
        self.errors = 0

    @property
    def active(self) -> bool:
        return self._enabled and self._m.enabled

    def _gen_key(self, namespace: str) -> str:
        return f"{self._m.prefix}:g:{namespace}"

    def key(self, namespace: str, parts: dict[str, Any]) -> str:
        digest = hashlib.sha256(_dump(parts).encode()).hexdigest()[:32]
        return f"{self._m.prefix}:{KEY_VERSION}:{namespace}:{digest}"

    def _fail(self, exc: BaseException) -> None:
        self.errors += 1
        self._m.record_failure(exc)

    def _generation(self, client: Any, namespace: str, current: str | None) -> str:
        if current is not None:
            return str(current)
        gen_key = self._gen_key(namespace)
        client.set(gen_key, str(time.time_ns()), nx=True)
        return str(client.get(gen_key))

    def get_or_set(
        self,
        namespace: str,
        parts: dict[str, Any],
        ttl_seconds: int,
        build: Callable[[], Any],
    ) -> Any:
        """Cached JSON value for (namespace, parts), else build() and store it.

        `parts` must hold everything the result depends on (organisation id, user id,
        filters...). One builder at a time per key; waiters reuse its result.
        """
        client = self._m.client if self.active else None
        if client is None:
            self.bypassed += 1
            return jsonable_encoder(build())
        key = self.key(namespace, parts)
        lock_key = f"{key}:lock"
        ttl = max(1, min(ttl_seconds, self._max_ttl))
        try:
            raw_gen, raw = client.mget(self._gen_key(namespace), key)
            gen = self._generation(client, namespace, raw_gen)
            hit = self._decode(raw, gen)
            if hit is not _MISS:
                self.hits += 1
                return hit
            self.misses += 1
            token = f"{threading.get_ident()}:{time.time_ns()}"
            if not client.set(lock_key, token, nx=True, ex=LOCK_SECONDS):
                waited = self._wait(client, key, gen)
                if waited is not _MISS:
                    return waited
                token = ""  # another builder holds the lock; build anyway, do not release it
        except REDIS_ERRORS as exc:
            self._fail(exc)
            self.bypassed += 1
            return jsonable_encoder(build())
        try:
            value = jsonable_encoder(build())
            try:
                _assert_cacheable(value)
                client.set(key, _dump({"g": gen, "v": value}), ex=ttl)
            except UncacheableError:
                logger.error("refused to cache payload", extra={"namespace": namespace})
            except REDIS_ERRORS as exc:
                self._fail(exc)
            return value
        finally:
            if token:
                self._release(client, lock_key, token)

    @staticmethod
    def _decode(raw: str | None, gen: str) -> Any:
        if raw is None:
            return _MISS
        try:
            env = json.loads(raw)
        except ValueError:
            return _MISS
        return env["v"] if isinstance(env, dict) and env.get("g") == gen else _MISS

    def _wait(self, client: Any, key: str, gen: str) -> Any:
        deadline = time.monotonic() + WAIT_SECONDS
        while time.monotonic() < deadline:
            time.sleep(0.05)
            found = self._decode(client.get(key), gen)
            if found is not _MISS:
                self.hits += 1
                return found
        return _MISS

    def _release(self, client: Any, lock_key: str, token: str) -> None:
        try:
            if client.get(lock_key) == token:
                client.delete(lock_key)
        except REDIS_ERRORS as exc:
            self._fail(exc)

    def invalidate(self, namespace: str) -> None:
        """Drop every entry of a namespace. If Redis is unreachable now, entries age out by TTL."""
        client = self._m.client if self.active else None
        if client is None:
            return
        try:
            client.set(self._gen_key(namespace), str(time.time_ns()))
        except REDIS_ERRORS as exc:
            self._fail(exc)
            logger.error("cache invalidation failed", extra={"namespace": namespace})

    def delete(self, namespace: str, parts: dict[str, Any]) -> None:
        client = self._m.client if self.active else None
        if client is None:
            return
        try:
            client.delete(self.key(namespace, parts))
        except REDIS_ERRORS as exc:
            self._fail(exc)

    def exists(self, namespace: str, parts: dict[str, Any]) -> bool:
        client = self._m.client if self.active else None
        if client is None:
            return False
        try:
            return bool(client.exists(self.key(namespace, parts)))
        except REDIS_ERRORS as exc:
            self._fail(exc)
            return False

    def stats(self) -> dict[str, int]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "bypassed": self.bypassed,
            "errors": self.errors,
        }


_current: CacheService | None = None


def set_cache(service: CacheService | None) -> None:
    """Process-wide handle for code without a request (session hooks, maintenance job)."""
    global _current  # noqa: PLW0603
    _current = service


def get_cache() -> CacheService | None:
    return _current
