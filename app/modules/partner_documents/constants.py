import enum


class PartnerDocCategory(enum.StrEnum):
    """PRD s.8 initial submission items (+ authorised-contact evidence 'where required')."""

    REGISTRATION_PROOF = "registration_proof"
    OPERATING_HISTORY = "operating_history"
    EMPLOYEE_STRENGTH = "employee_strength"
    FINANCIAL_STATEMENTS = "financial_statements"
    SERVICE_PORTFOLIO = "service_portfolio"
    INFRASTRUCTURE_SUMMARY = "infrastructure_summary"
    CLIENT_REFERENCES = "client_references"
    AUTHORIZED_CONTACT = "authorized_contact"


# Required before an application can be submitted (authorized_contact is optional).
REQUIRED_CATEGORIES = tuple(
    c for c in PartnerDocCategory if c is not PartnerDocCategory.AUTHORIZED_CONTACT
)


class DocStatus(enum.StrEnum):
    ACTIVE = "active"
    REMOVED = "removed"  # soft delete: bytes and rows are retained (retention policy undecided)


class ReviewStatus(enum.StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CLARIFICATION_NEEDED = "clarification_needed"
    REPLACEMENT_REQUESTED = "replacement_requested"  # staff ask for a new file
