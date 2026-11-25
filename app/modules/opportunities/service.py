"""Business logic for Project Exchange Steps 1-7."""

import secrets
import uuid
from datetime import UTC
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.common.utilities import utcnow
from app.core.exceptions import AppError, NotFoundError
from app.modules.auth.dependencies import PartnerContext, StaffContext
from app.modules.enquiries.activity import log_activity
from app.modules.enquiries.constants import ActorType
from app.modules.opportunities.constants import (
    OpportunityStatus,
    OpportunityVisibility,
    ProposalStatus,
)
from app.modules.opportunities.models import (
    EvaluationCriterion,
    OpportunityBriefAccess,
    OpportunityInvitation,
    OpportunityQuestion,
    ProjectOpportunity,
    ProjectProposal,
    ProposalScore,
)
from app.modules.opportunities.schemas import (
    AwardIn,
    CriteriaMatrixIn,
    OpportunityIntakeIn,
    OpportunityPublishIn,
    OpportunityStructureIn,
    ProposalDraftIn,
    ProposalScoresIn,
    ShortlistDecisionIn,
    ShortlistIn,
)
from app.modules.organizations.models import PartnerOrganization


def _ref(prefix: str) -> str:
    return f"{prefix}-{utcnow().year}-{secrets.token_hex(4).upper()}"


def _audit_staff(
    db: Session,
    staff: StaffContext,
    rtype: str,
    rid: uuid.UUID,
    action: str,
    meta: dict[str, Any] | None = None,
    org_id: uuid.UUID | None = None,
) -> None:
    log_activity(
        db,
        rtype,
        rid,
        action,
        meta,
        ActorType.STAFF,
        actor_user_id=staff.user.id,
        organization_id=org_id,
    )


def _audit_partner(
    db: Session,
    partner: PartnerContext,
    rtype: str,
    rid: uuid.UUID,
    action: str,
    meta: dict[str, Any] | None = None,
) -> None:
    log_activity(
        db,
        rtype,
        rid,
        action,
        meta,
        ActorType.PARTNER,
        actor_user_id=partner.user.id,
        organization_id=partner.organization_id,
    )


def _get_opp(db: Session, opp_id: uuid.UUID, lock: bool = False) -> ProjectOpportunity:
    stmt = select(ProjectOpportunity).where(ProjectOpportunity.id == opp_id)
    opp = db.execute(stmt.with_for_update() if lock else stmt).scalar_one_or_none()
    if opp is None:
        raise NotFoundError("Opportunity not found")
    return opp


def create_opportunity(
    db: Session, staff: StaffContext, data: OpportunityIntakeIn
) -> ProjectOpportunity:
    opp = ProjectOpportunity(
        reference=_ref("OPP"),
        title=data.title,
        category=data.category,
        summary=data.summary,
        status=OpportunityStatus.INTAKE,
        created_by=staff.user.id,
    )
    db.add(opp)
    db.flush()
    _audit_staff(db, staff, "opportunity", opp.id, "opportunity.created")
    return opp


def structure_opportunity(
    db: Session, staff: StaffContext, opp_id: uuid.UUID, data: OpportunityStructureIn
) -> ProjectOpportunity:
    opp = _get_opp(db, opp_id, lock=True)
    if opp.status not in (OpportunityStatus.INTAKE, OpportunityStatus.STRUCTURING):
        raise AppError(
            "Opportunity can only be structured during intake or structuring",
            status_code=409,
            code="INVALID_OPPORTUNITY_STATE",
        )
    if (
        data.budget_min is not None
        and data.budget_max is not None
        and data.budget_min > data.budget_max
    ):
        raise AppError(
            "budget_min cannot exceed budget_max", status_code=422, code="INVALID_BUDGET"
        )
    opp.scope = data.scope
    opp.required_skills = data.required_skills
    opp.budget_min = data.budget_min
    opp.budget_max = data.budget_max
    opp.currency = data.currency
    opp.expected_timeline = data.expected_timeline
    opp.geography = data.geography
    opp.compliance_requirements = data.compliance_requirements
    opp.acceptance_criteria = data.acceptance_criteria
    opp.submission_deadline = data.submission_deadline
    opp.structured_at = utcnow()
    opp.sourcing_manager_id = staff.user.id
    opp.status = OpportunityStatus.STRUCTURING
    _audit_staff(db, staff, "opportunity", opp.id, "opportunity.structured")
    return opp


