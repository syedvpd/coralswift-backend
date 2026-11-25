import enum


class OpportunityStatus(enum.StrEnum):
    INTAKE = "intake"
    STRUCTURING = "structuring"
    PUBLISHED = "published"
    SHORTLISTING = "shortlisting"
    AWARDED = "awarded"
    IN_DELIVERY = "in_delivery"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class OpportunityVisibility(enum.StrEnum):
    INVITE_ONLY = "invite_only"
    CATEGORY_TARGETED = "category_targeted"
    PUBLIC = "public"


class ProposalStatus(enum.StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_EVALUATION = "under_evaluation"
    SHORTLISTED = "shortlisted"
    AWARDED = "awarded"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
