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

    def __init__(self, secret: str, client: httpx.Client | None = None) -> None:
        self._secret = secret
        self._client = client or httpx.Client(timeout=5.0)

    def verify(self, token: str | None, client_ip: str) -> bool:
        if not token:
            return False
        try:
            response = self._client.post(
                TURNSTILE_URL,
                data={"secret": self._secret, "response": token, "remoteip": client_ip},
            )
            return response.status_code == 200 and response.json().get("success") is True
        except (httpx.HTTPError, ValueError):
            return False


def build_bot_verifier(settings: Settings) -> BotVerifier:
    if settings.captcha_enabled and settings.turnstile_secret_key:
        return TurnstileVerifier(settings.turnstile_secret_key.get_secret_value())
    return NoopBotVerifier()
