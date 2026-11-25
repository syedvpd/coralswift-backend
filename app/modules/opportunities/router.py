"""Routers for Project Exchange Steps 1-7 (Admin/Sourcing/Approver + Partner)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select

from app.common.pagination import PageDep, page_meta
from app.common.responses import ApiResponse, ErrorResponse, ok
from app.database.dependencies import DbSession
from app.modules.auth.constants import StaffRole
from app.modules.auth.dependencies import (
    ApproverDep,
    PartnerDep,
    SourcingDep,
    StaffContext,
    require_staff,
)
from app.modules.opportunities import service
from app.modules.opportunities.constants import OpportunityStatus
from app.modules.opportunities.models import (
    OpportunityQuestion,
    ProjectOpportunity,
    ProjectProposal,
)
from app.modules.opportunities.schemas import (
    AnswerIn,
    AwardIn,
    CriteriaMatrixIn,
    CriterionOut,
    OpportunityIntakeIn,
    OpportunityOut,
    OpportunityPublishIn,
    OpportunityStructureIn,
    ProposalDraftIn,
    ProposalOut,
    ProposalScoresIn,
    QuestionIn,
    QuestionOut,
    ShortlistDecisionIn,
    ShortlistIn,
)

admin_router = APIRouter(prefix="/admin/opportunities", tags=["admin-opportunities"])
partner_router = APIRouter(prefix="/partner", tags=["partner-opportunities"])
_ERR: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}
SourcingOrApproverDep = Annotated[
    StaffContext,
    Depends(
        require_staff(StaffRole.SOURCING_MANAGER, StaffRole.APPROVER, StaffRole.SUPER_ADMINISTRATOR)
    ),
]


def _opp_out(o: ProjectOpportunity) -> OpportunityOut:
    return OpportunityOut(
        id=o.id,
        reference=o.reference,
        title=o.title,
        category=o.category,
        summary=o.summary,
        status=o.status,
        scope=o.scope,
        required_skills=o.required_skills,
        budget_min=o.budget_min,
        budget_max=o.budget_max,
        currency=o.currency,
        expected_timeline=o.expected_timeline,
        geography=o.geography,
        compliance_requirements=o.compliance_requirements,
        acceptance_criteria=o.acceptance_criteria,
        submission_deadline=o.submission_deadline,
        visibility=o.visibility,
        target_categories=o.target_categories,
        published_at=o.published_at,
        shortlisted_at=o.shortlisted_at,
        shortlist_approved_at=o.shortlist_approved_at,
        awarded_proposal_id=o.awarded_proposal_id,
        awarded_at=o.awarded_at,
        created_at=o.created_at,
    )


def _prop_out(p: ProjectProposal) -> ProposalOut:
    return ProposalOut(
        id=p.id,
        reference=p.reference,
        opportunity_id=p.opportunity_id,
        organization_id=p.organization_id,
        status=p.status,
        technical_approach=p.technical_approach,
        proposed_timeline=p.proposed_timeline,
        proposed_budget=p.proposed_budget,
        currency=p.currency,
        team_summary=p.team_summary,
        deliverables_plan=p.deliverables_plan,
        document_ids=p.document_ids,
        submitted_at=p.submitted_at,
        locked_at=p.locked_at,
        weighted_score=p.weighted_score,
        is_shortlisted=p.is_shortlisted,
        shortlist_rank=p.shortlist_rank,
        shortlist_notes=p.shortlist_notes,
        created_at=p.created_at,
    )


def _q_out(q: OpportunityQuestion) -> QuestionOut:
    return QuestionOut(
        id=q.id,
        opportunity_id=q.opportunity_id,
        organization_id=q.organization_id,
        question=q.question,
        answer=q.answer,
        answered_at=q.answered_at,
        is_public=q.is_public,
        created_at=q.created_at,
    )


# ================================================================ Admin / Sourcing / Approver
@admin_router.post("", status_code=201, response_model=ApiResponse[OpportunityOut], responses=_ERR)
def create_opportunity(
    payload: OpportunityIntakeIn, staff: SourcingDep, db: DbSession
) -> ApiResponse[OpportunityOut]:
    return ok(_opp_out(service.create_opportunity(db, staff, payload)), "Opportunity created")


@admin_router.get("", response_model=ApiResponse[list[OpportunityOut]], responses=_ERR)
def list_opportunities(
    staff: SourcingOrApproverDep,
    db: DbSession,
    page: PageDep,
    status: Annotated[OpportunityStatus | None, Query()] = None,
) -> ApiResponse[list[OpportunityOut]]:
    stmt = select(ProjectOpportunity)
    if status is not None:
        stmt = stmt.where(ProjectOpportunity.status == status)
    total = len(db.execute(stmt).scalars().all())
    rows = (
        db.execute(
            stmt.order_by(ProjectOpportunity.created_at.desc())
            .limit(page.page_size)
            .offset(page.offset)
        )
        .scalars()
        .all()
    )
    return ok([_opp_out(r) for r in rows], meta=page_meta(page, total))


@admin_router.get("/{opp_id}", response_model=ApiResponse[OpportunityOut], responses=_ERR)
def get_opportunity(
    opp_id: uuid.UUID, staff: SourcingOrApproverDep, db: DbSession
) -> ApiResponse[OpportunityOut]:
    return ok(_opp_out(service._get_opp(db, opp_id)))


@admin_router.patch(
    "/{opp_id}/structure", response_model=ApiResponse[OpportunityOut], responses=_ERR
)
def structure_opportunity(
    opp_id: uuid.UUID, payload: OpportunityStructureIn, staff: SourcingDep, db: DbSession
) -> ApiResponse[OpportunityOut]:
    return ok(_opp_out(service.structure_opportunity(db, staff, opp_id, payload)), "Structured")


@admin_router.post("/{opp_id}/publish", response_model=ApiResponse[OpportunityOut], responses=_ERR)
def publish_opportunity(
    opp_id: uuid.UUID, payload: OpportunityPublishIn, staff: SourcingDep, db: DbSession
) -> ApiResponse[OpportunityOut]:
    return ok(_opp_out(service.publish_opportunity(db, staff, opp_id, payload)), "Published")


@admin_router.put(
    "/{opp_id}/criteria", response_model=ApiResponse[list[CriterionOut]], responses=_ERR
)
def set_criteria(
    opp_id: uuid.UUID, payload: CriteriaMatrixIn, staff: SourcingDep, db: DbSession
) -> ApiResponse[list[CriterionOut]]:
    rows = service.set_criteria_matrix(db, staff, opp_id, payload)
    return ok(
        [
            CriterionOut(
                id=c.id,
                name=c.name,
                description=c.description,
                weight_percent=c.weight_percent,
                max_score=c.max_score,
                position=c.position,
            )
            for c in rows
        ],
        "Criteria saved",
    )


@admin_router.get(
    "/{opp_id}/proposals", response_model=ApiResponse[list[ProposalOut]], responses=_ERR
)
def list_opportunity_proposals(
    opp_id: uuid.UUID, staff: SourcingOrApproverDep, db: DbSession
) -> ApiResponse[list[ProposalOut]]:
    service._get_opp(db, opp_id)
    rows = (
        db.execute(
            select(ProjectProposal)
            .where(ProjectProposal.opportunity_id == opp_id)
            .order_by(ProjectProposal.weighted_score.desc().nulls_last())
        )
        .scalars()
        .all()
    )
    return ok([_prop_out(p) for p in rows])


@admin_router.post(
    "/proposals/{proposal_id}/scores", response_model=ApiResponse[ProposalOut], responses=_ERR
)
def score_proposal(
    proposal_id: uuid.UUID, payload: ProposalScoresIn, staff: SourcingDep, db: DbSession
) -> ApiResponse[ProposalOut]:
    return ok(_prop_out(service.score_proposal(db, staff, proposal_id, payload)), "Proposal scored")


@admin_router.get(
    "/{opp_id}/comparison", response_model=ApiResponse[dict[str, Any]], responses=_ERR
)
def comparison_matrix(
    opp_id: uuid.UUID, staff: SourcingOrApproverDep, db: DbSession
) -> ApiResponse[dict[str, Any]]:
    return ok(service.comparison_matrix(db, opp_id))


@admin_router.post(
    "/{opp_id}/shortlist", response_model=ApiResponse[OpportunityOut], responses=_ERR
)
def shortlist_proposals(
    opp_id: uuid.UUID, payload: ShortlistIn, staff: SourcingDep, db: DbSession
) -> ApiResponse[OpportunityOut]:
    return ok(_opp_out(service.shortlist_proposals(db, staff, opp_id, payload)), "Shortlisted")


@admin_router.post(
    "/{opp_id}/shortlist/decision", response_model=ApiResponse[OpportunityOut], responses=_ERR
)
def decide_shortlist(
    opp_id: uuid.UUID, payload: ShortlistDecisionIn, staff: ApproverDep, db: DbSession
) -> ApiResponse[OpportunityOut]:
    return ok(
        _opp_out(service.decide_shortlist(db, staff, opp_id, payload)),
        "Shortlist decision recorded",
    )


@admin_router.post("/{opp_id}/award", response_model=ApiResponse[OpportunityOut], responses=_ERR)
def award_opportunity(
    opp_id: uuid.UUID, payload: AwardIn, staff: ApproverDep, db: DbSession
) -> ApiResponse[OpportunityOut]:
    return ok(
        _opp_out(service.award_opportunity(db, staff, opp_id, payload)), "Opportunity awarded"
    )


@admin_router.get(
    "/{opp_id}/questions", response_model=ApiResponse[list[QuestionOut]], responses=_ERR
)
def list_admin_questions(
    opp_id: uuid.UUID, staff: SourcingOrApproverDep, db: DbSession
) -> ApiResponse[list[QuestionOut]]:
    rows = (
        db.execute(
            select(OpportunityQuestion)
            .where(OpportunityQuestion.opportunity_id == opp_id)
            .order_by(OpportunityQuestion.created_at.asc())
        )
        .scalars()
        .all()
    )
    return ok([_q_out(q) for q in rows])


@admin_router.post(
    "/{opp_id}/questions/{question_id}/answer",
    response_model=ApiResponse[QuestionOut],
    responses=_ERR,
)
def answer_question(
    opp_id: uuid.UUID,
    question_id: uuid.UUID,
    payload: AnswerIn,
    staff: SourcingDep,
    db: DbSession,
) -> ApiResponse[QuestionOut]:
    q = service.answer_question(db, staff, opp_id, question_id, payload.answer, payload.is_public)
    return ok(_q_out(q), "Question answered")


# ================================================================ Partner Feed & Proposals
@partner_router.get(
    "/opportunities", response_model=ApiResponse[list[OpportunityOut]], responses=_ERR
)
def partner_list_opportunities(
    partner: PartnerDep, db: DbSession, page: PageDep
) -> ApiResponse[list[OpportunityOut]]:
    all_pub = (
        db.execute(
            select(ProjectOpportunity)
            .where(ProjectOpportunity.published_at.is_not(None))
            .order_by(ProjectOpportunity.published_at.desc())
        )
        .scalars()
        .all()
    )
    visible = [o for o in all_pub if service.partner_can_view(db, partner, o)]
    sliced = visible[page.offset : page.offset + page.page_size]
    return ok([_opp_out(o) for o in sliced], meta=page_meta(page, len(visible)))


@partner_router.get(
    "/opportunities/{opp_id}", response_model=ApiResponse[OpportunityOut], responses=_ERR
)
def partner_get_opportunity(
    opp_id: uuid.UUID, partner: PartnerDep, db: DbSession
) -> ApiResponse[OpportunityOut]:
    return ok(_opp_out(service.get_partner_opportunity(db, partner, opp_id)))


@partner_router.post(
    "/opportunities/{opp_id}/questions",
    status_code=201,
    response_model=ApiResponse[QuestionOut],
    responses=_ERR,
)
def partner_ask_question(
    opp_id: uuid.UUID, payload: QuestionIn, partner: PartnerDep, db: DbSession
) -> ApiResponse[QuestionOut]:
    return ok(
        _q_out(service.ask_question(db, partner, opp_id, payload.question)), "Question submitted"
    )


@partner_router.get(
    "/opportunities/{opp_id}/questions",
    response_model=ApiResponse[list[QuestionOut]],
    responses=_ERR,
)
def partner_list_questions(
    opp_id: uuid.UUID, partner: PartnerDep, db: DbSession
) -> ApiResponse[list[QuestionOut]]:
    opp = service._get_opp(db, opp_id)
    if not service.partner_can_view(db, partner, opp):
        from app.core.exceptions import NotFoundError

        raise NotFoundError("Opportunity not found")
    rows = (
        db.execute(
            select(OpportunityQuestion)
            .where(
                OpportunityQuestion.opportunity_id == opp_id,
                or_(
                    OpportunityQuestion.organization_id == partner.organization_id,
                    OpportunityQuestion.is_public.is_(True),
                ),
            )
            .order_by(OpportunityQuestion.created_at.asc())
        )
        .scalars()
        .all()
    )
    return ok([_q_out(q) for q in rows])


@partner_router.put(
    "/opportunities/{opp_id}/proposals",
    response_model=ApiResponse[ProposalOut],
    responses=_ERR,
)
def partner_save_proposal_draft(
    opp_id: uuid.UUID, payload: ProposalDraftIn, partner: PartnerDep, db: DbSession
) -> ApiResponse[ProposalOut]:
    return ok(_prop_out(service.upsert_proposal_draft(db, partner, opp_id, payload)), "Draft saved")


@partner_router.post(
    "/proposals/{proposal_id}/submit",
    response_model=ApiResponse[ProposalOut],
    responses=_ERR,
)
def partner_submit_proposal(
    proposal_id: uuid.UUID, partner: PartnerDep, db: DbSession
) -> ApiResponse[ProposalOut]:
    return ok(_prop_out(service.submit_proposal(db, partner, proposal_id)), "Proposal submitted")


@partner_router.post(
    "/proposals/{proposal_id}/withdraw",
    response_model=ApiResponse[ProposalOut],
    responses=_ERR,
)
def partner_withdraw_proposal(
    proposal_id: uuid.UUID, partner: PartnerDep, db: DbSession
) -> ApiResponse[ProposalOut]:
    return ok(_prop_out(service.withdraw_proposal(db, partner, proposal_id)), "Proposal withdrawn")


@partner_router.get("/proposals", response_model=ApiResponse[list[ProposalOut]], responses=_ERR)
def partner_list_proposals(
    partner: PartnerDep, db: DbSession, page: PageDep
) -> ApiResponse[list[ProposalOut]]:
    stmt = select(ProjectProposal).where(ProjectProposal.organization_id == partner.organization_id)
    total = len(db.execute(stmt).scalars().all())
    rows = (
        db.execute(
            stmt.order_by(ProjectProposal.created_at.desc())
            .limit(page.page_size)
            .offset(page.offset)
        )
        .scalars()
        .all()
    )
    return ok([_prop_out(p) for p in rows], meta=page_meta(page, total))