def publish_opportunity(
    db: Session, staff: StaffContext, opp_id: uuid.UUID, data: OpportunityPublishIn
) -> ProjectOpportunity:
    opp = _get_opp(db, opp_id, lock=True)
    if opp.status not in (OpportunityStatus.STRUCTURING, OpportunityStatus.PUBLISHED):
        raise AppError(
            "Opportunity must be structured before publishing",
            status_code=409,
            code="INVALID_OPPORTUNITY_STATE",
        )
    if data.visibility is OpportunityVisibility.INVITE_ONLY and not data.invited_organization_ids:
        raise AppError(
            "Invite-only opportunity requires at least one invited organization",
            status_code=422,
            code="INVITATIONS_REQUIRED",
        )
    if data.visibility is OpportunityVisibility.CATEGORY_TARGETED and not data.target_categories:
        raise AppError(
            "Category-targeted opportunity requires target_categories",
            status_code=422,
            code="TARGET_CATEGORIES_REQUIRED",
        )
    opp.visibility = data.visibility
    opp.target_categories = data.target_categories or None
    opp.published_at = utcnow()
    opp.published_by = staff.user.id
    opp.status = OpportunityStatus.PUBLISHED

    if data.invited_organization_ids:
        db.execute(
            delete(OpportunityInvitation).where(OpportunityInvitation.opportunity_id == opp.id)
        )
        now = utcnow()
        for org_id in set(data.invited_organization_ids):
            if db.get(PartnerOrganization, org_id) is None:
                raise NotFoundError(f"Organization {org_id} not found")
            db.add(
                OpportunityInvitation(
                    opportunity_id=opp.id,
                    organization_id=org_id,
                    invited_by=staff.user.id,
                    invited_at=now,
                )
            )
    _audit_staff(
        db,
        staff,
        "opportunity",
        opp.id,
        "opportunity.published",
        {"visibility": data.visibility.value},
    )
    return opp


def partner_can_view(db: Session, partner: PartnerContext, opp: ProjectOpportunity) -> bool:
    if opp.published_at is None or opp.status in (
        OpportunityStatus.INTAKE,
        OpportunityStatus.STRUCTURING,
        OpportunityStatus.CANCELLED,
    ):
        return False
    if opp.visibility is OpportunityVisibility.PUBLIC:
        return True
    if opp.visibility is OpportunityVisibility.INVITE_ONLY:
        inv = db.execute(
            select(OpportunityInvitation).where(
                OpportunityInvitation.opportunity_id == opp.id,
                OpportunityInvitation.organization_id == partner.organization_id,
            )
        ).scalar_one_or_none()
        return inv is not None
    if opp.visibility is OpportunityVisibility.CATEGORY_TARGETED:
        org = db.get(PartnerOrganization, partner.organization_id)
        if org is None:
            return False
        targets = {c.strip().lower() for c in (opp.target_categories or []) if c.strip()}
        org_tags = set()
        if org.primary_industry:
            org_tags.add(org.primary_industry.strip().lower())
        if org.competencies:
            for item in org.competencies:
                org_tags.add(str(item).strip().lower())
        return bool(targets & org_tags) or opp.category.strip().lower() in org_tags
    return False


def get_partner_opportunity(
    db: Session, partner: PartnerContext, opp_id: uuid.UUID
) -> ProjectOpportunity:
    opp = _get_opp(db, opp_id)
    if not partner_can_view(db, partner, opp):
        raise NotFoundError("Opportunity not found")
    db.add(
        OpportunityBriefAccess(
            opportunity_id=opp.id,
            organization_id=partner.organization_id,
            user_id=partner.user.id,
            accessed_at=utcnow(),
        )
    )
    _audit_partner(db, partner, "opportunity", opp.id, "opportunity.brief_viewed")
    return opp


