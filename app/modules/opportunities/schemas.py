import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.common.validation import Long, Short
from app.modules.opportunities.constants import (
    OpportunityStatus,
    OpportunityVisibility,
    ProposalStatus,
)


class OpportunityIntakeIn(BaseModel):
    title: Short
    category: str = Field(min_length=2, max_length=80)
    summary: Long | None = None


class OpportunityStructureIn(BaseModel):
    scope: Long
    required_skills: list[str] = Field(min_length=1, max_length=30)
    budget_min: Decimal | None = Field(default=None, ge=0)
    budget_max: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="INR", min_length=3, max_length=10)
    expected_timeline: str = Field(min_length=2, max_length=150)
    geography: str | None = Field(default=None, max_length=150)
    compliance_requirements: Long | None = None
    acceptance_criteria: Long | None = None
    submission_deadline: datetime


class OpportunityPublishIn(BaseModel):
    visibility: OpportunityVisibility
    target_categories: list[str] = Field(default_factory=list, max_length=20)
    invited_organization_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)


class OpportunityOut(BaseModel):
    id: uuid.UUID
    reference: str
    title: str
    category: str
    summary: str | None
    status: OpportunityStatus
    scope: str | None
    required_skills: list[str] | None
    budget_min: Decimal | None
    budget_max: Decimal | None
    currency: str
    expected_timeline: str | None
    geography: str | None
    compliance_requirements: str | None
    acceptance_criteria: str | None
    submission_deadline: datetime | None
    visibility: OpportunityVisibility | None
    target_categories: list[str] | None
    published_at: datetime | None
    shortlisted_at: datetime | None
    shortlist_approved_at: datetime | None
    awarded_proposal_id: uuid.UUID | None
    awarded_at: datetime | None
    created_at: datetime


class CriterionIn(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    description: Long | None = None
    weight_percent: int = Field(ge=1, le=100)
    max_score: int = Field(default=10, ge=1, le=100)


class CriteriaMatrixIn(BaseModel):
    criteria: list[CriterionIn] = Field(min_length=1, max_length=20)


class CriterionOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    weight_percent: int
    max_score: int
    position: int


class QuestionIn(BaseModel):
    question: Long


class AnswerIn(BaseModel):
    answer: Long
    is_public: bool = False


class QuestionOut(BaseModel):
    id: uuid.UUID
    opportunity_id: uuid.UUID
    organization_id: uuid.UUID
    question: str
    answer: str | None
    answered_at: datetime | None
    is_public: bool
    created_at: datetime


class ProposalDraftIn(BaseModel):
    technical_approach: Long | None = None
    proposed_timeline: str | None = Field(default=None, max_length=150)
    proposed_budget: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="INR", min_length=3, max_length=10)
    team_summary: Long | None = None
    deliverables_plan: Long | None = None
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)


class ProposalOut(BaseModel):
    id: uuid.UUID
    reference: str
    opportunity_id: uuid.UUID
    organization_id: uuid.UUID
    status: ProposalStatus
    technical_approach: str | None
    proposed_timeline: str | None
    proposed_budget: Decimal | None
    currency: str
    team_summary: str | None
    deliverables_plan: str | None
    document_ids: list[uuid.UUID] | None
    submitted_at: datetime | None
    locked_at: datetime | None
    weighted_score: Decimal | None
    is_shortlisted: bool
    shortlist_rank: int | None
    shortlist_notes: str | None
    created_at: datetime


class ScoreItemIn(BaseModel):
    criterion_id: uuid.UUID
    score: Decimal = Field(ge=0)
    rationale: Long | None = None


class ProposalScoresIn(BaseModel):
    scores: list[ScoreItemIn] = Field(min_length=1, max_length=20)


class ShortlistIn(BaseModel):
    proposal_ids: list[uuid.UUID] = Field(min_length=1, max_length=20)
    notes: Long | None = None


class ShortlistDecisionIn(BaseModel):
    approved: bool
    notes: Long | None = None


class AwardIn(BaseModel):
    proposal_id: uuid.UUID
    notes: Long | None = None
