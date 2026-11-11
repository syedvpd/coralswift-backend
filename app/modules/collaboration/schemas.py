import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.common.validation import EmailAddress, Long, Name, Phone, Short
from app.modules.collaboration.constants import (
    CollabAction,
    CollabKind,
    CollabStatus,
    MilestoneStatus,
    ProjectResponseKind,
    ProjectStatus,
)


# ------------------------------------------------------------------ projects
class MilestoneOut(BaseModel):
    id: uuid.UUID
    title: str
    due_date: date | None
    status: MilestoneStatus
    completed_at: datetime | None


class ProjectResponseOut(BaseModel):
    id: uuid.UUID
    kind: ProjectResponseKind
    body: str | None
    author: str
    document_ids: list[uuid.UUID]
    created_at: datetime


class ProjectContact(BaseModel):
    name: str | None
    email: str | None
    phone: str | None


class LinkedDocument(BaseModel):
    id: uuid.UUID
    category: str


class PartnerProjectRow(BaseModel):
    id: uuid.UUID
    reference: str
    title: str
    category: str | None
    status: ProjectStatus
    status_label: str
    shared_at: datetime | None
    updated_at: datetime


class PartnerProjectDetail(PartnerProjectRow):
    summary: str | None
    contact: ProjectContact
    milestones: list[MilestoneOut]
    responses: list[ProjectResponseOut]
    documents: list[LinkedDocument]
    message_ids: list[uuid.UUID]
    acknowledged_at: datetime | None
    confirmed_at: datetime | None


class StaffProjectRow(PartnerProjectRow):
    organization_id: uuid.UUID
    organization_name: str
    is_shared: bool


class StaffProjectDetail(PartnerProjectDetail):
    organization_id: uuid.UUID
    organization_name: str
    is_shared: bool


class ProjectActionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: Long | None = None


class SubmitInformationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: Long | None = None
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=10)


class MilestoneIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Short
    due_date: date | None = None


class MilestoneUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Short | None = None
    due_date: date | None = None
    status: MilestoneStatus | None = None


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_id: uuid.UUID
    title: Short
    category: Short | None = None
    summary: Long | None = None
    contact_name: Name | None = None
    contact_email: EmailAddress | None = None
    contact_phone: Phone | None = None
    milestones: list[MilestoneIn] = Field(default_factory=list, max_length=30)


class ProjectUpdate(BaseModel):
    """Omitted = unchanged; explicit null clears nullable fields."""

    model_config = ConfigDict(extra="forbid")

    title: Short | None = None
    category: Short | None = None
    summary: Long | None = None
    status: ProjectStatus | None = None
    contact_name: Name | None = None
    contact_email: EmailAddress | None = None
    contact_phone: Phone | None = None


class LinkDocumentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: uuid.UUID


# ------------------------------------------------------------------ messages
class MessageAttachmentOut(BaseModel):
    document_id: uuid.UUID
    category: str


class PartnerInboxRow(BaseModel):
    id: uuid.UUID
    direction: str
    subject: str
    sender_label: str
    project_id: uuid.UUID | None
    is_read: bool
    has_attachments: bool
    created_at: datetime


class PartnerInboxDetail(PartnerInboxRow):
    body: str
    attachments: list[MessageAttachmentOut]


class PartnerMessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: Short
    body: Long
    project_id: uuid.UUID | None = None
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=10)


class StaffMessageIn(PartnerMessageIn):
    organization_id: uuid.UUID
    partner_visible: bool = Field(
        default=True, description="false stores a staff-only internal note the partner never sees"
    )


class StaffInboxRow(PartnerInboxRow):
    organization_id: uuid.UUID
    organization_name: str
    partner_visible: bool
    body: str


# ------------------------------------------------------------ collaboration
class CollabResponseOut(BaseModel):
    id: uuid.UUID
    action: CollabAction
    body: str | None
    author: str
    from_partner: bool
    created_at: datetime


class CollabRow(BaseModel):
    id: uuid.UUID
    reference: str
    kind: CollabKind
    title: str
    status: CollabStatus
    project_id: uuid.UUID | None
    due_at: datetime | None
    starts_at: datetime | None
    ends_at: datetime | None
    location: str | None
    shared_at: datetime | None
    updated_at: datetime


class CollabDetail(CollabRow):
    body: str | None
    responses: list[CollabResponseOut]
    allowed_actions: list[CollabAction]


class StaffCollabRow(CollabRow):
    organization_id: uuid.UUID
    organization_name: str
    is_shared: bool
    response_count: int


class StaffCollabDetail(CollabDetail):
    organization_id: uuid.UUID
    organization_name: str
    is_shared: bool


class CollabRespondIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: CollabAction = CollabAction.REPLY
    body: Long | None = None


class CollabCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_id: uuid.UUID
    kind: CollabKind
    title: Short
    body: Long | None = None
    project_id: uuid.UUID | None = None
    due_at: datetime | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    location: Short | None = None


class CollabUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Short | None = None
    body: Long | None = None
    due_at: datetime | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    location: Short | None = None


class StaffReplyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: Long
