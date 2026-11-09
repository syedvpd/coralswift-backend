import uuid

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from app.modules.documents.constants import Classification
from app.modules.strategic.constants import DiscussionType


class StrategicEnquiry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Confidential by construction. No public read endpoint exists; Phase 3 must gate access
    on `access_classification`."""

    __tablename__ = "strategic_enquiries"

    enquiry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("enquiries.id", ondelete="RESTRICT"), unique=True
    )
    discussion_type: Mapped[DiscussionType] = mapped_column(
        enum_column(DiscussionType, "discussion_type")
    )
    business_overview: Mapped[str] = mapped_column(Text)
    confidential_summary: Mapped[str] = mapped_column(Text)
    access_classification: Mapped[Classification] = mapped_column(
        enum_column(Classification, "strategic_access_classification"),
        default=Classification.CONFIDENTIAL,
    )
