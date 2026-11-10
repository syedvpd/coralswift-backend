import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column


class MeetingStatus(enum.StrEnum):
    REQUESTED = "requested"
    CONFIRMED = "confirmed"
    DECLINED = "declined"
    CANCELLED = "cancelled"


class PrivacyRequestKind(enum.StrEnum):
    ACCESS = "access"
    CORRECTION = "correction"
    DELETION = "deletion"


class PrivacyRequestStatus(enum.StrEnum):
    RECEIVED = "received"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REJECTED = "rejected"


class SubscriptionStatus(enum.StrEnum):
    SUBSCRIBED = "subscribed"
    UNSUBSCRIBED = "unsubscribed"


class MeetingRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Detail row of an enquiry of type 'meeting'. A meeting is only confirmed by staff after they
    checked real calendar availability (PRD s.12, s.15D); there is no calendar integration yet."""

    __tablename__ = "meeting_requests"

    enquiry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("enquiries.id", ondelete="RESTRICT"), unique=True
    )
    purpose: Mapped[str] = mapped_column(Text)
    preferred_slots: Mapped[list[Any]] = mapped_column(JSONB)
    timezone: Mapped[str] = mapped_column(String(64))
    status: Mapped[MeetingStatus] = mapped_column(
        enum_column(MeetingStatus, "meeting_status"), default=MeetingStatus.REQUESTED
    )
    calendar_checked: Mapped[bool] = mapped_column(Boolean, default=False)
    confirmed_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "status <> 'confirmed' OR (calendar_checked AND confirmed_start IS NOT NULL"
            " AND confirmed_end IS NOT NULL AND confirmed_end > confirmed_start)",
            name="confirm_needs_calendar_check",
        ),
    )


class PrivacyRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Access / correction / deletion request intake (PRD s.19). Identity checks and the actual
    data handling are manual staff procedures."""

    __tablename__ = "privacy_requests"

    reference: Mapped[str] = mapped_column(String(20), unique=True)
    email: Mapped[str] = mapped_column(String(254), index=True)
    kind: Mapped[PrivacyRequestKind] = mapped_column(
        enum_column(PrivacyRequestKind, "privacy_request_kind")
    )
    details: Mapped[str | None] = mapped_column(Text)
    status: Mapped[PrivacyRequestStatus] = mapped_column(
        enum_column(PrivacyRequestStatus, "privacy_request_status"),
        default=PrivacyRequestStatus.RECEIVED,
    )
    handled_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    resolution_note: Mapped[str | None] = mapped_column(Text)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Public requests prove control of the address by email link; partner requests are signed in.
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_token_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    verification_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )

    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None

    @property
    def submitted_by_partner(self) -> bool:
        return self.submitted_by_user_id is not None


class NewsletterSubscription(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Opt-in list only (PRD s.15E). Nothing is sent by this backend."""

    __tablename__ = "newsletter_subscriptions"

    email: Mapped[str] = mapped_column(String(254), unique=True)
    status: Mapped[SubscriptionStatus] = mapped_column(
        enum_column(SubscriptionStatus, "subscription_status"),
        default=SubscriptionStatus.SUBSCRIBED,
    )
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consent_notice_version: Mapped[str] = mapped_column(String(50))
    unsubscribed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
