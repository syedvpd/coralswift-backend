"""Routers for Steps 8-10 (Contracts, Deliverables, Closure, Invoices) & Compliance Screening."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.common.pagination import PageDep, page_meta
from app.common.responses import ApiResponse, ErrorResponse, ok
from app.core.exceptions import NotFoundError
from app.database.dependencies import DbSession
from app.modules.auth.constants import StaffRole
from app.modules.auth.dependencies import (
    ComplianceDep,
    DeliveryDep,
    FinanceDep,
    PartnerDep,
    StaffContext,
    require_staff,
)
from app.modules.collaboration.models import PartnerProject, ProjectMilestone
from app.modules.delivery_governance import service
from app.modules.delivery_governance.constants import InvoiceStatus
from app.modules.delivery_governance.models import (
    MilestoneComment,
    MilestoneDeliverable,
    PartnerComplianceScreening,
    ProjectClosure,
    ProjectContract,
    ProjectInvoice,
)
from app.modules.delivery_governance.schemas import (
    ComplianceScreeningIn,
    ComplianceScreeningOut,
    ContractCreateIn,
    ContractOut,
    ContractSignIn,
    DeliverableOut,
    DeliverableReviewIn,
    DeliverableSubmitIn,
    InvoiceOut,
    InvoiceStatusIn,
    InvoiceSubmitIn,
    MilestoneCommentIn,
    MilestoneCommentOut,
    ProjectClosureIn,
    ProjectClosureOut,
)

admin_router = APIRouter(prefix="/admin", tags=["admin-delivery-governance"])
partner_router = APIRouter(prefix="/partner", tags=["partner-delivery-governance"])
_ERR: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}
ContractAdminDep = Annotated[
    StaffContext,
    Depends(
        require_staff(
            StaffRole.SOURCING_MANAGER,
            StaffRole.APPROVER,
            StaffRole.DELIVERY_MANAGER,
            StaffRole.SUPER_ADMINISTRATOR,
        )
    ),
]


def _contract_out(c: ProjectContract) -> ContractOut:
    return ContractOut(
        id=c.id,
        reference=c.reference,
        opportunity_id=c.opportunity_id,
        proposal_id=c.proposal_id,
        project_id=c.project_id,
        organization_id=c.organization_id,
        title=c.title,
        scope_summary=c.scope_summary,
        contract_value=c.contract_value,
        currency=c.currency,
        payment_terms=c.payment_terms,
        effective_date=c.effective_date,
        expiry_date=c.expiry_date,
        status=c.status,
        document_id=c.document_id,
        partner_signed_at=c.partner_signed_at,
        staff_countersigned_at=c.staff_countersigned_at,
        created_at=c.created_at,
    )


def _deliv_out(d: MilestoneDeliverable) -> DeliverableOut:
    return DeliverableOut(
        id=d.id,
        milestone_id=d.milestone_id,
        organization_id=d.organization_id,
        title=d.title,
        description=d.description,
        acceptance_criteria=d.acceptance_criteria,
        document_ids=d.document_ids,
        status=d.status,
        reviewed_at=d.reviewed_at,
        review_notes=d.review_notes,
        created_at=d.created_at,
    )


def _closure_out(c: ProjectClosure) -> ProjectClosureOut:
    return ProjectClosureOut(
        id=c.id,
        project_id=c.project_id,
        organization_id=c.organization_id,
        summary=c.summary,
        outcomes=c.outcomes,
        lessons_learned=c.lessons_learned,
        partner_rating=c.partner_rating,
        delivery_quality_score=c.delivery_quality_score,
        timeliness_score=c.timeliness_score,
        communication_score=c.communication_score,
        closed_at=c.closed_at,
    )


def _invoice_out(i: ProjectInvoice) -> InvoiceOut:
    return InvoiceOut(
        id=i.id,
        invoice_number=i.invoice_number,
        project_id=i.project_id,
        contract_id=i.contract_id,
        milestone_id=i.milestone_id,
        organization_id=i.organization_id,
        amount=i.amount,
        tax_amount=i.tax_amount,
        total_amount=i.total_amount,
        currency=i.currency,
        description=i.description,
        due_date=i.due_date,
        document_id=i.document_id,
        status=i.status,
        submitted_at=i.submitted_at,
        approved_at=i.approved_at,
        paid_at=i.paid_at,
        payment_reference=i.payment_reference,
        finance_notes=i.finance_notes,
    )


# ================================================================ Admin: Contracts (Step 8)
@admin_router.post(
    "/contracts", status_code=201, response_model=ApiResponse[ContractOut], responses=_ERR
)
def admin_create_contract(
    payload: ContractCreateIn, staff: ContractAdminDep, db: DbSession
) -> ApiResponse[ContractOut]:
    return ok(_contract_out(service.create_contract(db, staff, payload)), "Contract created")


@admin_router.get("/contracts", response_model=ApiResponse[list[ContractOut]], responses=_ERR)
def admin_list_contracts(
    staff: ContractAdminDep, db: DbSession, page: PageDep
) -> ApiResponse[list[ContractOut]]:
    rows = (
        db.execute(select(ProjectContract).order_by(ProjectContract.created_at.desc()))
        .scalars()
        .all()
    )
    sliced = rows[page.offset : page.offset + page.page_size]
    return ok([_contract_out(c) for c in sliced], meta=page_meta(page, len(rows)))


@admin_router.post(
    "/contracts/{contract_id}/send", response_model=ApiResponse[ContractOut], responses=_ERR
)
def admin_send_contract(
    contract_id: uuid.UUID, staff: ContractAdminDep, db: DbSession
) -> ApiResponse[ContractOut]:
    return ok(
        _contract_out(service.send_contract_for_signature(db, staff, contract_id)),
        "Contract sent for signature",
    )


@admin_router.post(
    "/contracts/{contract_id}/countersign",
    response_model=ApiResponse[ContractOut],
    responses=_ERR,
)
def admin_countersign_contract(
    contract_id: uuid.UUID, payload: ContractSignIn, staff: ContractAdminDep, db: DbSession
) -> ApiResponse[ContractOut]:
    return ok(
        _contract_out(service.countersign_contract(db, staff, contract_id, payload)),
        "Contract countersigned and active",
    )


# ================================================================ Partner: Contracts (Step 8)
@partner_router.get("/contracts", response_model=ApiResponse[list[ContractOut]], responses=_ERR)
def partner_list_contracts(
    partner: PartnerDep, db: DbSession, page: PageDep
) -> ApiResponse[list[ContractOut]]:
    rows = (
        db.execute(
            select(ProjectContract)
            .where(ProjectContract.organization_id == partner.organization_id)
            .order_by(ProjectContract.created_at.desc())
        )
        .scalars()
        .all()
    )
    sliced = rows[page.offset : page.offset + page.page_size]
    return ok([_contract_out(c) for c in sliced], meta=page_meta(page, len(rows)))


@partner_router.post(
    "/contracts/{contract_id}/sign", response_model=ApiResponse[ContractOut], responses=_ERR
)
def partner_sign_contract(
    contract_id: uuid.UUID, payload: ContractSignIn, partner: PartnerDep, db: DbSession
) -> ApiResponse[ContractOut]:
    return ok(
        _contract_out(service.partner_sign_contract(db, partner, contract_id, payload)),
        "Contract signed",
    )


# ================================================================ Step 9: Deliverables & Comments
@partner_router.post(
    "/milestones/{milestone_id}/deliverables",
    status_code=201,
    response_model=ApiResponse[DeliverableOut],
    responses=_ERR,
)
def partner_submit_deliverable(
    milestone_id: uuid.UUID, payload: DeliverableSubmitIn, partner: PartnerDep, db: DbSession
) -> ApiResponse[DeliverableOut]:
    return ok(
        _deliv_out(service.submit_deliverable(db, partner, milestone_id, payload)),
        "Deliverable submitted",
    )


@admin_router.post(
    "/deliverables/{deliverable_id}/review",
    response_model=ApiResponse[DeliverableOut],
    responses=_ERR,
)
def admin_review_deliverable(
    deliverable_id: uuid.UUID, payload: DeliverableReviewIn, staff: DeliveryDep, db: DbSession
) -> ApiResponse[DeliverableOut]:
    return ok(
        _deliv_out(service.review_deliverable(db, staff, deliverable_id, payload)),
        "Deliverable reviewed",
    )


@partner_router.post(
    "/milestones/{milestone_id}/comments",
    status_code=201,
    response_model=ApiResponse[MilestoneCommentOut],
    responses=_ERR,
)
def partner_add_milestone_comment(
    milestone_id: uuid.UUID, payload: MilestoneCommentIn, partner: PartnerDep, db: DbSession
) -> ApiResponse[MilestoneCommentOut]:
    ms, _ = service._partner_milestone(db, partner, milestone_id)
    c = service.add_milestone_comment(
        db, ms.id, partner.user.id, "partner", payload.body, partner.organization_id
    )
    return ok(
        MilestoneCommentOut(
            id=c.id,
            milestone_id=c.milestone_id,
            user_id=c.user_id,
            author_type=c.author_type,
            body=c.body,
            created_at=c.created_at,
        ),
        "Comment added",
    )


@partner_router.get(
    "/milestones/{milestone_id}/comments",
    response_model=ApiResponse[list[MilestoneCommentOut]],
    responses=_ERR,
)
def partner_list_milestone_comments(
    milestone_id: uuid.UUID, partner: PartnerDep, db: DbSession
) -> ApiResponse[list[MilestoneCommentOut]]:
    ms, _ = service._partner_milestone(db, partner, milestone_id)
    rows = (
        db.execute(
            select(MilestoneComment)
            .where(MilestoneComment.milestone_id == ms.id)
            .order_by(MilestoneComment.created_at.asc())
        )
        .scalars()
        .all()
    )
    return ok(
        [
            MilestoneCommentOut(
                id=c.id,
                milestone_id=c.milestone_id,
                user_id=c.user_id,
                author_type=c.author_type,
                body=c.body,
                created_at=c.created_at,
            )
            for c in rows
        ]
    )


@admin_router.post(
    "/milestones/{milestone_id}/comments",
    status_code=201,
    response_model=ApiResponse[MilestoneCommentOut],
    responses=_ERR,
)
def admin_add_milestone_comment(
    milestone_id: uuid.UUID, payload: MilestoneCommentIn, staff: DeliveryDep, db: DbSession
) -> ApiResponse[MilestoneCommentOut]:
    row = db.execute(
        select(ProjectMilestone, PartnerProject)
        .join(PartnerProject, PartnerProject.id == ProjectMilestone.project_id)
        .where(ProjectMilestone.id == milestone_id)
    ).first()
    if row is None:
        raise NotFoundError("Milestone not found")
    ms, proj = row
    c = service.add_milestone_comment(
        db, ms.id, staff.user.id, "staff", payload.body, proj.organization_id
    )
    return ok(
        MilestoneCommentOut(
            id=c.id,
            milestone_id=c.milestone_id,
            user_id=c.user_id,
            author_type=c.author_type,
            body=c.body,
            created_at=c.created_at,
        ),
        "Comment added",
    )


# ================================================================ Step 10: Closure & Invoices
@admin_router.post(
    "/projects/{project_id}/close",
    status_code=201,
    response_model=ApiResponse[ProjectClosureOut],
    responses=_ERR,
)
def admin_close_project(
    project_id: uuid.UUID, payload: ProjectClosureIn, staff: DeliveryDep, db: DbSession
) -> ApiResponse[ProjectClosureOut]:
    return ok(_closure_out(service.close_project(db, staff, project_id, payload)), "Project closed")


@admin_router.get(
    "/projects/{project_id}/closure",
    response_model=ApiResponse[ProjectClosureOut],
    responses=_ERR,
)
def admin_get_closure(
    project_id: uuid.UUID, staff: DeliveryDep, db: DbSession
) -> ApiResponse[ProjectClosureOut]:
    c = db.execute(
        select(ProjectClosure).where(ProjectClosure.project_id == project_id)
    ).scalar_one_or_none()
    if c is None:
        raise NotFoundError("Closure record not found")
    return ok(_closure_out(c))


@partner_router.get(
    "/projects/{project_id}/closure",
    response_model=ApiResponse[ProjectClosureOut],
    responses=_ERR,
)
def partner_get_closure(
    project_id: uuid.UUID, partner: PartnerDep, db: DbSession
) -> ApiResponse[ProjectClosureOut]:
    c = db.execute(
        select(ProjectClosure).where(
            ProjectClosure.project_id == project_id,
            ProjectClosure.organization_id == partner.organization_id,
        )
    ).scalar_one_or_none()
    if c is None:
        raise NotFoundError("Closure record not found")
    return ok(_closure_out(c))


@partner_router.post(
    "/invoices", status_code=201, response_model=ApiResponse[InvoiceOut], responses=_ERR
)
def partner_submit_invoice(
    payload: InvoiceSubmitIn, partner: PartnerDep, db: DbSession
) -> ApiResponse[InvoiceOut]:
    return ok(_invoice_out(service.submit_invoice(db, partner, payload)), "Invoice submitted")


@partner_router.get("/invoices", response_model=ApiResponse[list[InvoiceOut]], responses=_ERR)
def partner_list_invoices(
    partner: PartnerDep, db: DbSession, page: PageDep
) -> ApiResponse[list[InvoiceOut]]:
    rows = (
        db.execute(
            select(ProjectInvoice)
            .where(ProjectInvoice.organization_id == partner.organization_id)
            .order_by(ProjectInvoice.submitted_at.desc())
        )
        .scalars()
        .all()
    )
    sliced = rows[page.offset : page.offset + page.page_size]
    return ok([_invoice_out(i) for i in sliced], meta=page_meta(page, len(rows)))


@admin_router.get("/invoices", response_model=ApiResponse[list[InvoiceOut]], responses=_ERR)
def admin_list_invoices(
    staff: FinanceDep,
    db: DbSession,
    page: PageDep,
    status: Annotated[InvoiceStatus | None, Query()] = None,
) -> ApiResponse[list[InvoiceOut]]:
    stmt = select(ProjectInvoice)
    if status is not None:
        stmt = stmt.where(ProjectInvoice.status == status)
    rows = db.execute(stmt.order_by(ProjectInvoice.submitted_at.desc())).scalars().all()
    sliced = rows[page.offset : page.offset + page.page_size]
    return ok([_invoice_out(i) for i in sliced], meta=page_meta(page, len(rows)))


@admin_router.post(
    "/invoices/{invoice_id}/status", response_model=ApiResponse[InvoiceOut], responses=_ERR
)
def admin_update_invoice_status(
    invoice_id: uuid.UUID, payload: InvoiceStatusIn, staff: FinanceDep, db: DbSession
) -> ApiResponse[InvoiceOut]:
    return ok(
        _invoice_out(service.update_invoice_status(db, staff, invoice_id, payload)),
        "Invoice status updated",
    )


# ================================================================ Compliance: KYC/KYB/Sanctions
@admin_router.put(
    "/compliance/organizations/{organization_id}/screening",
    response_model=ApiResponse[ComplianceScreeningOut],
    responses=_ERR,
)
def admin_upsert_compliance_screening(
    organization_id: uuid.UUID,
    payload: ComplianceScreeningIn,
    staff: ComplianceDep,
    db: DbSession,
) -> ApiResponse[ComplianceScreeningOut]:
    rec = service.upsert_compliance_screening(db, staff, organization_id, payload)
    return ok(
        ComplianceScreeningOut(
            id=rec.id,
            organization_id=rec.organization_id,
            kyc_status=rec.kyc_status,
            kyb_status=rec.kyb_status,
            sanctions_status=rec.sanctions_status,
            screening_notes=rec.screening_notes,
            screened_at=rec.screened_at,
        ),
        "Compliance screening updated",
    )


@admin_router.get(
    "/compliance/organizations/{organization_id}/screening",
    response_model=ApiResponse[ComplianceScreeningOut],
    responses=_ERR,
)
def admin_get_compliance_screening(
    organization_id: uuid.UUID, staff: ComplianceDep, db: DbSession
) -> ApiResponse[ComplianceScreeningOut]:
    rec = db.execute(
        select(PartnerComplianceScreening).where(
            PartnerComplianceScreening.organization_id == organization_id
        )
    ).scalar_one_or_none()
    if rec is None:
        raise NotFoundError("Compliance screening record not found")
    return ok(
        ComplianceScreeningOut(
            id=rec.id,
            organization_id=rec.organization_id,
            kyc_status=rec.kyc_status,
            kyb_status=rec.kyb_status,
            sanctions_status=rec.sanctions_status,
            screening_notes=rec.screening_notes,
            screened_at=rec.screened_at,
        )
    )
