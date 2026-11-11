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


class CompanyType(enum.StrEnum):
    PRIVATE_LIMITED = "private_limited"
    PUBLIC_LIMITED = "public_limited"
    PARTNERSHIP = "partnership"
    LLP = "llp"
    PROPRIETORSHIP = "proprietorship"
    NONPROFIT = "nonprofit"
    OTHER = "other"


class OperatingModel(enum.StrEnum):
    ONSITE = "onsite"
    REMOTE = "remote"
    HYBRID = "hybrid"
    MULTI_LOCATION = "multi_location"


# Partner permissions the API enforces. Richer roles are an open decision (D22).
PARTNER_PERMISSIONS: dict[MembershipRole, list[str]] = {
    MembershipRole.OWNER: ["team.manage"],
    MembershipRole.MEMBER: [],
}
