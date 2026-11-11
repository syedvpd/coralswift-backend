import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from app.modules.applications.constants import (
    MessageKind,
    MessageStatus,
    PortalStatus,
    VerificationOutcome,
)
from app.modules.partners.constants import EngagementPathway


class PortalApplication(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "portal_applications"

    reference: Mapped[str] = mapped_column(String(32), unique=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_organizations.id", ondelete="RESTRICT"), index=True
    )
    pathway: Mapped[EngagementPathway] = mapped_column(
        enum_column(EngagementPathway, "portal_app_pathway")
    )
    status: Mapped[PortalStatus] = mapped_column(
        enum_column(PortalStatus, "portal_app_status"), default=PortalStatus.DRAFT
    )
    resume_status: Mapped[PortalStatus | None] = mapped_column(
        enum_column(PortalStatus, "portal_app_resume_status")
    )
    cover_note: Mapped[str | None] = mapped_column(Text)
    assigned_reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    submission_count: Mapped[int] = mapped_column(Integer, default=0)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        # Technical guard against duplicate/concurrent applications (business rule unconfirmed).
        Index(
            "uq_portal_app_one_open_per_org",
            "organization_id",
            unique=True,
            postgresql_where=text("status NOT IN ('rejected', 'withdrawn')"),
        ),
        Index("ix_portal_apps_status", "status"),
    )


class ApplicationSubmission(UUIDPrimaryKeyMixin, Base):
    """Immutable snapshot taken at each (re)submission; previous submissions are preserved."""

    __tablename__ = "application_submissions"

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portal_applications.id", ondelete="RESTRICT")
    )
    submission_no: Mapped[int] = mapped_column(Integer)
    submitted_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)

    __table_args__ = (UniqueConstraint("application_id", "submission_no", name="uq_submission_no"),)


class ApplicationStatusHistory(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "application_status_history"

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portal_applications.id", ondelete="RESTRICT"), index=True
    )
    from_status: Mapped[PortalStatus | None] = mapped_column(
        enum_column(PortalStatus, "history_from_status")
    )
    to_status: Mapped[PortalStatus] = mapped_column(enum_column(PortalStatus, "history_to_status"))
    actor_type: Mapped[str] = mapped_column(String(20))
    actor_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    reason: Mapped[str | None] = mapped_column(Text)  # reviewer-only
    partner_note: Mapped[str | None] = mapped_column(Text)  # partner-visible
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EligibilityVerification(UUIDPrimaryKeyMixin, Base):
    """Append-only human verification record. No thresholds are evaluated anywhere in code."""

    __tablename__ = "eligibility_verifications"

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portal_applications.id", ondelete="RESTRICT"), index=True
    )
    submission_no: Mapped[int] = mapped_column(Integer)
    verified_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    verified_operating_years: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    verified_personnel: Mapped[int | None] = mapped_column(Integer)
    verified_turnover_inr_crore: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    outcome: Mapped[VerificationOutcome] = mapped_column(
        enum_column(VerificationOutcome, "verification_outcome")
    )
    exception_note: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    supporting_version_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)

    __table_args__ = (
        CheckConstraint(
            "outcome <> 'verified_with_exception' OR exception_note IS NOT NULL",
            name="exception_needs_note",
        ),
    )


class ReviewerNote(UUIDPrimaryKeyMixin, Base):
    """Internal. No partner-facing route or schema may read this table."""

    __tablename__ = "reviewer_notes"

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portal_applications.id", ondelete="RESTRICT"), index=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ApplicationMessage(UUIDPrimaryKeyMixin, Base):
    """Partner-visible conversation (information requests and partner responses)."""

    __tablename__ = "application_messages"

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portal_applications.id", ondelete="RESTRICT"), index=True
    )
    kind: Mapped[MessageKind] = mapped_column(enum_column(MessageKind, "message_kind"))
    status: Mapped[MessageStatus | None] = mapped_column(
        enum_column(MessageStatus, "message_status")
    )
    author_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    body: Mapped[str] = mapped_column(Text)
    requested_categories: Mapped[list[str] | None] = mapped_column(ARRAY(String(50)))
    in_reply_to_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("application_messages.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_date: Mapped[date | None] = mapped_column(Date)  # information requests only (0024)
