import enum


class UserType(enum.StrEnum):
    PARTNER = "partner"
    STAFF = "staff"


class StaffRole(enum.StrEnum):
    """PRD s.14 roles. Phase 2 uses only the first two; the rest are reserved for Phase 3."""

    PARTNER_REVIEWER = "partner_reviewer"
    SUPER_ADMINISTRATOR = "super_administrator"
    BUSINESS_DEVELOPMENT_MANAGER = "business_development_manager"
    CONTENT_ADMINISTRATOR = "content_administrator"


class UserStatus(enum.StrEnum):
    INVITED = "invited"
    ACTIVE = "active"
    DEACTIVATED = "deactivated"
    SUSPENDED = "suspended"  # set by admin "suspend"; reactivation is an admin action


class TokenPurpose(enum.StrEnum):
    INVITATION = "invitation"
    PASSWORD_RESET = "password_reset"


TOKEN_PREFIX = "cs_"
