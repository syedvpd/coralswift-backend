"""Shared input types for public forms. All text is stripped; NUL bytes are rejected (PostgreSQL
cannot store them) and phone/country/email are normalised."""

import os
import re
from typing import Annotated

from email_validator import EmailNotValidError, validate_email
from pydantic import AfterValidator, BeforeValidator, StringConstraints

_PHONE_CLEAN = re.compile(r"[\s().-]")
_PHONE_E164 = re.compile(r"^\+[1-9][0-9]{6,14}$")
_COUNTRY = re.compile(r"^[A-Z]{2}$")


def _no_nul(value: str) -> str:
    if "\x00" in value:
        raise ValueError("contains invalid characters")
    return value


def _phone(value: str) -> str:
    cleaned = _PHONE_CLEAN.sub("", value)
    if not _PHONE_E164.match(cleaned):
        raise ValueError("must be an international number such as +14155550123")
    return cleaned


def _country(value: str) -> str:
    value = value.upper()
    if not _COUNTRY.match(value):
        raise ValueError("must be a 2-letter ISO country code")
    return value


Name = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=150),
    AfterValidator(_no_nul),
]
Short = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
    AfterValidator(_no_nul),
]
Medium = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
    AfterValidator(_no_nul),
]
Long = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=4000),
    AfterValidator(_no_nul),
]
Message = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=5, max_length=5000),
    AfterValidator(_no_nul),
]
Phone = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=30), AfterValidator(_phone)
]
Country = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=2), AfterValidator(_country)
]


def _email(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("must be a valid email address")
    # email-validator rejects special-use names by default. Permit these only for local/dev
    # and automated test deployments, where .test addresses are intentionally used.
    test_environment = os.getenv("APP_ENV", "development").lower() in {"development", "testing"}
    try:
        return validate_email(
            value.strip(), check_deliverability=False, test_environment=test_environment
        ).normalized.lower()
    except EmailNotValidError as exc:
        raise ValueError(str(exc)) from exc


EmailAddress = Annotated[str, BeforeValidator(_email), StringConstraints(max_length=254)]
BusinessEmail = EmailAddress
