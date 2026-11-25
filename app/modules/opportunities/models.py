"""Project Exchange Platform: Opportunities, Proposals, Evaluation Matrix, Shortlisting & Q&A."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from app.modules.opportunities.constants import (
    OpportunityStatus,
    OpportunityVisibility,
    ProposalStatus,
)


class ProjectOpportunity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "project_opportunities"

    reference: Mapped[str] = mapped_column(String(32), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(80), index=True)
    summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[OpportunityStatus] = mapped_column(
        enum_column(OpportunityStatus, "opportunity_status"),
        default=OpportunityStatus.INTAKE,
        index=True,
    )

    # Step 2: Structuring fields
    scope: Mapped[str | None] = mapped_column(Text)
    required_skills: Mapped[list[str] | None] = mapped_column(JSONB)
    budget_min: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    budget_max: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    expected_timeline: Mapped[str | None] = mapped_column(String(150))
    geography: Mapped[str | None] = mapped_column(String(150))
    compliance_requirements: Mapped[str | None] = mapped_column(Text)
    acceptance_criteria: Mapped[str | None] = mapped_column(Text)
    submission_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    structured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sourcing_manager_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )

    # Step 3: Publishing & Visibility
    visibility: Mapped[OpportunityVisibility | None] = mapped_column(
        enum_column(OpportunityVisibility, "opportunity_visibility")
    )
    target_categories: Mapped[list[str] | None] = mapped_column(JSONB)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )

    # Step 7: Shortlist review & Award
    shortlisted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shortlisted_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    shortlist_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shortlist_approved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    shortlist_decision_notes: Mapped[str | None] = mapped_column(Text)
    awarded_proposal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    awarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class OpportunityInvitation(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "opportunity_invitations"

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project_opportunities.id", ondelete="CASCADE"), index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_organizations.id", ondelete="RESTRICT"), index=True
    )
    invited_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    invited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("opportunity_id", "organization_id", name="uq_opp_invite"),)


class OpportunityBriefAccess(UUIDPrimaryKeyMixin, Base):
    """Logs every partner view of a published opportunity brief (Step 4 control)."""

    __tablename__ = "opportunity_brief_accesses"

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project_opportunities.id", ondelete="CASCADE"), index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_organizations.id", ondelete="RESTRICT"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    accessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OpportunityQuestion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Structured clarification Q&A on an opportunity (not open chat)."""

    __tablename__ = "opportunity_questions"

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project_opportunities.id", ondelete="CASCADE"), index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_organizations.id", ondelete="RESTRICT"), index=True
    )
    asked_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text)
    answered_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)


class ProjectProposal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Step 5: Partner proposal with draft/submit/lock lifecycle."""

    __tablename__ = "project_proposals"

    reference: Mapped[str] = mapped_column(String(32), unique=True)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project_opportunities.id", ondelete="RESTRICT"), index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_organizations.id", ondelete="RESTRICT"), index=True
    )
    submitted_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    status: Mapped[ProposalStatus] = mapped_column(
        enum_column(ProposalStatus, "proposal_status"),
        default=ProposalStatus.DRAFT,
        index=True,
    )
    technical_approach: Mapped[str | None] = mapped_column(Text)
    proposed_timeline: Mapped[str | None] = mapped_column(String(150))
    proposed_budget: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    team_summary: Mapped[str | None] = mapped_column(Text)
    deliverables_plan: Mapped[str | None] = mapped_column(Text)
    document_ids: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(Uuid))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Step 6 & 7: Evaluation & Shortlist
    weighted_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    is_shortlisted: Mapped[bool] = mapped_column(Boolean, default=False)
    shortlist_rank: Mapped[int | None] = mapped_column(Integer)
    shortlist_notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("opportunity_id", "organization_id", name="uq_opp_org_proposal"),
    )


class EvaluationCriterion(UUIDPrimaryKeyMixin, Base):
    """Step 6: Weighted evaluation criteria matrix per opportunity."""

    __tablename__ = "evaluation_criteria"

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project_opportunities.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text)
    weight_percent: Mapped[int] = mapped_column(Integer)
    max_score: Mapped[int] = mapped_column(Integer, default=10)
    position: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        CheckConstraint("weight_percent BETWEEN 1 AND 100", name="weight_range"),
        CheckConstraint("max_score > 0", name="max_score_positive"),
    )


class ProposalScore(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Step 6: Individual criterion score for a proposal, audited in Activity."""

    __tablename__ = "proposal_scores"

    proposal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project_proposals.id", ondelete="CASCADE"), index=True
    )
    criterion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluation_criteria.id", ondelete="CASCADE"), index=True
    )
    scorer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    score: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    rationale: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("proposal_id", "criterion_id", name="uq_proposal_criterion_score"),
    )
