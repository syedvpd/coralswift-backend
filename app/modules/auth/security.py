"""Password hashing (Argon2id) and opaque-token helpers. Pure functions, no DB."""

import hashlib
import secrets
from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import Settings
from app.core.exceptions import AppError
from app.modules.auth.constants import TOKEN_PREFIX

MAX_PASSWORD_LENGTH = 128


@lru_cache(maxsize=8)
def _hasher(time_cost: int, memory_kib: int) -> PasswordHasher:
    return PasswordHasher(time_cost=time_cost, memory_cost=memory_kib, parallelism=1)


def hash_password(settings: Settings, password: str) -> str:
    return _hasher(settings.password_time_cost, settings.password_memory_kib).hash(password)


def verify_password(settings: Settings, password_hash: str, password: str) -> bool:
    try:
        return _hasher(settings.password_time_cost, settings.password_memory_kib).verify(
            password_hash, password
        )
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(settings: Settings, password_hash: str) -> bool:
    return _hasher(settings.password_time_cost, settings.password_memory_kib).check_needs_rehash(
        password_hash
    )


@lru_cache(maxsize=8)
def _dummy_hash(time_cost: int, memory_kib: int) -> str:
    return _hasher(time_cost, memory_kib).hash("dummy-password-for-timing")


def burn_verify(settings: Settings, password: str) -> None:
    """Spend the same time as a real check so unknown accounts are not distinguishable by timing."""
    verify_password(
        settings, _dummy_hash(settings.password_time_cost, settings.password_memory_kib), password
    )


def validate_password_policy(settings: Settings, password: str, email: str | None = None) -> None:
    problems: list[str] = []
    if len(password) < settings.password_min_length:
        problems.append(f"must be at least {settings.password_min_length} characters")
    if len(password) > MAX_PASSWORD_LENGTH:
        problems.append(f"must be at most {MAX_PASSWORD_LENGTH} characters")
    if "\x00" in password:
        problems.append("contains invalid characters")
    if email and password.lower() == email.lower():
        problems.append("must not equal the email address")
    if problems:
        raise AppError(
            "Password does not meet the policy",
            status_code=422,
            code="WEAK_PASSWORD",
            details=[{"field": "password", "message": "; ".join(problems)}],
        )


def new_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
