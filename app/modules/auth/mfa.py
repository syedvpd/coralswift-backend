"""TOTP (RFC 6238) multi-factor authentication helpers. Pure functions, no DB.

The shared secret must be recoverable, so it is encrypted at rest with Fernet (authenticated
encryption) using a key derived from SECRET_KEY. Rotating SECRET_KEY invalidates enrolled
secrets (users must re-enroll). Recovery codes are random, shown once, stored only as hashes.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings

STEP_SECONDS = 30
DIGITS = 6
WINDOW = 1  # accept the previous and next step to tolerate clock drift
RECOVERY_CODE_COUNT = 8


def _fernet(settings: Settings) -> Fernet:
    digest = hashlib.sha256(b"mfa-secret-key:" + settings.secret_key.get_secret_value().encode())
    return Fernet(base64.urlsafe_b64encode(digest.digest()))


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode()


def encrypt_secret(settings: Settings, secret: str) -> str:
    return _fernet(settings).encrypt(secret.encode()).decode()


def decrypt_secret(settings: Settings, token: str) -> str | None:
    try:
        return _fernet(settings).decrypt(token.encode()).decode()
    except InvalidToken:
        return None


def _hotp(secret: str, counter: int) -> str:
    key = base64.b32decode(secret)
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()  # noqa: S324 - RFC 4226
    offset = mac[-1] & 0x0F
    value = (struct.unpack(">I", mac[offset : offset + 4])[0] & 0x7FFFFFFF) % 10**DIGITS
    return str(value).zfill(DIGITS)


def current_step(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // STEP_SECONDS)


def code_at(secret: str, step: int) -> str:
    return _hotp(secret, step)


def verify_code(
    secret: str, code: str, last_step: int | None, now: float | None = None
) -> int | None:
    """Return the matched time step, or None. Steps <= last_step are rejected (no code replay)."""
    if not (code.isdigit() and len(code) == DIGITS):
        return None
    step_now = current_step(now)
    for step in range(step_now - WINDOW, step_now + WINDOW + 1):
        if last_step is not None and step <= last_step:
            continue
        if hmac.compare_digest(_hotp(secret, step), code):
            return step
    return None


def provisioning_uri(settings: Settings, email: str, secret: str) -> str:
    issuer = quote(settings.mfa_issuer)
    return (
        f"otpauth://totp/{issuer}:{quote(email)}?secret={secret}&issuer={issuer}"
        f"&algorithm=SHA1&digits={DIGITS}&period={STEP_SECONDS}"
    )


def new_recovery_codes() -> list[str]:
    return [secrets.token_hex(5) for _ in range(RECOVERY_CODE_COUNT)]


def hash_recovery_code(code: str) -> str:
    return hashlib.sha256(code.strip().lower().encode()).hexdigest()
