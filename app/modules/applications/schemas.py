import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.common.validation import Long
from app.modules.applications.constants import PARTNER_LABELS, PortalStatus
from app.modules.applications.models import ApplicationStatusHistory, PortalApplication
from app.modules.partners.constants import EngagementPathway


class DraftIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pathway: EngagementPathway
    cover_note: Long | None = None


class DraftUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pathway: EngagementPathway | None = None
    cover_note: Long | None = None


class WithdrawIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: Long | None = None


class ApplicationOut(BaseModel):
    """Partner-safe view: no assignee, no reviewer reasons, no internal stage notes."""

    id: uuid.UUID
    reference: str
    status: PortalStatus
    status_label: str
    pathway: EngagementPathway
    cover_note: str | None
    submission_count: int
    submitted_at: datetime | None
    open_information_requests: int


class ReadinessOut(BaseModel):
    complete: bool
    missing_profile_fields: list[str]
    missing_document_categories: list[str]


class PartnerHistoryItem(BaseModel):
    from_status: PortalStatus | None
    to_status: PortalStatus
    to_label: str
    note: str | None
    created_at: datetime


def application_out(app: PortalApplication, open_requests: int) -> ApplicationOut:
    return ApplicationOut(
        id=app.id,
        reference=app.reference,
        status=app.status,
        status_label=PARTNER_LABELS[app.status],
        pathway=app.pathway,
        cover_note=app.cover_note,
        submission_count=app.submission_count,
        submitted_at=app.submitted_at,
        open_information_requests=open_requests,
    )


def partner_history_item(h: ApplicationStatusHistory) -> PartnerHistoryItem:
    """Excludes `reason` (reviewer-only) and the acting user."""
    return PartnerHistoryItem(
        from_status=h.from_status,
        to_status=h.to_status,
        to_label=PARTNER_LABELS[h.to_status],
        note=h.partner_note,
        created_at=h.created_at,
    )
