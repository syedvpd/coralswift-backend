import enum

APPLICATION_SEQUENCE = "portal_application_seq"


class PortalStatus(enum.StrEnum):
    """PRD s.11/s.28 evaluation stages as separate statuses, plus lifecycle states (proposed)."""

    DRAFT = "draft"
    SUBMITTED = "submitted"  # expression of interest received
    ELIGIBILITY_VERIFICATION = "eligibility_verification"
    CAPABILITY_REVIEW = "capability_review"
    COMMERCIAL_LEGAL_REVIEW = "commercial_legal_review"
    PILOT_ONBOARDING = "pilot_onboarding"
    SCALE_UP = "scale_up"
    INFORMATION_REQUESTED = "information_requested"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


TERMINAL = frozenset({PortalStatus.REJECTED, PortalStatus.WITHDRAWN})

# Partner-facing wording (internal stage names are not leaked verbatim).
PARTNER_LABELS = {
    PortalStatus.DRAFT: "Draft",
    PortalStatus.SUBMITTED: "Submitted",
    PortalStatus.ELIGIBILITY_VERIFICATION: "Eligibility verification",
    PortalStatus.CAPABILITY_REVIEW: "Capability review",
    PortalStatus.COMMERCIAL_LEGAL_REVIEW: "Commercial and legal review",
    PortalStatus.PILOT_ONBOARDING: "Pilot / onboarding",
    PortalStatus.SCALE_UP: "Scale-up",
    PortalStatus.INFORMATION_REQUESTED: "Additional information requested",
    PortalStatus.REJECTED: "Not progressed",
    PortalStatus.WITHDRAWN: "Withdrawn",
}


class MessageKind(enum.StrEnum):
    INFORMATION_REQUEST = "information_request"
    PARTNER_RESPONSE = "partner_response"


class MessageStatus(enum.StrEnum):
    OPEN = "open"
    ANSWERED = "answered"


class VerificationOutcome(enum.StrEnum):
    """Chosen by the human reviewer. Never derived from thresholds in code."""

    VERIFIED = "verified"
    VERIFIED_WITH_EXCEPTION = "verified_with_exception"
    NOT_VERIFIED = "not_verified"
    INCONCLUSIVE = "inconclusive"
