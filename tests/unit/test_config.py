from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import Settings

GOOD_KEY = "k" * 48
PROD_INTEGRATIONS: dict[str, Any] = {
    "storage_backend": "s3",
    "s3_bucket": "bucket",
    "email_backend": "brevo",
    "brevo_api_key": "key",
    "email_sender_address": "noreply@example.com",
    "captcha_enabled": True,
    "turnstile_secret_key": "secret",
}


def make(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": "postgresql+psycopg://u:p@localhost:5432/x",
        "secret_key": GOOD_KEY,
    }
    values.update(overrides)
    if values.get("app_env") in ("production", "staging"):
        for key, value in PROD_INTEGRATIONS.items():
            values.setdefault(key, value)
    return Settings(_env_file=None, **values)


def test_production_requires_s3_and_brevo() -> None:
    with pytest.raises(ValidationError, match="STORAGE_BACKEND=s3"):
        make(app_env="production", allowed_hosts="a.com", storage_backend="local")
    with pytest.raises(ValidationError, match="BREVO_API_KEY"):
        make(app_env="production", allowed_hosts="a.com", email_backend="console")


def test_captcha_rules() -> None:
    with pytest.raises(ValidationError, match="TURNSTILE_SECRET_KEY"):
        make(captcha_enabled=True)  # enabled without a secret, even outside production
    with pytest.raises(ValidationError, match="CAPTCHA_ENABLED"):
        make(app_env="production", allowed_hosts="a.com", captcha_enabled=False)
    with pytest.raises(ValidationError, match="CAPTCHA_ENABLED"):
        make(app_env="production", allowed_hosts="a.com", turnstile_secret_key=None)
    assert make().captcha_enabled is False  # dev default: explicitly off


def test_staging_is_hardened_and_restricts_recipients() -> None:
    base: dict[str, Any] = {"app_env": "staging", "allowed_hosts": "stg.a.com"}
    with pytest.raises(ValidationError, match="EMAIL_RECIPIENT_ALLOWLIST"):
        make(**base)
    s = make(**base, email_recipient_allowlist="qa@example.com,@example.org")
    assert s.is_hardened and not s.is_production
    assert s.email_recipient_allowlist == ["qa@example.com", "@example.org"]
    # same strict profile as production: missing security configuration refuses to load
    for bad in (
        {"debug": True},
        {"allowed_hosts": "*"},
        {"captcha_enabled": False},
        {"staff_mfa_required": False},
    ):
        with pytest.raises(ValidationError):
            make(**{**base, "email_recipient_allowlist": "qa@example.com", **bad})


def test_missing_required_settings_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    text = str(exc.value)
    assert "database_url" in text and "secret_key" in text


def test_valid_production_config_loads() -> None:
    s = make(
        app_env="production",
        cors_allowed_origins="https://a.com,https://b.com",
        allowed_hosts="api.a.com",
    )
    assert s.is_production
    assert s.cors_allowed_origins == ["https://a.com", "https://b.com"]


@pytest.mark.parametrize(
    "overrides, fragment",
    [
        ({"secret_key": "short"}, "SECRET_KEY"),
        ({"secret_key": "change-me-" + "x" * 40}, "SECRET_KEY"),
        ({"debug": True}, "DEBUG"),
        ({"cors_allowed_origins": "*"}, "CORS_ALLOWED_ORIGINS"),
        ({"allowed_hosts": "*"}, "ALLOWED_HOSTS"),
    ],
)
def test_insecure_production_config_rejected(overrides: dict[str, Any], fragment: str) -> None:
    base: dict[str, Any] = {"app_env": "production", "allowed_hosts": "api.a.com"}
    base.update(overrides)
    with pytest.raises(ValidationError, match=fragment):
        make(**base)


def test_same_values_allowed_outside_production() -> None:
    assert make(app_env="development", debug=True, secret_key="dev").debug is True


def test_json_list_and_log_level_normalised() -> None:
    s = make(cors_allowed_origins='["https://a.com"]', log_level="debug")
    assert s.cors_allowed_origins == ["https://a.com"]
    assert s.log_level == "DEBUG"


def test_non_postgres_url_rejected() -> None:
    with pytest.raises(ValidationError, match="PostgreSQL"):
        make(database_url="sqlite:///x.db")


def test_secrets_not_in_repr() -> None:
    s = make()
    assert GOOD_KEY not in repr(s) and "u:p@" not in repr(s)
