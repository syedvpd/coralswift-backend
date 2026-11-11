import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from app.modules.organizations.constants import MembershipRole, MembershipStatus, OrgStatus


class PartnerOrganization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Company record + its profile. Separate from user accounts (see PartnerMembership)."""

    __tablename__ = "partner_organizations"

    legal_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[OrgStatus] = mapped_column(
        enum_column(OrgStatus, "org_status"), default=OrgStatus.ACTIVE
    )
    # Link to the Phase 1 public submission this organization came from (never auto-merged).
    source_enquiry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("enquiries.id", ondelete="RESTRICT"), index=True
    )
    registration_number: Mapped[str | None] = mapped_column(String(100))
    year_established: Mapped[int | None] = mapped_column(SmallInteger)
    employee_count: Mapped[int | None] = mapped_column(Integer)
    annual_turnover_inr_crore: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    registered_address: Mapped[str | None] = mapped_column(String(500))
    country: Mapped[str | None] = mapped_column(String(2))
    website: Mapped[str | None] = mapped_column(String(300))
    service_categories: Mapped[list[str] | None] = mapped_column(ARRAY(String(50)))
    technical_capabilities: Mapped[str | None] = mapped_column(Text)
    infrastructure_summary: Mapped[str | None] = mapped_column(Text)
    business_description: Mapped[str | None] = mapped_column(Text)
    client_references: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    authorized_contacts: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    profile_version: Mapped[int] = mapped_column(Integer, default=0)
    # Extended profile (0021); all optional and partner-editable (direct updates, revisions kept)
    trading_name: Mapped[str | None] = mapped_column(String(200))
    company_type: Mapped[str | None] = mapped_column(String(60))
    state: Mapped[str | None] = mapped_column(String(100))
    city: Mapped[str | None] = mapped_column(String(100))
    primary_industry: Mapped[str | None] = mapped_column(String(100))
    competencies: Mapped[list[str] | None] = mapped_column(ARRAY(String(100)))
    operating_model: Mapped[str | None] = mapped_column(String(100))
    coverage: Mapped[list[str] | None] = mapped_column(ARRAY(String(100)))
    years_of_experience: Mapped[int | None] = mapped_column(SmallInteger)
    offices: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    workforce: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    financial_period: Mapped[str | None] = mapped_column(String(30))
    additional_contacts: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)

    __table_args__ = (
        CheckConstraint("year_established BETWEEN 1800 AND 2100", name="year_range"),
        CheckConstraint("employee_count >= 0", name="employees_non_negative"),
        CheckConstraint("annual_turnover_inr_crore >= 0", name="turnover_non_negative"),
        CheckConstraint("country ~ '^[A-Z]{2}$'", name="country_iso2"),
        CheckConstraint("years_of_experience BETWEEN 0 AND 200", name="experience_range"),
    )


class PartnerMembership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "partner_memberships"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_organizations.id", ondelete="RESTRICT"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    role: Mapped[MembershipRole] = mapped_column(
        enum_column(MembershipRole, "membership_role"), default=MembershipRole.MEMBER
    )
    status: Mapped[MembershipStatus] = mapped_column(
        enum_column(MembershipStatus, "membership_status"), default=MembershipStatus.ACTIVE
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_membership_org_user"),
        # One active organization per user keeps tenant resolution unambiguous.
        Index(
            "uq_membership_one_active_org_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )


class PartnerProfileRevision(UUIDPrimaryKeyMixin, Base):
    """Append-only profile change history: {field: {old, new}} per revision."""

    __tablename__ = "partner_profile_revisions"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_organizations.id", ondelete="RESTRICT")
    )
    version: Mapped[int] = mapped_column(Integer)
    changed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    changes: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("organization_id", "version", name="uq_profile_revision_version"),
    )


class ProfileChangeRequest(UUIDPrimaryKeyMixin, Base):
    """Partner asks for a profile change that staff approve or reject (PRD s.13 profile update
    requests). Approval applies the changes through the normal revision-tracked update path."""

    __tablename__ = "profile_change_requests"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_organizations.id", ondelete="RESTRICT"), index=True
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    changes: Mapped[dict[str, Any]] = mapped_column(JSONB)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|approved|rejected
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    decision_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('pending','approved','rejected')", name="status_values"),
    )
