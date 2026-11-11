import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from app.modules.partner_documents.constants import PartnerDocCategory


class TaskStatus(enum.StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class OnboardingRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One onboarding file per organisation. Staff define the tasks; none are invented (D10)."""

    __tablename__ = "onboarding_records"

    reference: Mapped[str] = mapped_column(String(32), unique=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_organizations.id", ondelete="RESTRICT"), unique=True
    )
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("portal_applications.id", ondelete="RESTRICT")
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class OnboardingTask(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "onboarding_tasks"

    record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("onboarding_records.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[TaskStatus] = mapped_column(
        enum_column(TaskStatus, "onboarding_task_status"), default=TaskStatus.PENDING
    )
    required_action: Mapped[str | None] = mapped_column(Text)
    due_date: Mapped[date | None] = mapped_column(Date)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    document_category: Mapped[PartnerDocCategory | None] = mapped_column(
        enum_column(PartnerDocCategory, "onboarding_doc_category")
    )
    partner_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
