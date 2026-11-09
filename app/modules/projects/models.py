import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from app.modules.projects.constants import ProjectCategory


class ProjectEnquiry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "project_enquiries"

    enquiry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("enquiries.id", ondelete="RESTRICT"), unique=True
    )
    project_category: Mapped[ProjectCategory] = mapped_column(
        enum_column(ProjectCategory, "project_category"), index=True
    )
    requirement_summary: Mapped[str] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(Text)
    expected_timeline: Mapped[str] = mapped_column(String(200))
    estimated_volume: Mapped[str | None] = mapped_column(String(200))
    geography: Mapped[str] = mapped_column(String(200))
    security_constraints: Mapped[str | None] = mapped_column(Text)
