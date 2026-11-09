import uuid
from datetime import datetime
from typing import Any

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


class EnquiryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: EnquiryStatus | None = None
    priority: Priority | None = None


class AssignIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID | None = Field(description="null clears the owner")


class FollowUpIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: Long
    due_at: datetime | None = None


class FollowUpOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    author_id: uuid.UUID
    note: str
    due_at: datetime | None
    completed_at: datetime | None
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
