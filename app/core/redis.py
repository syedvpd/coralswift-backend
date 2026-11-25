"""One shared synchronous Redis client per app (the app is sync FastAPI + sync SQLAlchemy).

No client = Redis disabled. Nothing connects at import time; the pool connects lazily. After a
failure Redis is skipped for a short pause (circuit breaker) so a dead Redis costs one timeout,
not one per request. Callers decide the fallback: caches fall back to the database, rate limits
to a per-process limiter. Credentials never reach logs (only the host is logged).
"""

import logging
import threading
import time
from typing import Any
from urllib.parse import urlsplit

from redis import BlockingConnectionPool, Redis
from redis.exceptions import RedisError

from app.core.config import Settings

logger = logging.getLogger("app.redis")

# Redis calls that can fail with these are treated as "Redis unavailable".
REDIS_ERRORS = (RedisError, OSError)


class RedisManager:
    def __init__(self, settings: Settings) -> None:
        self._url = settings.redis_url.get_secret_value() if settings.redis_url else None
        self._settings = settings
        self._client: Any = (
            None  # redis-py stubs type sync calls as Awaitable; Any keeps them usable
        )
        self._lock = threading.Lock()
        self._down_until = 0.0
        self.errors = 0
        self.prefix = settings.redis_key_prefix

    @property
    def enabled(self) -> bool:
        return self._url is not None

    @property
    def host(self) -> str:
        return (urlsplit(self._url).hostname or "?") if self._url else "-"

    def _build(self, url: str) -> Redis:
        pool = BlockingConnectionPool.from_url(
            url,
            timeout=self._settings.redis_connect_timeout_seconds,  # wait for a free connection
            max_connections=self._settings.redis_max_connections,
            socket_connect_timeout=self._settings.redis_connect_timeout_seconds,
            socket_timeout=self._settings.redis_socket_timeout_seconds,
            health_check_interval=30,
            decode_responses=True,
        )
        return Redis(connection_pool=pool)

    @property
    def client(self) -> Any:
        """The shared client, or None when disabled or paused after a recent failure."""
        if self._url is None or time.monotonic() < self._down_until:
            return None
        if self._client is None:
            with self._lock:
                if self._client is None:
                    self._client = self._build(self._url)
        return self._client

    def record_failure(self, exc: BaseException) -> None:
        self.errors += 1
        self._down_until = time.monotonic() + self._settings.redis_retry_after_failure_seconds
        # Class name only: exception text can contain the connection URL.
        logger.warning("redis unavailable", extra={"error": type(exc).__name__, "host": self.host})

    def ping(self) -> bool:
        """Readiness probe. Bypasses the circuit breaker so recovery is detected."""
        if self._url is None:
            return False
        try:
            if self._client is None:
                with self._lock:
                    self._client = self._client or self._build(self._url)
            self._client.ping()
        except REDIS_ERRORS as exc:
            self.record_failure(exc)
            return False
        self._down_until = 0.0
        return True

    def start(self) -> None:
        if self.enabled:
            ok = self.ping()
            logger.info("redis", extra={"host": self.host, "connected": ok})

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
                self._client.connection_pool.disconnect()
            except REDIS_ERRORS:
                logger.warning("redis close failed")
            self._client = None
