import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.common.validation import Long, Short
from app.modules.delivery_governance.constants import (
    ContractStatus,
    DeliverableStatus,
    InvoiceStatus,
    ScreeningStatus,
)


class ContractCreateIn(BaseModel):
    organization_id: uuid.UUID
    opportunity_id: uuid.UUID | None = None
    proposal_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    title: Short
    scope_summary: Long | None = None
    contract_value: Decimal = Field(ge=0)
    currency: str = Field(default="INR", min_length=3, max_length=10)
    payment_terms: Long | None = None
    effective_date: date | None = None
    expiry_date: date | None = None
    document_id: uuid.UUID | None = None


class ContractSignIn(BaseModel):
    signer_name: Short
    accepted_terms: bool
    document_id: uuid.UUID | None = None


class ContractOut(BaseModel):
    id: uuid.UUID
    reference: str
    opportunity_id: uuid.UUID | None
    proposal_id: uuid.UUID | None
    project_id: uuid.UUID | None
    organization_id: uuid.UUID
    title: str
    scope_summary: str | None
    contract_value: Decimal
    currency: str
    payment_terms: str | None
    effective_date: date | None
    expiry_date: date | None
    status: ContractStatus
    document_id: uuid.UUID | None
    partner_signed_at: datetime | None
    staff_countersigned_at: datetime | None
    created_at: datetime


class DeliverableSubmitIn(BaseModel):
    title: Short
    description: Long | None = None
    acceptance_criteria: Long | None = None
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)


class DeliverableReviewIn(BaseModel):
    status: DeliverableStatus
    review_notes: Long | None = None


class DeliverableOut(BaseModel):
    id: uuid.UUID
    milestone_id: uuid.UUID
    organization_id: uuid.UUID
    title: str
    description: str | None
    acceptance_criteria: str | None
    document_ids: list[uuid.UUID] | None
    status: DeliverableStatus
    reviewed_at: datetime | None
    review_notes: str | None
    created_at: datetime


class MilestoneCommentIn(BaseModel):
    body: Long


class MilestoneCommentOut(BaseModel):
    id: uuid.UUID
    milestone_id: uuid.UUID
    user_id: uuid.UUID
    author_type: str
    body: str
    created_at: datetime


class ProjectClosureIn(BaseModel):
    summary: Long
    outcomes: Long | None = None
    lessons_learned: Long | None = None
    partner_rating: int = Field(ge=1, le=5)
    delivery_quality_score: int | None = Field(default=None, ge=1, le=5)
    timeliness_score: int | None = Field(default=None, ge=1, le=5)
    communication_score: int | None = Field(default=None, ge=1, le=5)


class ProjectClosureOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    organization_id: uuid.UUID
    summary: str
    outcomes: str | None
    lessons_learned: str | None
    partner_rating: int
    delivery_quality_score: int | None
    timeliness_score: int | None
    communication_score: int | None
    closed_at: datetime


class InvoiceSubmitIn(BaseModel):
    project_id: uuid.UUID
    contract_id: uuid.UUID | None = None
    milestone_id: uuid.UUID | None = None
    amount: Decimal = Field(gt=0)
    tax_amount: Decimal = Field(default=Decimal("0.00"), ge=0)
    currency: str = Field(default="INR", min_length=3, max_length=10)
    description: Long | None = None
    due_date: date | None = None
    document_id: uuid.UUID | None = None


class InvoiceStatusIn(BaseModel):
    status: InvoiceStatus
    payment_reference: str | None = Field(default=None, max_length=100)
    finance_notes: Long | None = None


class InvoiceOut(BaseModel):
    id: uuid.UUID
    invoice_number: str
    project_id: uuid.UUID
    contract_id: uuid.UUID | None
    milestone_id: uuid.UUID | None
    organization_id: uuid.UUID
    amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    currency: str
    description: str | None
    due_date: date | None
    document_id: uuid.UUID | None
    status: InvoiceStatus
    submitted_at: datetime
    approved_at: datetime | None
    paid_at: datetime | None
    payment_reference: str | None
    finance_notes: str | None


class ComplianceScreeningIn(BaseModel):
    kyc_status: ScreeningStatus
    kyb_status: ScreeningStatus
    sanctions_status: ScreeningStatus
    screening_notes: Long | None = None


class ComplianceScreeningOut(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    kyc_status: ScreeningStatus
    kyb_status: ScreeningStatus
    sanctions_status: ScreeningStatus
    screening_notes: str | None
    screened_at: datetime | None
