import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.common.validation import Long, Name
from app.modules.auth.constants import StaffRole
from app.modules.enquiries.constants import EnquiryStatus, EnquiryType, Priority


class EnquiryRow(BaseModel):
    id: uuid.UUID
    reference_number: str
    enquiry_type: EnquiryType
    subject: str
    status: EnquiryStatus
    priority: Priority
    source: str
    contact_name: str
    contact_email: str
    company_name: str | None
    assigned_user_id: uuid.UUID | None
    next_follow_up_at: datetime | None
    created_at: datetime
    updated_at: datetime | None = None
    contact_phone: str | None = None
    assigned_user_name: str | None = None
    first_response_at: datetime | None = None
    response_due_at: datetime | None = None
    category: str | None = None  # project category, or strategic discussion type


class EnquiryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: EnquiryStatus | None = None
    priority: Priority | None = None


class AssignIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID | None = Field(description="null clears the owner")


FollowUpKind = Literal["note", "follow_up", "communication"]


class FollowUpIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: Long
    due_at: datetime | None = None
    kind: FollowUpKind = "follow_up"  # note = internal, communication = contact with the requester
    assignee_id: uuid.UUID | None = None


class FollowUpUpdate(BaseModel):
    """Only the fields you send change; send null to clear due_at or assignee_id."""

    model_config = ConfigDict(extra="forbid")

    note: Long | None = None
    due_at: datetime | None = None
    assignee_id: uuid.UUID | None = None


class FollowUpOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    author_id: uuid.UUID
    note: str
    due_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    kind: str = "follow_up"
    status: str = "open"  # open | completed | cancelled
    cancelled_at: datetime | None = None
    assignee_id: uuid.UUID | None = None
    author_name: str | None = None
    assignee_name: str | None = None
    enquiry_id: uuid.UUID | None = None
    enquiry_reference: str | None = None


class ActivityOut(BaseModel):
    id: uuid.UUID
    action: str
    actor_type: str
    actor_user_id: uuid.UUID | None
    actor_name: str | None
    meta: dict[str, Any]
    created_at: datetime


class EnquiryDetail(BaseModel):
    enquiry: EnquiryRow
    message: str | None
    contact: dict[str, Any]
    company: dict[str, Any] | None
    details: dict[str, Any] | None
    documents: list[dict[str, Any]]
    follow_ups: list[FollowUpOut]


class OrgRow(BaseModel):
    id: uuid.UUID
    legal_name: str
    status: str
    country: str | None
    created_at: datetime
    open_application_status: str | None
    updated_at: datetime | None = None
    primary_contact: dict[str, Any] | None = None


class OrgStatusIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(pattern="^(active|suspended)$")
    reason: Long


class StaffInviteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    full_name: Name
    role: StaffRole


class StaffRoleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: StaffRole


class StaffOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    staff_role: StaffRole | None
    status: str
    mfa_enabled: bool
    last_login_at: datetime | None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AuditRow(BaseModel):
    id: uuid.UUID
    record_type: str
    record_id: uuid.UUID
    action: str
    actor_type: str
    actor_user_id: uuid.UUID | None
    organization_id: uuid.UUID | None
    request_id: str | None
    meta: dict[str, Any]
    created_at: datetime
    actor_name: str | None = None  # full name of actor_user_id
    is_strategic: bool = (
        False  # the record is a strategic/M&A enquiry (super administrators only see these rows)
    )


class NotificationRow(BaseModel):
    id: uuid.UUID
    recipient: str
    template: str
    notification_type: str
    status: str
    retry_count: int
    last_error: str | None
    created_at: datetime
    sent_at: datetime | None
    enquiry_id: uuid.UUID | None
    is_strategic: bool = False
