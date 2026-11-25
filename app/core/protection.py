"""Abuse protection for public endpoints: body-size cap, rate limit, bot-check hook."""

import threading
import time
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, Header, Request
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from app.common.responses import error_body
from app.core.config import Settings, get_settings
from app.core.exceptions import AppError
from app.core.redis import REDIS_ERRORS, RedisManager


class BodySizeLimitMiddleware:
    """Rejects requests whose declared Content-Length exceeds the cap.

    shortcut: chunked bodies carry no length; the reverse proxy must cap them too (per-file
    limits are still enforced in the upload service).
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            length = Headers(scope=scope).get("content-length", "")
            if length.isdigit() and int(length) > self.max_bytes:
                body = error_body("PAYLOAD_TOO_LARGE", "Request body is too large")
                await JSONResponse(body, status_code=413)(scope, receive, send)
                return
        await self.app(scope, receive, send)


class FixedWindowLimiter:
    """Per-process fixed-window counter.

    shortcut: state is per worker process and lost on restart. Real enforcement belongs at the
    proxy/CDN; with REDIS_URL set, DistributedLimiter (below) is used instead.
    """

    def __init__(self, window_seconds: int = 60) -> None:
        self.window = window_seconds
        self._hits: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, limit: int) -> int | None:
        """Return None if allowed, else seconds until the window resets."""
        now = time.monotonic()
        with self._lock:
            start, count = self._hits.get(key, (now, 0))
            if now - start >= self.window:
                start, count = now, 0
            if count >= limit:
                return max(1, int(self.window - (now - start)))
            self._hits[key] = (start, count + 1)
            if len(self._hits) > 10_000:  # bound memory
                self._hits = {k: v for k, v in self._hits.items() if now - v[0] < self.window}
            return None


_WINDOW_SCRIPT = """
local c = redis.call('INCR', KEYS[1])
local t = redis.call('TTL', KEYS[1])
if c == 1 or t < 0 then redis.call('EXPIRE', KEYS[1], ARGV[1]) t = tonumber(ARGV[1]) end
return {c, t}
"""


class DistributedLimiter:
    """Fixed-window counter shared by all workers via one atomic Lua call.

    If Redis is unavailable it falls back to the per-process limiter: limits stay enforced
    (never fail open), just per worker.
    """

    def __init__(self, manager: RedisManager, local: FixedWindowLimiter) -> None:
        self._manager = manager
        self._local = local

    def check(self, key: str, limit: int) -> int | None:
        client = self._manager.client
        if client is not None:
            try:
                count, ttl = client.eval(
                    _WINDOW_SCRIPT, 1, f"{self._manager.prefix}:rl:{key}", str(self._local.window)
                )
                return max(1, int(ttl)) if int(count) > limit else None
            except REDIS_ERRORS as exc:
                self._manager.record_failure(exc)
        return self._local.check(key, limit)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def rate_limit(name: str, multiplier: int = 1) -> Callable[[Request], None]:
    def dependency(request: Request) -> None:
        settings: Settings = request.app.state.settings
        if settings.rate_limit_per_minute == 0:
            return
        limiter: FixedWindowLimiter | DistributedLimiter = request.app.state.rate_limiter
        retry_after = limiter.check(
            f"{name}:{client_ip(request)}", settings.rate_limit_per_minute * multiplier
        )
        if retry_after is not None:
            raise AppError(
                "Too many requests. Please try again later.",
                status_code=429,
                code="TOO_MANY_REQUESTS",
                headers={"Retry-After": str(retry_after)},
            )

    return dependency


def require_human(
    request: Request,
    x_bot_token: Annotated[str | None, Header()] = None,
) -> None:
    """Integration point for CAPTCHA/Turnstile. Default verifier allows everything."""
    if not request.app.state.bot_verifier.verify(x_bot_token, client_ip(request)):
        raise AppError("Bot check failed", status_code=403, code="BOT_CHECK_FAILED")


def require_human_action(expected_action: str) -> Any:
    """Dependency factory enforcing an expected Turnstile action on siteverify."""

    def dependency(
        request: Request,
        x_bot_token: Annotated[str | None, Header()] = None,
    ) -> None:
        if not request.app.state.bot_verifier.verify(
            x_bot_token, client_ip(request), expected_action=expected_action
        ):
            raise AppError("Bot check failed", status_code=403, code="BOT_CHECK_FAILED")

    return dependency


SubmissionGuards = [Depends(rate_limit("submit")), Depends(require_human)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
