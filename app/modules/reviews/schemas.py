import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.common.validation import Long
from app.modules.applications.constants import PortalStatus, VerificationOutcome
from app.modules.partner_documents.constants import PartnerDocCategory, ReviewStatus


class AssignIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_id: uuid.UUID | None = None  # null clears the reviewer


class TransitionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to_status: PortalStatus
    reason: Long | None = Field(default=None, description="Reviewer-only; required for decisions")
    partner_note: Long | None = Field(default=None, description="Shown to the partner")


class InformationRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: Long
    requested_categories: list[PartnerDocCategory] = Field(default_factory=list, max_length=8)
    due_date: date | None = Field(default=None, description="deadline shown to the partner")


class NoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: Long


class NoteOut(BaseModel):
    id: uuid.UUID
    author_id: uuid.UUID
    body: str
    created_at: datetime
    author_name: str | None = None


class EligibilityIn(BaseModel):
    """Values are typed in by the reviewer from evidence; nothing is computed or compared."""

    model_config = ConfigDict(extra="forbid")

    verified_operating_years: Decimal | None = Field(default=None, ge=0, le=500, decimal_places=1)
    verified_personnel: int | None = Field(default=None, ge=0, le=10_000_000)
    verified_turnover_inr_crore: Decimal | None = Field(
        default=None, ge=0, max_digits=14, decimal_places=2
    )
    outcome: VerificationOutcome
    exception_note: Long | None = None
    notes: Long | None = None
    supporting_version_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _exception_needs_explanation(self) -> "EligibilityIn":
        if self.outcome is VerificationOutcome.VERIFIED_WITH_EXCEPTION and not self.exception_note:
            raise ValueError(
                "exception_note is required when the outcome is verified_with_exception"
            )
        return self


class EligibilityOut(BaseModel):
    id: uuid.UUID
    submission_no: int
    verified_by: uuid.UUID
    verified_at: datetime
    verified_operating_years: Decimal | None
    verified_personnel: int | None
    verified_turnover_inr_crore: Decimal | None
    outcome: VerificationOutcome
    exception_note: str | None
    notes: str | None
    supporting_version_ids: list[str]


class DocumentReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version_no: int | None = Field(default=None, ge=1)
    status: ReviewStatus
    comment: Long | None = Field(default=None, description="Visible to the partner")

    @model_validator(mode="after")
    def _comment_for_negative(self) -> "DocumentReviewIn":
        negative = (
            ReviewStatus.REJECTED,
            ReviewStatus.CLARIFICATION_NEEDED,
            ReviewStatus.REPLACEMENT_REQUESTED,
        )
        if self.status in negative and not self.comment:
            raise ValueError("a comment is required when rejecting or asking for clarification")
        return self


class ReviewerApplicationOut(BaseModel):
    id: uuid.UUID
    reference: str
    organization_id: uuid.UUID
    organization_name: str
    status: PortalStatus
    pathway: str
    assigned_reviewer_id: uuid.UUID | None
    submission_count: int
    submitted_at: datetime | None
    updated_at: datetime | None = None
    decided_at: datetime | None = None
    assigned_reviewer_name: str | None = None
    primary_contact: dict[str, Any] | None = None  # first authorised contact of the organisation
    allowed_next: list[PortalStatus] = []  # statuses the reviewer may move it to from here


class HistoryItem(BaseModel):
    from_status: PortalStatus | None
    to_status: PortalStatus
    actor_type: str
    actor_user_id: uuid.UUID
    reason: str | None
    partner_note: str | None
    created_at: datetime
    actor_name: str | None = None


class ReviewerMessageOut(BaseModel):
    id: uuid.UUID
    kind: str
    status: str | None
    author_user_id: uuid.UUID
    body: str
    requested_categories: list[str] | None
    in_reply_to: uuid.UUID | None
    created_at: datetime
    due_date: date | None = None


class AuditItem(BaseModel):
    action: str
    actor_type: str
    actor_user_id: uuid.UUID | None
    request_id: str | None
    meta: dict[str, object]
    created_at: datetime
