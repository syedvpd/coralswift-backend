"""Centralised, validated settings. Single source of truth for environment config."""

import json
from typing import Annotated, Any, Literal

from fastapi import Request
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.core.constants import MIN_PRODUCTION_SECRET_LENGTH


def _split_list(value: Any) -> Any:
    """Accept 'a,b' or '["a","b"]' for list settings."""
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("["):
            return json.loads(text)
        return [item.strip() for item in text.split(",") if item.strip()]
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_name: str = "CoralSwift API"
    app_env: Literal["development", "testing", "staging", "production"] = "development"
    app_version: str = "0.1.0"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # Required everywhere: no default means a missing value fails at startup.
    database_url: SecretStr
    secret_key: SecretStr

    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    allowed_hosts: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1"]
    )

    access_token_expire_minutes: int = Field(default=30, gt=0)
    refresh_token_expire_minutes: int = Field(default=10080, gt=0)

    # --- Phase 1: public submissions ---
    # Consent notice shown to users; replace once legal approves the privacy notice (PRD s.21).
    privacy_notice_version: str = "draft-unapproved"
    max_request_body_bytes: int = Field(default=12 * 1024 * 1024, gt=0)
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    max_documents_per_enquiry: int = Field(default=10, gt=0)
    # Per-client submissions per minute. Uploads get 2x, status lookups 3x. 0 disables.
    rate_limit_per_minute: int = Field(default=10, ge=0)
    idempotency_ttl_hours: int = Field(default=24, gt=0)

    storage_backend: Literal["local", "s3"] = "local"
    storage_local_root: str = "var/storage"
    s3_bucket: str | None = None
    s3_partner_bucket: str | None = None  # partner evidence; falls back to s3_bucket when unset
    s3_region: str | None = None
    s3_endpoint_url: str | None = None  # set for S3-compatible stores (MinIO, R2, ...)
    s3_access_key_id: SecretStr | None = None
    s3_secret_access_key: SecretStr | None = None

    email_backend: Literal["console", "brevo"] = "console"
    brevo_api_key: SecretStr | None = None
    scanner_backend: Literal["none", "clamav"] = "none"  # D33: none = quarantine-only
    redis_url: SecretStr | None = None  # unset = no caching
    cache_ttl_seconds: int = Field(default=60, gt=0, le=3600)
    clamav_host: str = "localhost"
    clamav_port: int = Field(default=3310, ge=1, le=65535)
    clamav_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    enquiry_reply_enabled: bool = False  # D15: ad-hoc requester emails stay off until approved
    email_webhook_secret: SecretStr | None = None  # shared secret for provider event webhooks
    email_sender_address: str | None = None
    email_sender_name: str = "Coral Swift"
    notification_max_retries: int = Field(default=5, gt=0)
    # Only these recipients (full address or "@domain") may receive mail. Required in staging so
    # test environments can never email real customers; empty = unrestricted.
    email_recipient_allowlist: Annotated[list[str], NoDecode] = Field(default_factory=list)
    captcha_enabled: bool = False  # explicit opt-in; production requires true
    turnstile_secret_key: SecretStr | None = None  # Cloudflare Turnstile secret
    turnstile_allowed_hostnames: Annotated[list[str], NoDecode] = Field(default_factory=list)
    # Internal recipients per queue. Owners are an open PRD decision, so empty = no internal mail.
    notify_general_emails: Annotated[list[str], NoDecode] = Field(default_factory=list)
    notify_project_emails: Annotated[list[str], NoDecode] = Field(default_factory=list)
    notify_partner_emails: Annotated[list[str], NoDecode] = Field(default_factory=list)
    notify_strategic_emails: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # --- Phase 2: partner portal auth ---
    portal_base_url: str = "http://localhost:3000"  # used in emailed links only
    password_min_length: int = Field(default=12, ge=8)
    password_time_cost: int = Field(default=2, ge=1)  # Argon2id (OWASP minimum profile)
    password_memory_kib: int = Field(default=19456, ge=8)
    login_max_failures: int = Field(default=5, ge=1)
    login_lockout_minutes: int = Field(default=15, ge=1)
    invitation_ttl_hours: int = Field(default=168, ge=1)
    password_reset_ttl_minutes: int = Field(default=60, ge=1)

    @field_validator(
        "cors_allowed_origins",
        "allowed_hosts",
        "turnstile_allowed_hostnames",
        "notify_general_emails",
        "notify_project_emails",
        "notify_partner_emails",
        "notify_strategic_emails",
        "email_recipient_allowlist",
        mode="before",
    )
    @classmethod
    def _parse_lists(cls, value: Any) -> Any:
        return _split_list(value)

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_level(cls, value: Any) -> Any:
        return value.upper() if isinstance(value, str) else value

    @field_validator("api_v1_prefix")
    @classmethod
    def _prefix_shape(cls, value: str) -> str:
        if not value.startswith("/") or value.endswith("/"):
            raise ValueError("must start with '/' and not end with '/'")
        return value

    @field_validator("database_url")
    @classmethod
    def _postgres_only(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith("postgresql"):
            raise ValueError("must be a PostgreSQL SQLAlchemy URL")
        return value

    @model_validator(mode="after")
    def _production_rules(self) -> "Settings":
        if self.captcha_enabled and not self.turnstile_secret_key:
            raise ValueError("CAPTCHA_ENABLED=true requires TURNSTILE_SECRET_KEY")
        if not self.is_hardened:
            return self
        problems: list[str] = []
        if self.app_env == "staging" and not self.email_recipient_allowlist:
            problems.append("staging needs EMAIL_RECIPIENT_ALLOWLIST (internal test inboxes only)")
        if not self.captcha_enabled:
            problems.append("production needs CAPTCHA_ENABLED=true and TURNSTILE_SECRET_KEY")
        if any("*" in hostname for hostname in self.turnstile_allowed_hostnames):
            problems.append("TURNSTILE_ALLOWED_HOSTNAMES must not contain '*'")
        key = self.secret_key.get_secret_value()
        placeholder = any(m in key.lower() for m in ("change-me", "replace-with", "dev-only"))
        if len(key) < MIN_PRODUCTION_SECRET_LENGTH or placeholder:
            problems.append(f"SECRET_KEY must be random, >= {MIN_PRODUCTION_SECRET_LENGTH} chars")
        if self.debug:
            problems.append("DEBUG must be false")
        if any("*" in origin for origin in self.cors_allowed_origins):
            problems.append("CORS_ALLOWED_ORIGINS must not contain '*'")
        if "*" in self.allowed_hosts or not self.allowed_hosts:
            problems.append("ALLOWED_HOSTS must be an explicit, non-empty host list")
        if self.storage_backend != "s3" or not self.s3_bucket:
            problems.append("production needs STORAGE_BACKEND=s3 and S3_BUCKET")
        if self.email_backend != "brevo" or not self.brevo_api_key or not self.email_sender_address:
            problems.append(
                "production needs EMAIL_BACKEND=brevo, BREVO_API_KEY, EMAIL_SENDER_ADDRESS"
            )
        if problems:
            raise ValueError(f"Invalid {self.app_env} configuration: " + "; ".join(problems))
        return self

    @property
    def is_hardened(self) -> bool:
        """Staging and production share the strict security profile."""
        return self.app_env in ("staging", "production")

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


def load_settings() -> Settings:
    return Settings()


def get_settings(request: Request) -> Settings:
    """FastAPI dependency: the settings the app was built with."""
    settings: Settings = request.app.state.settings
    return settings
