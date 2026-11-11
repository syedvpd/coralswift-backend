import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PerformanceEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One staff-recorded indicator value for an organisation and period. Which indicators exist
    and how they are calculated is the owner's decision (D39): staff supply the label and the
    written definition; nothing is computed here. Partners see only published entries."""

    __tablename__ = "performance_entries"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_organizations.id", ondelete="RESTRICT"), index=True
    )
    period: Mapped[str] = mapped_column(String(20))  # e.g. 2026-Q3 (sortable text)
    indicator_key: Mapped[str] = mapped_column(String(40))
    label: Mapped[str] = mapped_column(String(120))
    value: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    unit: Mapped[str | None] = mapped_column(String(30))
    definition: Mapped[str] = mapped_column(Text)  # the documented calculation, shown to partners
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))

    __table_args__ = (
        UniqueConstraint(
            "organization_id", "period", "indicator_key", name="uq_perf_org_period_key"
        ),
    )


class PerformanceFeedback(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "performance_feedback"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_organizations.id", ondelete="RESTRICT"), index=True
    )
    period: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
