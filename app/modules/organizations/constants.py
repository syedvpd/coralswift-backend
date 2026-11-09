import enum


class OrgStatus(enum.StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class MembershipRole(enum.StrEnum):
    OWNER = "owner"
    MEMBER = "member"


class MembershipStatus(enum.StrEnum):
    ACTIVE = "active"
    REMOVED = "removed"


# Profile fields that count towards the completion indicator (PRD s.13 / s.8).
REQUIRED_PROFILE_FIELDS = (
    "registration_number",
    "year_established",
    "employee_count",
    "annual_turnover_inr_crore",
    "registered_address",
    "country",
    "website",
    "service_categories",
    "technical_capabilities",
    "infrastructure_summary",
    "client_references",
    "business_description",
    "authorized_contacts",
)
MIN_CLIENT_REFERENCES = 2
