"""Email providers. `delivered` is True only when a provider accepted the mail."""

import logging
import uuid
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import Settings

logger = logging.getLogger("app.email")
BREVO_URL = "https://api.brevo.com/v3/smtp/email"


class EmailDeliveryError(Exception):
    """Provider rejected or could not be reached. Message must never contain credentials."""


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    html: str
    text: str


@dataclass(frozen=True)
class SendResult:
    provider_reference: str
    delivered: bool


class EmailSender(Protocol):
    def send(self, message: EmailMessage) -> SendResult: ...


class ConsoleEmailSender:
    """Development backend: logs metadata only (no body) and reports delivered=False."""

    def send(self, message: EmailMessage) -> SendResult:
        ref = f"console-{uuid.uuid4().hex[:12]}"
        logger.info("email not delivered (console backend)", extra={"subject": message.subject})
        return SendResult(provider_reference=ref, delivered=False)


class BrevoEmailSender:
    def __init__(
        self,
        api_key: str,
        sender_address: str,
        sender_name: str,
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._sender = {"name": sender_name, "email": sender_address}
        self._client = client or httpx.Client(timeout=10.0)

    def send(self, message: EmailMessage) -> SendResult:
        payload = {
            "sender": self._sender,
            "to": [{"email": message.to}],
            "subject": message.subject,
            "htmlContent": message.html,
            "textContent": message.text,
        }
        try:
            response = self._client.post(
                BREVO_URL, json=payload, headers={"api-key": self._api_key}
            )
        except httpx.HTTPError as exc:
            raise EmailDeliveryError(f"brevo unreachable: {type(exc).__name__}") from exc
        if response.status_code not in (200, 201):
            raise EmailDeliveryError(f"brevo rejected request: HTTP {response.status_code}")
        message_id = response.json().get("messageId", "")
        return SendResult(provider_reference=str(message_id), delivered=True)


class AllowlistEmailSender:
    """Staging guard: refuses any recipient outside the allow-list (address or "@domain")."""

    def __init__(self, inner: EmailSender, allowlist: list[str]) -> None:
        self._inner = inner
        self._allowed = {item.lower() for item in allowlist}

    def send(self, message: EmailMessage) -> SendResult:
        to = message.to.lower()
        if to not in self._allowed and "@" + to.rsplit("@", 1)[-1] not in self._allowed:
            raise EmailDeliveryError("recipient not on this environment's allow-list")
        return self._inner.send(message)


def build_email_sender(settings: Settings) -> EmailSender:
    sender: EmailSender = ConsoleEmailSender()
    if settings.email_backend == "brevo":
        if not (settings.brevo_api_key and settings.email_sender_address):
            raise ValueError("BREVO_API_KEY and EMAIL_SENDER_ADDRESS are required for brevo")
        sender = BrevoEmailSender(
            settings.brevo_api_key.get_secret_value(),
            settings.email_sender_address,
            settings.email_sender_name,
        )
    if settings.email_recipient_allowlist:
        return AllowlistEmailSender(sender, settings.email_recipient_allowlist)
    return sender
