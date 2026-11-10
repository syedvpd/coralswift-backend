import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, UUIDPrimaryKeyMixin


class EnquiryFollowUp(UUIDPrimaryKeyMixin, Base):
    """Staff communication history / follow-up task on an enquiry (PRD s.14, s.15B)."""

    __tablename__ = "enquiry_followups"

    enquiry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("enquiries.id", ondelete="RESTRICT"), index=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    note: Mapped[str] = mapped_column(Text)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # note = internal note, follow_up = task with a due date, communication = logged contact
    kind: Mapped[str] = mapped_column(String(20), default="follow_up", server_default="follow_up")
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def status(self) -> str:
        return "cancelled" if self.cancelled_at else "completed" if self.completed_at else "open"

    __table_args__ = (
        Index("ix_followups_open_due", "completed_at", "due_at"),
        CheckConstraint("kind IN ('note', 'follow_up', 'communication')", name="kind_valid"),
    )


class SystemSetting(Base):
    """Operational settings (PRD s.14, s.28): SLA targets, queue owners, escalation, retention.
    Allowed keys and validation live in admin/settings_service.py."""

    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class NotificationTemplate(Base):
    """Staff-editable override of a built-in email template (PRD s.14)."""

    __tablename__ = "notification_templates"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    subject: Mapped[str] = mapped_column(String(200))
    text_body: Mapped[str] = mapped_column(Text)
    html_body: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
