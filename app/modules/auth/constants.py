import enum


class UserType(enum.StrEnum):
    PARTNER = "partner"
    STAFF = "staff"


class StaffRole(enum.StrEnum):
    """Platform staff roles covering onboarding, project exchange, delivery, finance, and audit."""

    PARTNER_REVIEWER = "partner_reviewer"
    SUPER_ADMINISTRATOR = "super_administrator"
    BUSINESS_DEVELOPMENT_MANAGER = "business_development_manager"
    CONTENT_ADMINISTRATOR = "content_administrator"
    SOURCING_MANAGER = "sourcing_manager"
    COMPLIANCE_OFFICER = "compliance_officer"
    DELIVERY_MANAGER = "delivery_manager"
    FINANCE = "finance"
    AUDITOR = "auditor"
    APPROVER = "approver"


class UserStatus(enum.StrEnum):
    INVITED = "invited"
    ACTIVE = "active"
    DEACTIVATED = "deactivated"
    SUSPENDED = "suspended"  # set by admin "suspend"; reactivation is an admin action


class TokenPurpose(enum.StrEnum):
    INVITATION = "invitation"
    PASSWORD_RESET = "password_reset"


TOKEN_PREFIX = "cs_"
