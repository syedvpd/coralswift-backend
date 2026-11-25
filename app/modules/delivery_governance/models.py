"""Steps 8-10 & Compliance: Contracts, Deliverables, Closure, Invoices, KYC/KYB Screening."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from app.modules.delivery_governance.constants import (
    ContractStatus,
    DeliverableStatus,
    InvoiceStatus,
    ScreeningStatus,
)


class ProjectContract(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Step 8: Digital contract with e-signature tracking & document vault link."""

    __tablename__ = "project_contracts"

    reference: Mapped[str] = mapped_column(String(32), unique=True)
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_opportunities.id", ondelete="RESTRICT"), index=True
    )
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_proposals.id", ondelete="RESTRICT"), index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("partner_projects.id", ondelete="RESTRICT"), index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_organizations.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    scope_summary: Mapped[str | None] = mapped_column(Text)
    contract_value: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    payment_terms: Mapped[str | None] = mapped_column(Text)
    effective_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[ContractStatus] = mapped_column(
        enum_column(ContractStatus, "contract_status"),
        default=ContractStatus.DRAFT,
        index=True,
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("partner_documents.id", ondelete="RESTRICT")
    )
    partner_signed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    partner_signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    partner_signature_hash: Mapped[str | None] = mapped_column(String(128))
    staff_countersigned_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    staff_countersigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    staff_signature_hash: Mapped[str | None] = mapped_column(String(128))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class MilestoneDeliverable(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Step 9: Deliverable submission & Delivery Manager acceptance per milestone."""

    __tablename__ = "milestone_deliverables"

    milestone_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project_milestones.id", ondelete="CASCADE"), index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_organizations.id", ondelete="RESTRICT"), index=True
    )
    submitted_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    acceptance_criteria: Mapped[str | None] = mapped_column(Text)
    document_ids: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(Uuid))
    status: Mapped[DeliverableStatus] = mapped_column(
        enum_column(DeliverableStatus, "deliverable_status"),
        default=DeliverableStatus.SUBMITTED,
        index=True,
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_notes: Mapped[str | None] = mapped_column(Text)


class MilestoneComment(UUIDPrimaryKeyMixin, Base):
    """Step 9: Structured milestone comments (not open chat)."""

    __tablename__ = "milestone_comments"

    milestone_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project_milestones.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    author_type: Mapped[str] = mapped_column(String(20))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProjectClosure(UUIDPrimaryKeyMixin, Base):
    """Step 10: Permanent project closure & partner rating record."""

    __tablename__ = "project_closures"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_projects.id", ondelete="RESTRICT"), unique=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_organizations.id", ondelete="RESTRICT"), index=True
    )
    summary: Mapped[str] = mapped_column(Text)
    outcomes: Mapped[str | None] = mapped_column(Text)
    lessons_learned: Mapped[str | None] = mapped_column(Text)
    partner_rating: Mapped[int] = mapped_column(Integer)
    delivery_quality_score: Mapped[int | None] = mapped_column(Integer)
    timeliness_score: Mapped[int | None] = mapped_column(Integer)
    communication_score: Mapped[int | None] = mapped_column(Integer)
    closed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("partner_rating BETWEEN 1 AND 5", name="partner_rating_range"),
    )


class ProjectInvoice(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Step 10: Partner invoicing & Finance payment status tracking."""

    __tablename__ = "project_invoices"

    invoice_number: Mapped[str] = mapped_column(String(32), unique=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_projects.id", ondelete="RESTRICT"), index=True
    )
    contract_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_contracts.id", ondelete="RESTRICT")
    )
    milestone_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_milestones.id", ondelete="RESTRICT")
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_organizations.id", ondelete="RESTRICT"), index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    description: Mapped[str | None] = mapped_column(Text)
    due_date: Mapped[date | None] = mapped_column(Date)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("partner_documents.id", ondelete="RESTRICT")
    )
    status: Mapped[InvoiceStatus] = mapped_column(
        enum_column(InvoiceStatus, "invoice_status"),
        default=InvoiceStatus.SUBMITTED,
        index=True,
    )
    submitted_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payment_reference: Mapped[str | None] = mapped_column(String(100))
    finance_notes: Mapped[str | None] = mapped_column(Text)


class PartnerComplianceScreening(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Section 8: KYC/KYB & sanctions/watchlist screening record for partner vetting."""

    __tablename__ = "partner_compliance_screenings"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_organizations.id", ondelete="RESTRICT"), unique=True
    )
    kyc_status: Mapped[ScreeningStatus] = mapped_column(
        enum_column(ScreeningStatus, "screening_status"), default=ScreeningStatus.PENDING
    )
    kyb_status: Mapped[ScreeningStatus] = mapped_column(
        enum_column(ScreeningStatus, "screening_status"), default=ScreeningStatus.PENDING
    )
    sanctions_status: Mapped[ScreeningStatus] = mapped_column(
        enum_column(ScreeningStatus, "screening_status"), default=ScreeningStatus.PENDING
    )
    screening_notes: Mapped[str | None] = mapped_column(Text)
    screened_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    screened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
