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


_state = {"enforce_clean": False}


def set_scan_enforcement(on: bool) -> None:
    """True when a scanner is configured: only `clean` files may be reviewed or downloaded."""
    _state["enforce_clean"] = on


def scan_enforced() -> bool:
    return _state["enforce_clean"]


def attachable_statuses() -> tuple[UploadStatus, ...]:
    """Statuses that may be downloaded/reviewed/attached. Quarantine-only deployments (no
    scanner, owner decision D33) allow quarantined files; with a scanner only `clean` passes."""
    if _state["enforce_clean"]:
        return (UploadStatus.CLEAN,)
    return (UploadStatus.QUARANTINED, UploadStatus.CLEAN)


def scan_status_of(status: str) -> str:
    """not_scanned | scan_pending | clean | infected | scan_failed (clean only if scanned)."""
    if status == UploadStatus.CLEAN.value:
        return "clean"
    if status == UploadStatus.REJECTED.value:
        return "infected"
    if status == UploadStatus.FAILED.value:
        return "scan_failed"
    return "scan_pending" if _state["enforce_clean"] else "not_scanned"
