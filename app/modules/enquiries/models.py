"""Company, Contact, Enquiry, Activity. Companies/contacts are never auto-merged: each
submission creates its own rows; de-duplication is a staff decision (Phase 3)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from app.modules.enquiries.constants import (
    ActorType,
    ConsentStatus,
    EnquiryStatus,
    EnquiryType,
    Priority,
)


class Company(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "companies"

    legal_name: Mapped[str] = mapped_column(String(200))
    website: Mapped[str | None] = mapped_column(String(300))
    year_established: Mapped[int | None] = mapped_column(SmallInteger)
    registered_address: Mapped[str | None] = mapped_column(String(500))
    country: Mapped[str | None] = mapped_column(String(2))
    business_category: Mapped[str | None] = mapped_column(String(100))

    __table_args__ = (
        CheckConstraint("year_established BETWEEN 1800 AND 2100", name="year_range"),
        CheckConstraint("country ~ '^[A-Z]{2}$'", name="country_iso2"),
    )


class Contact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "contacts"

    company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    full_name: Mapped[str] = mapped_column(String(150))
    designation: Mapped[str | None] = mapped_column(String(150))
    business_email: Mapped[str] = mapped_column(String(254), index=True)
    phone: Mapped[str] = mapped_column(String(20))
    country: Mapped[str] = mapped_column(String(2))
    consent_status: Mapped[ConsentStatus] = mapped_column(
        enum_column(ConsentStatus, "consent_status")
    )
    consent_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consent_notice_version: Mapped[str] = mapped_column(String(50))

    __table_args__ = (
        CheckConstraint("business_email = lower(business_email)", name="email_lowercase"),
        CheckConstraint("country ~ '^[A-Z]{2}$'", name="country_iso2"),
        CheckConstraint("phone ~ '^\\+[0-9]{7,15}$'", name="phone_e164"),
    )


class Enquiry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "enquiries"

    reference_number: Mapped[str] = mapped_column(String(32), unique=True)
    enquiry_type: Mapped[EnquiryType] = mapped_column(enum_column(EnquiryType, "enquiry_type"))
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contacts.id", ondelete="RESTRICT"), index=True
    )
    subject: Mapped[str] = mapped_column(String(200))
    # Null for partner/strategic: their free text lives in the type-specific table.
    message: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(50))
    status: Mapped[EnquiryStatus] = mapped_column(
        enum_column(EnquiryStatus, "enquiry_status"), default=EnquiryStatus.RECEIVED
    )
    priority: Mapped[Priority] = mapped_column(
        enum_column(Priority, "enquiry_priority"), default=Priority.NORMAL
    )
    assigned_owner: Mapped[str | None] = mapped_column(String(100))  # unused; see assigned_user_id
    # Phase 3 (migration 0008): lead owner and next follow-up (PRD s.15B)
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    next_follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    # SLA tracking (PRD s.28); targets come from system settings, none are invented
    response_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    first_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_enquiries_type_status_created", "enquiry_type", "status", "created_at"),
    )


class Activity(UUIDPrimaryKeyMixin, Base):
    """Append-only audit trail. `meta` must never contain PII or confidential text."""

    __tablename__ = "activities"

    record_type: Mapped[str] = mapped_column(String(50))
    record_id: Mapped[uuid.UUID]
    action: Mapped[str] = mapped_column(String(80))
    actor_type: Mapped[ActorType] = mapped_column(enum_column(ActorType, "activity_actor_type"))
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    # Phase 2 additions (migrations 0004/0005): who, for which organization, in which request.
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("partner_organizations.id", ondelete="RESTRICT"), index=True
    )
    request_id: Mapped[str | None] = mapped_column(String(64))
    # Added in 0019: origin of the request and whether the audited action succeeded.
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(200))
    outcome: Mapped[str] = mapped_column(String(10), default="success", server_default="success")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_activities_record", "record_type", "record_id"),)
