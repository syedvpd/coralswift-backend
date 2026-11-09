import enum


class OwnerType(enum.StrEnum):
    UNATTACHED = "unattached"
    ENQUIRY = "enquiry"


class UploadPurpose(enum.StrEnum):
    PROJECT_ATTACHMENT = "project_attachment"
    PARTNER_EVIDENCE = "partner_evidence"
    STRATEGIC_ATTACHMENT = "strategic_attachment"


class EvidenceCategory(enum.StrEnum):
    """The eight initial submission items in PRD s.8 (authorized contact is a form field)."""

    REGISTRATION_PROOF = "registration_proof"
    OPERATING_HISTORY = "operating_history"
    EMPLOYEE_STRENGTH = "employee_strength"
    FINANCIAL_STATEMENTS = "financial_statements"
    SERVICE_PORTFOLIO = "service_portfolio"
    INFRASTRUCTURE_SUMMARY = "infrastructure_summary"
    CLIENT_REFERENCES = "client_references"


class Classification(enum.StrEnum):
    RESTRICTED = "restricted"
    CONFIDENTIAL = "confidential"


class UploadStatus(enum.StrEnum):
    UPLOADING = "uploading"
    # No malware scanner is configured: every stored file stays quarantined until one is.
    QUARANTINED = "quarantined"
    CLEAN = "clean"  # reserved for a future scanner
    REJECTED = "rejected"  # reserved for a future scanner
    FAILED = "failed"


ATTACHABLE_STATUSES = (UploadStatus.QUARANTINED, UploadStatus.CLEAN)
