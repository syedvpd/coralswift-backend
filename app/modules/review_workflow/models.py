import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from app.modules.applications.constants import PortalStatus


class ChecklistResult(enum.StrEnum):
    PENDING = "pending"
    PASSED = "pass"
    FAILED = "fail"
    NOT_APPLICABLE = "not_applicable"


class ReviewChecklistItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Reviewer-recorded checklist answer: pass, fail or not applicable plus a note (D9).
    No numerical scoring and no automated decision. `score`/`max_score` columns are legacy and
    unused (kept: no data is dropped)."""

    __tablename__ = "review_checklist_items"

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portal_applications.id", ondelete="RESTRICT"), index=True
    )
    stage: Mapped[PortalStatus] = mapped_column(enum_column(PortalStatus, "checklist_stage"))
    name: Mapped[str] = mapped_column(String(200))
    result: Mapped[ChecklistResult] = mapped_column(
        enum_column(ChecklistResult, "checklist_result"), default=ChecklistResult.PENDING
    )
    score: Mapped[int | None] = mapped_column(SmallInteger)
    max_score: Mapped[int | None] = mapped_column(SmallInteger)
    note: Mapped[str | None] = mapped_column(Text)
    updated_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))

    __table_args__ = (
        UniqueConstraint("application_id", "stage", "name", name="uq_checklist_app_stage_name"),
    )


class ApplicationException(UUIDPrimaryKeyMixin, Base):
    """Approved exception to a review rule: who approved it and why. Append-only."""

    __tablename__ = "application_exceptions"

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portal_applications.id", ondelete="RESTRICT"), index=True
    )
    rule: Mapped[str] = mapped_column(String(100))
    reason: Mapped[str] = mapped_column(Text)
    approver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ApplicationStageOwner(Base):
    __tablename__ = "application_stage_owners"

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portal_applications.id", ondelete="RESTRICT"), primary_key=True
    )
    stage: Mapped[PortalStatus] = mapped_column(
        enum_column(PortalStatus, "stage_owner_stage"), primary_key=True
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    updated_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EnquiryAssessment(UUIDPrimaryKeyMixin, Base):
    """Append-only assessment outcomes for an enquiry (latest wins). Outcome values are free
    slugs until the owner defines the list (D8)."""

    __tablename__ = "enquiry_assessments"

    enquiry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("enquiries.id", ondelete="RESTRICT"), index=True
    )
    outcome: Mapped[str] = mapped_column(String(40))
    note: Mapped[str | None] = mapped_column(Text)
    assessed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
