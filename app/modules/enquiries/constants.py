import enum


class EnquiryType(enum.StrEnum):
    GENERAL = "general"
    PROJECT = "project"
    PARTNER = "partner"
    STRATEGIC = "strategic"
    MEETING = "meeting"  # PRD s.12/s.15D meeting request (add-on)


class EnquiryStatus(enum.StrEnum):
    RECEIVED = "received"
    IN_REVIEW = "in_review"  # reserved for Phase 3 staff workflows
    CLOSED = "closed"  # reserved for Phase 3 staff workflows


class Priority(enum.StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class ConsentStatus(enum.StrEnum):
    GRANTED = "granted"
    WITHDRAWN = "withdrawn"


class ContactTopic(enum.StrEnum):
    GENERAL_INFORMATION = "general_information"
    SERVICES = "services"
    PARTNERSHIP = "partnership"
    OTHER = "other"


class ActorType(enum.StrEnum):
    PUBLIC = "public"
    SYSTEM = "system"
    STAFF = "staff"  # reserved for Phase 3
    PARTNER = "partner"
    REVIEWER = "reviewer"


REFERENCE_SEQUENCE = "enquiry_reference_seq"
SOURCE_WEBSITE = "website"
