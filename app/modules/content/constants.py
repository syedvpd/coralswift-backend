import enum


class ContentType(enum.StrEnum):
    ARTICLE = "article"  # insights (PRD s.5, s.15E)
    FAQ = "faq"  # FAQ / self-service (s.15C)
    PAGE = "page"  # governed website page copy (s.28)
    RESOURCE = "resource"  # downloadable capability statement / approved document (s.15A/E)
    HERO = "hero"  # homepage hero / banner block (structured `data`)
    SERVICE = "service"
    INDUSTRY = "industry"
    NAVIGATION = "navigation"  # menu tree in `data.items`


class ContentStatus(enum.StrEnum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class ClaimStatus(enum.StrEnum):
    """PRD s.28: verified, pending verification, illustrative or prohibited from publication."""

    VERIFIED = "verified"
    PENDING_VERIFICATION = "pending_verification"
    ILLUSTRATIVE = "illustrative"
    PROHIBITED = "prohibited"


class ClaimCategory(enum.StrEnum):
    COMPANY = "company"
    GEOGRAPHY = "geography"
    PARTNER_REFERENCE = "partner_reference"  # s.10: private until verified + written permission
    PROJECT = "project"
    CERTIFICATION = "certification"
    TESTIMONIAL = "testimonial"
    OTHER = "other"


# s.10/s.19/s.28: naming partners, certifications or testimonials needs verification AND permission.
PERMISSION_REQUIRED = frozenset(
    {ClaimCategory.PARTNER_REFERENCE, ClaimCategory.CERTIFICATION, ClaimCategory.TESTIMONIAL}
)