def _ensure_deadline_open(opp: ProjectOpportunity) -> None:
    if opp.status is not OpportunityStatus.PUBLISHED:
        raise AppError(
            "Opportunity is not accepting proposals",
            status_code=409,
            code="PROPOSALS_CLOSED",
        )
    if opp.submission_deadline is not None:
        dl = opp.submission_deadline
        if dl.tzinfo is None:
            dl = dl.replace(tzinfo=UTC)
        if utcnow() > dl:
            raise AppError(
                "Submission deadline has passed",
                status_code=409,
                code="DEADLINE_PASSED",
            )


def upsert_proposal_draft(
    db: Session, partner: PartnerContext, opp_id: uuid.UUID, data: ProposalDraftIn
) -> ProjectProposal:
    opp = _get_opp(db, opp_id)
    if not partner_can_view(db, partner, opp):
        raise NotFoundError("Opportunity not found")
    _ensure_deadline_open(opp)

    prop = db.execute(
        select(ProjectProposal)
        .where(
            ProjectProposal.opportunity_id == opp.id,
            ProjectProposal.organization_id == partner.organization_id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if prop is not None and prop.locked_at is not None:
        raise AppError(
            "Proposal is already submitted and locked",
            status_code=409,
            code="PROPOSAL_LOCKED",
        )
    if prop is None:
        prop = ProjectProposal(
            reference=_ref("PROP"),
            opportunity_id=opp.id,
            organization_id=partner.organization_id,
            submitted_by=partner.user.id,
            status=ProposalStatus.DRAFT,
        )
        db.add(prop)
        db.flush()
    prop.technical_approach = data.technical_approach
    prop.proposed_timeline = data.proposed_timeline
    prop.proposed_budget = data.proposed_budget
    prop.currency = data.currency
    prop.team_summary = data.team_summary
    prop.deliverables_plan = data.deliverables_plan
    prop.document_ids = data.document_ids or None
    _audit_partner(db, partner, "proposal", prop.id, "proposal.draft_saved")
    return prop


def submit_proposal(
    db: Session, partner: PartnerContext, proposal_id: uuid.UUID
) -> ProjectProposal:
    prop = db.execute(
        select(ProjectProposal)
        .where(
            ProjectProposal.id == proposal_id,
            ProjectProposal.organization_id == partner.organization_id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if prop is None:
        raise NotFoundError("Proposal not found")
    if prop.locked_at is not None or prop.status is not ProposalStatus.DRAFT:
        raise AppError(
            "Proposal is already submitted or closed", status_code=409, code="PROPOSAL_LOCKED"
        )
    opp = _get_opp(db, prop.opportunity_id)
    _ensure_deadline_open(opp)
    if not prop.technical_approach or prop.proposed_budget is None or not prop.proposed_timeline:
        raise AppError(
            "technical_approach, proposed_budget, and proposed_timeline are required to submit",
            status_code=422,
            code="INCOMPLETE_PROPOSAL",
        )
    now = utcnow()
    prop.status = ProposalStatus.SUBMITTED
    prop.submitted_at = now
    prop.locked_at = now
    prop.submitted_by = partner.user.id
    _audit_partner(db, partner, "proposal", prop.id, "proposal.submitted")
    return prop


def set_criteria_matrix(
    db: Session, staff: StaffContext, opp_id: uuid.UUID, data: CriteriaMatrixIn
) -> list[EvaluationCriterion]:
    opp = _get_opp(db, opp_id, lock=True)
    if sum(c.weight_percent for c in data.criteria) != 100:
        raise AppError(
            "Criteria weights must sum to exactly 100%",
            status_code=422,
            code="INVALID_WEIGHTS_SUM",
        )
    db.execute(delete(EvaluationCriterion).where(EvaluationCriterion.opportunity_id == opp.id))
    rows = []
    for idx, item in enumerate(data.criteria):
        c = EvaluationCriterion(
            opportunity_id=opp.id,
            name=item.name,
            description=item.description,
            weight_percent=item.weight_percent,
            max_score=item.max_score,
            position=idx,
        )
        db.add(c)
        rows.append(c)
    db.flush()
    _audit_staff(
        db,
        staff,
        "opportunity",
        opp.id,
        "opportunity.criteria_updated",
        {"count": len(rows)},
    )
    return rows


def score_proposal(
    db: Session, staff: StaffContext, proposal_id: uuid.UUID, data: ProposalScoresIn
) -> ProjectProposal:
    prop = db.execute(
        select(ProjectProposal).where(ProjectProposal.id == proposal_id).with_for_update()
    ).scalar_one_or_none()
    if prop is None:
        raise NotFoundError("Proposal not found")
    if prop.status in (ProposalStatus.DRAFT, ProposalStatus.WITHDRAWN):
        raise AppError(
            "Only submitted proposals can be scored",
            status_code=409,
            code="INVALID_PROPOSAL_STATE",
        )
    criteria = {
        c.id: c
        for c in db.execute(
            select(EvaluationCriterion).where(
                EvaluationCriterion.opportunity_id == prop.opportunity_id
            )
        )
        .scalars()
        .all()
    }
    if not criteria:
        raise AppError("Evaluation criteria not defined", status_code=409, code="NO_CRITERIA")

    for item in data.scores:
        crit = criteria.get(item.criterion_id)
        if crit is None:
            raise NotFoundError(f"Criterion {item.criterion_id} not found for this opportunity")
        if item.score > Decimal(crit.max_score):
            raise AppError(
                f"Score for {crit.name} exceeds max_score ({crit.max_score})",
                status_code=422,
                code="SCORE_EXCEEDS_MAX",
            )
        existing = db.execute(
            select(ProposalScore).where(
                ProposalScore.proposal_id == prop.id,
                ProposalScore.criterion_id == crit.id,
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                ProposalScore(
                    proposal_id=prop.id,
                    criterion_id=crit.id,
                    scorer_id=staff.user.id,
                    score=item.score,
                    rationale=item.rationale,
                )
            )
        else:
            existing.score = item.score
            existing.rationale = item.rationale
            existing.scorer_id = staff.user.id

    db.flush()
    all_scores = (
        db.execute(select(ProposalScore).where(ProposalScore.proposal_id == prop.id))
        .scalars()
        .all()
    )
    total = Decimal("0.00")
    for s in all_scores:
        crit = criteria[s.criterion_id]
        total += (s.score / Decimal(crit.max_score)) * Decimal(crit.weight_percent)
    prop.weighted_score = total.quantize(Decimal("0.01"))
    if prop.status is ProposalStatus.SUBMITTED:
        prop.status = ProposalStatus.UNDER_EVALUATION

    _audit_staff(
        db,
        staff,
        "proposal",
        prop.id,
        "proposal.scored",
        {"weighted_score": str(prop.weighted_score)},
        org_id=prop.organization_id,
    )
    return prop


def shortlist_proposals(
    db: Session, staff: StaffContext, opp_id: uuid.UUID, data: ShortlistIn
) -> ProjectOpportunity:
    opp = _get_opp(db, opp_id, lock=True)
    if opp.status not in (OpportunityStatus.PUBLISHED, OpportunityStatus.SHORTLISTING):
        raise AppError(
            "Opportunity is not open for shortlisting", status_code=409, code="INVALID_STATE"
        )
    proposals = (
        db.execute(
            select(ProjectProposal)
            .where(ProjectProposal.opportunity_id == opp.id)
            .with_for_update()
        )
        .scalars()
        .all()
    )
    by_id = {p.id: p for p in proposals}
    for pid in data.proposal_ids:
        p = by_id.get(pid)
        if p is None or p.status in (ProposalStatus.DRAFT, ProposalStatus.WITHDRAWN):
            raise AppError(
                f"Proposal {pid} cannot be shortlisted", status_code=422, code="INVALID_PROPOSAL"
            )

    selected = set(data.proposal_ids)
    for p in proposals:
        if p.id in selected:
            p.is_shortlisted = True
            p.shortlist_rank = data.proposal_ids.index(p.id) + 1
            p.shortlist_notes = data.notes
            p.status = ProposalStatus.SHORTLISTED
        elif p.status is ProposalStatus.SHORTLISTED:
            p.is_shortlisted = False
            p.shortlist_rank = None
            p.status = ProposalStatus.UNDER_EVALUATION

    opp.status = OpportunityStatus.SHORTLISTING
    opp.shortlisted_at = utcnow()
    opp.shortlisted_by = staff.user.id
    _audit_staff(
        db,
        staff,
        "opportunity",
        opp.id,
        "opportunity.shortlisted",
        {"count": len(selected)},
    )
    return opp


def decide_shortlist(
    db: Session, staff: StaffContext, opp_id: uuid.UUID, data: ShortlistDecisionIn
) -> ProjectOpportunity:
    opp = _get_opp(db, opp_id, lock=True)
    if opp.status is not OpportunityStatus.SHORTLISTING:
        raise AppError(
            "Opportunity is not awaiting shortlist decision", status_code=409, code="INVALID_STATE"
        )
    opp.shortlist_decision_notes = data.notes
    if data.approved:
        opp.shortlist_approved_at = utcnow()
        opp.shortlist_approved_by = staff.user.id
        action = "opportunity.shortlist_approved"
    else:
        opp.shortlist_approved_at = None
        opp.shortlist_approved_by = None
        opp.status = OpportunityStatus.PUBLISHED
        action = "opportunity.shortlist_rejected"
    _audit_staff(db, staff, "opportunity", opp.id, action)
    return opp


def award_opportunity(
    db: Session, staff: StaffContext, opp_id: uuid.UUID, data: AwardIn
) -> ProjectOpportunity:
    opp = _get_opp(db, opp_id, lock=True)
    if opp.shortlist_approved_at is None:
        raise AppError(
            "Shortlist must be approved by an Approver before award",
            status_code=409,
            code="SHORTLIST_NOT_APPROVED",
        )
    if opp.status is not OpportunityStatus.SHORTLISTING:
        raise AppError(
            "Opportunity cannot be awarded in current state", status_code=409, code="INVALID_STATE"
        )

    proposals = (
        db.execute(
            select(ProjectProposal)
            .where(ProjectProposal.opportunity_id == opp.id)
            .with_for_update()
        )
        .scalars()
        .all()
    )
    winner = next((p for p in proposals if p.id == data.proposal_id), None)
    if winner is None or not winner.is_shortlisted:
        raise AppError(
            "Awarded proposal must be on the approved shortlist",
            status_code=422,
            code="NOT_SHORTLISTED",
        )

    now = utcnow()
    for p in proposals:
        if p.id == winner.id:
            p.status = ProposalStatus.AWARDED
        elif p.status not in (ProposalStatus.DRAFT, ProposalStatus.WITHDRAWN):
            p.status = ProposalStatus.REJECTED

    opp.awarded_proposal_id = winner.id
    opp.awarded_at = now
    opp.status = OpportunityStatus.AWARDED
    _audit_staff(
        db,
        staff,
        "opportunity",
        opp.id,
        "opportunity.awarded",
        {"proposal_id": str(winner.id)},
        org_id=winner.organization_id,
    )
    return opp


def ask_question(
    db: Session, partner: PartnerContext, opp_id: uuid.UUID, question_text: str
) -> OpportunityQuestion:
    opp = _get_opp(db, opp_id)
    if not partner_can_view(db, partner, opp):
        raise NotFoundError("Opportunity not found")
    q = OpportunityQuestion(
        opportunity_id=opp.id,
        organization_id=partner.organization_id,
        asked_by=partner.user.id,
        question=question_text,
    )
    db.add(q)
    db.flush()
    _audit_partner(db, partner, "opportunity_question", q.id, "opportunity.question_asked")
    return q


def answer_question(
    db: Session,
    staff: StaffContext,
    opp_id: uuid.UUID,
    question_id: uuid.UUID,
    answer_text: str,
    is_public: bool,
) -> OpportunityQuestion:
    q = db.execute(
        select(OpportunityQuestion).where(
            OpportunityQuestion.id == question_id,
            OpportunityQuestion.opportunity_id == opp_id,
        )
    ).scalar_one_or_none()
    if q is None:
        raise NotFoundError("Question not found")
    q.answer = answer_text
    q.is_public = is_public
    q.answered_by = staff.user.id
    q.answered_at = utcnow()
    _audit_staff(
        db,
        staff,
        "opportunity_question",
        q.id,
        "opportunity.question_answered",
        {"is_public": is_public},
        org_id=q.organization_id,
    )
    return q


def withdraw_proposal(
    db: Session, partner: PartnerContext, proposal_id: uuid.UUID
) -> ProjectProposal:
    prop = db.execute(
        select(ProjectProposal)
        .where(
            ProjectProposal.id == proposal_id,
            ProjectProposal.organization_id == partner.organization_id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if prop is None:
        raise NotFoundError("Proposal not found")
    if prop.status in (ProposalStatus.AWARDED, ProposalStatus.REJECTED, ProposalStatus.WITHDRAWN):
        raise AppError(
            "Proposal cannot be withdrawn in its current state",
            status_code=409,
            code="INVALID_STATE",
        )
    prop.status = ProposalStatus.WITHDRAWN
    _audit_partner(db, partner, "proposal", prop.id, "proposal.withdrawn")
    return prop


def comparison_matrix(db: Session, opp_id: uuid.UUID) -> dict[str, Any]:
    opp = _get_opp(db, opp_id)
    criteria = (
        db.execute(
            select(EvaluationCriterion)
            .where(EvaluationCriterion.opportunity_id == opp.id)
            .order_by(EvaluationCriterion.position)
        )
        .scalars()
        .all()
    )
    proposals = (
        db.execute(
            select(ProjectProposal)
            .where(
                ProjectProposal.opportunity_id == opp.id,
                ProjectProposal.status.not_in([ProposalStatus.DRAFT, ProposalStatus.WITHDRAWN]),
            )
            .order_by(ProjectProposal.weighted_score.desc().nulls_last())
        )
        .scalars()
        .all()
    )
    prop_ids = [p.id for p in proposals]
    scores_by_prop: dict[uuid.UUID, dict[uuid.UUID, dict[str, Any]]] = {}
    if prop_ids:
        for s in db.execute(
            select(ProposalScore).where(ProposalScore.proposal_id.in_(prop_ids))
        ).scalars():
            scores_by_prop.setdefault(s.proposal_id, {})[s.criterion_id] = {
                "score": str(s.score),
                "rationale": s.rationale,
            }
    return {
        "opportunity_id": opp.id,
        "reference": opp.reference,
        "title": opp.title,
        "criteria": [
            {
                "id": c.id,
                "name": c.name,
                "weight_percent": c.weight_percent,
                "max_score": c.max_score,
            }
            for c in criteria
        ],
        "proposals": [
            {
                "proposal_id": p.id,
                "reference": p.reference,
                "organization_id": p.organization_id,
                "status": p.status.value,
                "proposed_budget": str(p.proposed_budget)
                if p.proposed_budget is not None
                else None,
                "weighted_score": str(p.weighted_score) if p.weighted_score is not None else None,
                "is_shortlisted": p.is_shortlisted,
                "shortlist_rank": p.shortlist_rank,
                "scores": scores_by_prop.get(p.id, {}),
            }
            for p in proposals
        ],
    }
