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
    contact: "EnquiryContactOut"
    company: "EnquiryCompanyOut | None"
    details: "EnquiryDetailsOut | None"
    documents: list["EnquiryDocumentOut"]
    follow_ups: list[FollowUpOut]


class EnquiryContactOut(BaseModel):
    full_name: str
    designation: str | None
    business_email: EmailStr
    phone: str | None
    country: str | None
    consent_status: str
    consent_timestamp: datetime | None
    consent_notice_version: str | None


class EnquiryCompanyOut(BaseModel):
    legal_name: str
    website: str | None
    country: str | None
    year_established: int | None
    registered_address: str | None


class EnquiryDetailsOut(BaseModel):
    project_category: str | None = None
    requirement_summary: str | None = None
    scope: str | None = None
    expected_timeline: str | None = None
    estimated_volume: str | None = None
    geography: str | None = None
    security_constraints: str | None = None
    preferred_engagement_pathway: str | None = None
    workforce_range: str | None = None
    service_categories: list[str] | None = None
    infrastructure_summary: str | None = None
    client_experience: str | None = None
    application_status: str | None = None
    turnover_range: str | None = None
    client_references: list[dict[str, Any]] | None = None
    purpose: str | None = None
    preferred_slots: list[dict[str, Any]] | None = None
    timezone: str | None = None
    status: str | None = None
    calendar_checked: bool | None = None
    confirmed_start: datetime | None = None
    confirmed_end: datetime | None = None
    decision_note: str | None = None
    discussion_type: str | None = None
    business_overview: str | None = None
    confidential_summary: str | None = None
    access_classification: str | None = None


class EnquiryDocumentOut(BaseModel):
    id: uuid.UUID
    original_filename: str
    content_type: str
    file_size: int
    category: str | None
    classification: str
    upload_status: str


class OverviewActivityOut(BaseModel):
    action: str
    record_type: str
    actor_type: str
    created_at: datetime


class OverviewOut(BaseModel):
    enquiries: dict[str, int]
    unassigned_enquiries: int
    overdue_follow_ups: int
    sla_breached: int
    failed_notifications: int | None = None
    applications: dict[str, int] | None = None
    unassigned_applications: int | None = None
    recent_activity: list[OverviewActivityOut] | None = None


class WorkloadRow(BaseModel):
    assignee_id: uuid.UUID | None
    assignee_name: str | None
    open_enquiries: int
    overdue_follow_ups: int
    sla_breached: int


class WorkloadOut(BaseModel):
    rows: list[WorkloadRow]
    totals: "WorkloadTotals"


class WorkloadTotals(BaseModel):
    open_enquiries: int
    overdue_follow_ups: int
    sla_breached: int


class KpiCountOut(BaseModel):
    type: str
    source: str
    count: int


class KpiStatusCountOut(BaseModel):
    type: str
    status: str
    count: int


class KpiCompletionOut(BaseModel):
    created: int
    submitted: int
    rate: float | None
    by_status: dict[str, int]


class KpiPortalAdoptionOut(BaseModel):
    active_partner_users: int


class KpisOut(BaseModel):
    avg_hours_to_first_follow_up: float | None
    enquiries_by_type_and_source: list[KpiCountOut]
    enquiries_by_type_and_status: list[KpiStatusCountOut]
    overdue_follow_ups: int
    meeting_requests_by_status: dict[str, int]
    partner_application_completion: KpiCompletionOut | None = None
    portal_adoption: KpiPortalAdoptionOut | None = None
    eligibility_outcomes_recorded: dict[str, int] | None = None
    document_review_turnaround_hours_avg: float | None = None


class ReportCountOut(BaseModel):
    key: str
    count: int


class ReportPeriodCountOut(BaseModel):
    period: datetime
    count: int


class FollowUpReportOut(BaseModel):
    total: int
    by_kind: list[ReportCountOut]
    by_status: list[ReportCountOut]
    by_month: list[ReportPeriodCountOut]


class DocumentReviewReportOut(BaseModel):
    total_versions: int
    by_review_status: list[ReportCountOut]
    avg_turnaround_hours: float | None


class CommunicationReportOut(BaseModel):
    total: int
    by_delivery_status: list[ReportCountOut]
    by_template: list[ReportCountOut]


class OrganizationProfileOut(BaseModel):
    legal_name: str
    status: str
    year_established: int | None
    employee_count: int | None
    registered_address: str | None
    country: str | None
    website: str | None
    service_categories: list[str] | None
    technical_capabilities: str | None
    business_description: str | None
    registration_number: str | None = None
    annual_turnover_inr_crore: float | None = None
    client_references: list[dict[str, Any]] | None = None
    authorized_contacts: list[dict[str, Any]] | None = None


class OrganizationApplicationOut(BaseModel):
    id: uuid.UUID
    reference: str
    status: str
    assigned_reviewer_id: uuid.UUID | None


class OrganizationDetailOut(BaseModel):
    profile: OrganizationProfileOut
    applications: list[OrganizationApplicationOut]


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
