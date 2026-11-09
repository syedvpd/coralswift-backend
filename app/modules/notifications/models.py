import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, SmallInteger, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from app.modules.notifications.constants import DeliveryStatus, NotificationType, TemplateKey


class Notification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Email outbox row, written in the same transaction as the enquiry (commit-then-send)."""

    __tablename__ = "notifications"

    enquiry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("enquiries.id", ondelete="SET NULL"), index=True
    )
    recipient: Mapped[str] = mapped_column(String(254))
    notification_type: Mapped[NotificationType] = mapped_column(
        enum_column(NotificationType, "notification_type")
    )
    template_key: Mapped[TemplateKey] = mapped_column(enum_column(TemplateKey, "template_key"))
    # Template variables only (reference, name). Never confidential free text.
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    delivery_status: Mapped[DeliveryStatus] = mapped_column(
        enum_column(DeliveryStatus, "delivery_status"), default=DeliveryStatus.PENDING
    )
    retry_count: Mapped[int] = mapped_column(SmallInteger, default=0)
    provider_reference: Mapped[str | None] = mapped_column(String(120))
    last_error: Mapped[str | None] = mapped_column(String(300))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # enquiry + template + recipient: a retry of the same logical email can never be queued twice.
    dedupe_key: Mapped[str] = mapped_column(String(320), unique=True)

    __table_args__ = (
        CheckConstraint("retry_count >= 0", name="retry_non_negative"),
        Index("ix_notifications_status_created", "delivery_status", "created_at"),
    )
