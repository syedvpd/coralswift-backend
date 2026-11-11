import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from app.modules.collaboration.constants import (
    CollabAction,
    CollabKind,
    CollabStatus,
    MessageDirection,
    MilestoneStatus,
    ProjectResponseKind,
    ProjectStatus,
)


class PartnerProject(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Engagement staff prepare for one organisation. Partners see it only once shared."""

    __tablename__ = "partner_projects"

    reference: Mapped[str] = mapped_column(String(32), unique=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_organizations.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(60))
    summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ProjectStatus] = mapped_column(
        enum_column(ProjectStatus, "partner_project_status"), default=ProjectStatus.PLANNING
    )
    contact_name: Mapped[str | None] = mapped_column(String(150))
    contact_email: Mapped[str | None] = mapped_column(String(254))
    contact_phone: Mapped[str | None] = mapped_column(String(30))
    shared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shared_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class ProjectMilestone(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "project_milestones"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_projects.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[MilestoneStatus] = mapped_column(
        enum_column(MilestoneStatus, "milestone_status"), default=MilestoneStatus.PENDING
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    position: Mapped[int] = mapped_column(Integer, default=0)


class ProjectResponse(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "project_responses"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_projects.id", ondelete="RESTRICT"), index=True
    )
    kind: Mapped[ProjectResponseKind] = mapped_column(
        enum_column(ProjectResponseKind, "project_response_kind")
    )
    body: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    document_ids: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(Uuid))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProjectDocumentLink(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "project_document_links"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_projects.id", ondelete="RESTRICT")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_documents.id", ondelete="RESTRICT")
    )
    linked_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("project_id", "document_id", name="uq_project_doc"),)


class PartnerMessage(UUIDPrimaryKeyMixin, Base):
    """Organisation-wide inbox item. `partner_visible=False` is a staff-only internal note."""

    __tablename__ = "partner_messages"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_organizations.id", ondelete="RESTRICT")
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("partner_projects.id", ondelete="RESTRICT")
    )
    direction: Mapped[MessageDirection] = mapped_column(
        enum_column(MessageDirection, "partner_message_direction")
    )
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    sender_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    sender_label: Mapped[str] = mapped_column(String(100))
    partner_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_partner_messages_org_created", "organization_id", "created_at"),)


class PartnerMessageRead(Base):
    __tablename__ = "partner_message_reads"

    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_messages.id", ondelete="RESTRICT"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True
    )
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PartnerMessageAttachment(Base):
    __tablename__ = "partner_message_attachments"

    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_messages.id", ondelete="RESTRICT"), primary_key=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_documents.id", ondelete="RESTRICT"), primary_key=True
    )


class CollabItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Discussion, meeting or follow-up staff share with one organisation."""

    __tablename__ = "collab_items"

    reference: Mapped[str] = mapped_column(String(32), unique=True)
    kind: Mapped[CollabKind] = mapped_column(enum_column(CollabKind, "collab_kind"))
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_organizations.id", ondelete="RESTRICT")
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("partner_projects.id", ondelete="RESTRICT")
    )
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str | None] = mapped_column(Text)
    status: Mapped[CollabStatus] = mapped_column(
        enum_column(CollabStatus, "collab_status"), default=CollabStatus.OPEN
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    location: Mapped[str | None] = mapped_column(String(300))
    shared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shared_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))

    __table_args__ = (Index("ix_collab_items_org_kind", "organization_id", "kind"),)


class OrganizationBdmAssignment(UUIDPrimaryKeyMixin, Base):
    """Explicit organisation -> business development manager assignment (D45). A BDM gets
    read-only access to an organisation only while an active row exists. History is kept."""

    __tablename__ = "organization_bdm_assignments"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_organizations.id", ondelete="RESTRICT"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    assigned_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    removed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(
            "uq_bdm_assignment_active",
            "organization_id",
            "user_id",
            unique=True,
            postgresql_where=text("removed_at IS NULL"),
        ),
    )


class CollabResponse(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "collab_responses"

    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collab_items.id", ondelete="RESTRICT"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    action: Mapped[CollabAction] = mapped_column(enum_column(CollabAction, "collab_action"))
    body: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
