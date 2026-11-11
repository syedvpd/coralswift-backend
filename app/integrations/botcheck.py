from collections.abc import Sequence
from typing import Protocol

import httpx

from app.core.config import Settings

TURNSTILE_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


class BotVerifier(Protocol):
    def verify(self, token: str | None, client_ip: str) -> bool: ...


class NoopBotVerifier:
    """Used only when CAPTCHA_ENABLED=false (local/dev; production config forbids it)."""

    def verify(self, token: str | None, client_ip: str) -> bool:
        return True


class TurnstileVerifier:
    """Cloudflare Turnstile server-side check. Fails closed: no token or provider error = reject."""

    def __init__(
        self,
        secret: str,
        client: httpx.Client | None = None,
        *,
        allowed_hostnames: Sequence[str] | None = None,
    ) -> None:
        self._secret = secret
        self._client = client or httpx.Client(timeout=5.0)
        self._allowed_hostnames = frozenset(
            h.strip().lower() for h in (allowed_hostnames or ()) if h.strip()
        )

    def verify(self, token: str | None, client_ip: str) -> bool:
        cleaned = token.strip() if token else ""
        if not cleaned or len(cleaned) > 2048:
            return False
        try:
            response = self._client.post(
                TURNSTILE_URL,
                data={"secret": self._secret, "response": cleaned, "remoteip": client_ip},
            )
            if response.status_code != 200:
                return False
            body = response.json()
            if body.get("success") is not True:
                return False
            if self._allowed_hostnames:
                hostname = str(body.get("hostname") or "").strip().lower()
                if hostname not in self._allowed_hostnames:
                    return False
            return True
        except (httpx.HTTPError, ValueError):
            return False


def build_bot_verifier(settings: Settings) -> BotVerifier:
    if settings.captcha_enabled and settings.turnstile_secret_key:
        return TurnstileVerifier(
            settings.turnstile_secret_key.get_secret_value(),
            allowed_hostnames=settings.turnstile_allowed_hostnames,
        )
    return NoopBotVerifier()
