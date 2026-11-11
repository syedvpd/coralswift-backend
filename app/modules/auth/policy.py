"""Runtime security policy: super-admin-written values override the environment defaults."""

from sqlalchemy.orm import Session

from app.core.config import Settings

# system-setting key -> Settings field
OVERRIDES = {
    "security.password_min_length": "password_min_length",
    "security.access_token_minutes": "access_token_expire_minutes",
    "security.refresh_token_minutes": "refresh_token_expire_minutes",
    "security.invitation_ttl_hours": "invitation_ttl_hours",
    "security.reset_ttl_minutes": "password_reset_ttl_minutes",
    "security.login_max_failures": "login_max_failures",
    "security.login_lockout_minutes": "login_lockout_minutes",
}


def effective_settings(db: Session, settings: Settings) -> Settings:
    from app.modules.admin import settings_service as cfg

    updates = {
        field: value
        for key, field in OVERRIDES.items()
        if (value := cfg.get_int(db, key)) is not None
    }
    return settings.model_copy(update=updates) if updates else settings
