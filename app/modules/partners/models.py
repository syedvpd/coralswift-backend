import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from app.modules.partners.constants import (
    ApplicationStatus,
    EngagementPathway,
    TurnoverRange,
    WorkforceRange,
)


class PartnerApplication(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Submitted values are recorded as-is for human review. Nothing here decides eligibility."""

    __tablename__ = "partner_applications"

    enquiry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("enquiries.id", ondelete="RESTRICT"), unique=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    preferred_engagement_pathway: Mapped[EngagementPathway] = mapped_column(
        enum_column(EngagementPathway, "engagement_pathway")
    )
    workforce_range: Mapped[WorkforceRange] = mapped_column(
        enum_column(WorkforceRange, "workforce_range")
    )
    turnover_range: Mapped[TurnoverRange] = mapped_column(
        enum_column(TurnoverRange, "turnover_range")
    )
    service_categories: Mapped[list[str]] = mapped_column(ARRAY(String(50)))
    infrastructure_summary: Mapped[str] = mapped_column(Text)
    client_experience: Mapped[str] = mapped_column(Text)
    client_references: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    application_status: Mapped[ApplicationStatus] = mapped_column(
        enum_column(ApplicationStatus, "application_status"),
        default=ApplicationStatus.SUBMITTED,
        index=True,
    )
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("cardinality(service_categories) >= 1", name="has_service_category"),
        CheckConstraint("jsonb_array_length(client_references) >= 2", name="two_client_references"),
    )
