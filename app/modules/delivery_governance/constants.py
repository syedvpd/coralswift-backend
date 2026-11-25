import enum


class ContractStatus(enum.StrEnum):
    DRAFT = "draft"
    SENT_FOR_SIGNATURE = "sent_for_signature"
    PARTNER_SIGNED = "partner_signed"
    COUNTERSIGNED = "countersigned"
    ACTIVE = "active"
    COMPLETED = "completed"
    TERMINATED = "terminated"


class DeliverableStatus(enum.StrEnum):
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    ACCEPTED = "accepted"
    REVISION_REQUESTED = "revision_requested"
    REJECTED = "rejected"


class InvoiceStatus(enum.StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    PAID = "paid"
    DISPUTED = "disputed"
    CANCELLED = "cancelled"


class ScreeningStatus(enum.StrEnum):
    PENDING = "pending"
    PASSED = "passed"
    FLAGGED = "flagged"
    FAILED = "failed"
