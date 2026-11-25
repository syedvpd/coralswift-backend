"""Business logic for Steps 8-10 & Compliance Screening."""

import hashlib
import secrets
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.utilities import utcnow
from app.core.exceptions import AppError, NotFoundError
from app.modules.auth.dependencies import PartnerContext, StaffContext
from app.modules.collaboration.constants import MilestoneStatus, ProjectStatus
from app.modules.collaboration.models import PartnerProject, ProjectMilestone
from app.modules.delivery_governance.constants import (
    ContractStatus,
    DeliverableStatus,
    InvoiceStatus,
)
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
    ContractCreateIn,
    ContractSignIn,
    DeliverableReviewIn,
    DeliverableSubmitIn,
    InvoiceStatusIn,
    InvoiceSubmitIn,
    ProjectClosureIn,
)
from app.modules.enquiries.activity import log_activity
from app.modules.enquiries.constants import ActorType
from app.modules.organizations.models import PartnerOrganization


def _ref(prefix: str) -> str:
    return f"{prefix}-{utcnow().year}-{secrets.token_hex(4).upper()}"


def _sig_hash(contract_id: uuid.UUID, user_id: uuid.UUID, signer: str, ts: str) -> str:
    payload = f"{contract_id}:{user_id}:{signer}:{ts}".encode()
    return hashlib.sha256(payload).hexdigest()


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


# ------------------------------------------------------------------ Step 8: Contracts
def create_contract(db: Session, staff: StaffContext, data: ContractCreateIn) -> ProjectContract:
    if db.get(PartnerOrganization, data.organization_id) is None:
        raise NotFoundError("Organization not found")
    contract = ProjectContract(
        reference=_ref("CTR"),
        opportunity_id=data.opportunity_id,
        proposal_id=data.proposal_id,
        project_id=data.project_id,
        organization_id=data.organization_id,
        title=data.title,
        scope_summary=data.scope_summary,
        contract_value=data.contract_value,
        currency=data.currency,
        payment_terms=data.payment_terms,
        effective_date=data.effective_date,
        expiry_date=data.expiry_date,
        document_id=data.document_id,
        status=ContractStatus.DRAFT,
        created_by=staff.user.id,
    )
    db.add(contract)
    db.flush()
    _audit_staff(
        db, staff, "contract", contract.id, "contract.created", org_id=data.organization_id
    )
    return contract


def send_contract_for_signature(
    db: Session, staff: StaffContext, contract_id: uuid.UUID
) -> ProjectContract:
    contract = db.execute(
        select(ProjectContract).where(ProjectContract.id == contract_id).with_for_update()
    ).scalar_one_or_none()
    if contract is None:
        raise NotFoundError("Contract not found")
    if contract.status is not ContractStatus.DRAFT:
        raise AppError(
            "Only draft contracts can be sent for signature", status_code=409, code="INVALID_STATE"
        )
    contract.status = ContractStatus.SENT_FOR_SIGNATURE
    _audit_staff(
        db,
        staff,
        "contract",
        contract.id,
        "contract.sent_for_signature",
        org_id=contract.organization_id,
    )
    return contract


def partner_sign_contract(
    db: Session, partner: PartnerContext, contract_id: uuid.UUID, data: ContractSignIn
) -> ProjectContract:
    contract = db.execute(
        select(ProjectContract)
        .where(
            ProjectContract.id == contract_id,
            ProjectContract.organization_id == partner.organization_id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if contract is None:
        raise NotFoundError("Contract not found")
    if contract.status is not ContractStatus.SENT_FOR_SIGNATURE:
        raise AppError(
            "Contract is not awaiting partner signature", status_code=409, code="INVALID_STATE"
        )
    if not data.accepted_terms:
        raise AppError("Terms must be accepted to sign", status_code=422, code="TERMS_NOT_ACCEPTED")
    now = utcnow()
    contract.partner_signed_by = partner.user.id
    contract.partner_signed_at = now
    contract.partner_signature_hash = _sig_hash(
        contract.id, partner.user.id, data.signer_name, now.isoformat()
    )
    if data.document_id is not None:
        contract.document_id = data.document_id
    contract.status = ContractStatus.PARTNER_SIGNED
    _audit_partner(db, partner, "contract", contract.id, "contract.partner_signed")
    return contract


def countersign_contract(
    db: Session, staff: StaffContext, contract_id: uuid.UUID, data: ContractSignIn
) -> ProjectContract:
    contract = db.execute(
        select(ProjectContract).where(ProjectContract.id == contract_id).with_for_update()
    ).scalar_one_or_none()
    if contract is None:
        raise NotFoundError("Contract not found")
    if contract.status is not ContractStatus.PARTNER_SIGNED:
        raise AppError(
            "Partner must sign before countersigning", status_code=409, code="INVALID_STATE"
        )
    if not data.accepted_terms:
        raise AppError(
            "Terms must be accepted to countersign", status_code=422, code="TERMS_NOT_ACCEPTED"
        )
    now = utcnow()
    contract.staff_countersigned_by = staff.user.id
    contract.staff_countersigned_at = now
    contract.staff_signature_hash = _sig_hash(
        contract.id, staff.user.id, data.signer_name, now.isoformat()
    )
    if data.document_id is not None:
        contract.document_id = data.document_id
    contract.status = ContractStatus.ACTIVE
    _audit_staff(
        db,
        staff,
        "contract",
        contract.id,
        "contract.countersigned",
        org_id=contract.organization_id,
    )
    return contract


# ------------------------------------------------------------------ Step 9: Deliverables & Comments
def _partner_milestone(
    db: Session, partner: PartnerContext, milestone_id: uuid.UUID
) -> tuple[ProjectMilestone, PartnerProject]:
    row = db.execute(
        select(ProjectMilestone, PartnerProject)
        .join(PartnerProject, PartnerProject.id == ProjectMilestone.project_id)
        .where(
            ProjectMilestone.id == milestone_id,
            PartnerProject.organization_id == partner.organization_id,
            PartnerProject.shared_at.is_not(None),
        )
    ).first()
    if row is None:
        raise NotFoundError("Milestone not found")
    return row[0], row[1]


def submit_deliverable(
    db: Session, partner: PartnerContext, milestone_id: uuid.UUID, data: DeliverableSubmitIn
) -> MilestoneDeliverable:
    ms, proj = _partner_milestone(db, partner, milestone_id)
    deliv = MilestoneDeliverable(
        milestone_id=ms.id,
        organization_id=partner.organization_id,
        submitted_by=partner.user.id,
        title=data.title,
        description=data.description,
        acceptance_criteria=data.acceptance_criteria,
        document_ids=data.document_ids or None,
        status=DeliverableStatus.SUBMITTED,
    )
    db.add(deliv)
    db.flush()
    _audit_partner(
        db, partner, "deliverable", deliv.id, "deliverable.submitted", {"milestone_id": str(ms.id)}
    )
    return deliv


def review_deliverable(
    db: Session, staff: StaffContext, deliverable_id: uuid.UUID, data: DeliverableReviewIn
) -> MilestoneDeliverable:
    deliv = db.execute(
        select(MilestoneDeliverable)
        .where(MilestoneDeliverable.id == deliverable_id)
        .with_for_update()
    ).scalar_one_or_none()
    if deliv is None:
        raise NotFoundError("Deliverable not found")
    if data.status not in (
        DeliverableStatus.ACCEPTED,
        DeliverableStatus.REVISION_REQUESTED,
        DeliverableStatus.REJECTED,
        DeliverableStatus.UNDER_REVIEW,
    ):
        raise AppError("Invalid review status", status_code=422, code="INVALID_STATUS")
    now = utcnow()
    deliv.status = data.status
    deliv.reviewed_by = staff.user.id
    deliv.reviewed_at = now
    deliv.review_notes = data.review_notes
    if data.status is DeliverableStatus.ACCEPTED:
        ms = db.get(ProjectMilestone, deliv.milestone_id)
        if ms is not None:
            ms.status = MilestoneStatus.DONE
            ms.completed_at = now
    _audit_staff(
        db,
        staff,
        "deliverable",
        deliv.id,
        "deliverable.reviewed",
        {"status": data.status.value},
        org_id=deliv.organization_id,
    )
    return deliv


def add_milestone_comment(
    db: Session,
    milestone_id: uuid.UUID,
    user_id: uuid.UUID,
    author_type: str,
    body: str,
    org_id: uuid.UUID,
) -> MilestoneComment:
    comment = MilestoneComment(
        milestone_id=milestone_id,
        user_id=user_id,
        author_type=author_type,
        body=body,
        created_at=utcnow(),
    )
    db.add(comment)
    db.flush()
    log_activity(
        db,
        "milestone_comment",
        comment.id,
        "milestone.comment_added",
        {"milestone_id": str(milestone_id)},
        ActorType.PARTNER if author_type == "partner" else ActorType.STAFF,
        actor_user_id=user_id,
        organization_id=org_id,
    )
    return comment


# ------------------------------------------------------------------ Step 10: Closure & Invoices
def close_project(
    db: Session, staff: StaffContext, project_id: uuid.UUID, data: ProjectClosureIn
) -> ProjectClosure:
    proj = db.execute(
        select(PartnerProject).where(PartnerProject.id == project_id).with_for_update()
    ).scalar_one_or_none()
    if proj is None:
        raise NotFoundError("Project not found")
    existing = db.execute(
        select(ProjectClosure).where(ProjectClosure.project_id == proj.id)
    ).scalar_one_or_none()
    if existing is not None:
        raise AppError("Project is already closed", status_code=409, code="ALREADY_CLOSED")
    now = utcnow()
    closure = ProjectClosure(
        project_id=proj.id,
        organization_id=proj.organization_id,
        summary=data.summary,
        outcomes=data.outcomes,
        lessons_learned=data.lessons_learned,
        partner_rating=data.partner_rating,
        delivery_quality_score=data.delivery_quality_score,
        timeliness_score=data.timeliness_score,
        communication_score=data.communication_score,
        closed_by=staff.user.id,
        closed_at=now,
    )
    db.add(closure)
    proj.status = ProjectStatus.COMPLETED
    db.flush()
    _audit_staff(
        db,
        staff,
        "project_closure",
        closure.id,
        "project.closed",
        {"partner_rating": data.partner_rating},
        org_id=proj.organization_id,
    )
    return closure


def submit_invoice(db: Session, partner: PartnerContext, data: InvoiceSubmitIn) -> ProjectInvoice:
    proj = db.execute(
        select(PartnerProject).where(
            PartnerProject.id == data.project_id,
            PartnerProject.organization_id == partner.organization_id,
            PartnerProject.shared_at.is_not(None),
        )
    ).scalar_one_or_none()
    if proj is None:
        raise NotFoundError("Project not found")
    inv = ProjectInvoice(
        invoice_number=_ref("INV"),
        project_id=proj.id,
        contract_id=data.contract_id,
        milestone_id=data.milestone_id,
        organization_id=partner.organization_id,
        amount=data.amount,
        tax_amount=data.tax_amount,
        total_amount=data.amount + data.tax_amount,
        currency=data.currency,
        description=data.description,
        due_date=data.due_date,
        document_id=data.document_id,
        status=InvoiceStatus.SUBMITTED,
        submitted_by=partner.user.id,
        submitted_at=utcnow(),
    )
    db.add(inv)
    db.flush()
    _audit_partner(db, partner, "invoice", inv.id, "invoice.submitted")
    return inv


def update_invoice_status(
    db: Session, staff: StaffContext, invoice_id: uuid.UUID, data: InvoiceStatusIn
) -> ProjectInvoice:
    inv = db.execute(
        select(ProjectInvoice).where(ProjectInvoice.id == invoice_id).with_for_update()
    ).scalar_one_or_none()
    if inv is None:
        raise NotFoundError("Invoice not found")
    now = utcnow()
    inv.status = data.status
    if data.payment_reference is not None:
        inv.payment_reference = data.payment_reference
    if data.finance_notes is not None:
        inv.finance_notes = data.finance_notes
    if data.status is InvoiceStatus.APPROVED:
        inv.approved_by = staff.user.id
        inv.approved_at = now
    elif data.status is InvoiceStatus.PAID:
        if inv.approved_at is None:
            inv.approved_by = staff.user.id
            inv.approved_at = now
        inv.paid_at = now
    _audit_staff(
        db,
        staff,
        "invoice",
        inv.id,
        "invoice.status_changed",
        {"status": data.status.value},
        org_id=inv.organization_id,
    )
    return inv


# ------------------------------------------------------------------ Compliance Screening
def upsert_compliance_screening(
    db: Session, staff: StaffContext, organization_id: uuid.UUID, data: ComplianceScreeningIn
) -> PartnerComplianceScreening:
    if db.get(PartnerOrganization, organization_id) is None:
        raise NotFoundError("Organization not found")
    rec = db.execute(
        select(PartnerComplianceScreening)
        .where(PartnerComplianceScreening.organization_id == organization_id)
        .with_for_update()
    ).scalar_one_or_none()
    now = utcnow()
    if rec is None:
        rec = PartnerComplianceScreening(
            organization_id=organization_id,
            kyc_status=data.kyc_status,
            kyb_status=data.kyb_status,
            sanctions_status=data.sanctions_status,
            screening_notes=data.screening_notes,
            screened_by=staff.user.id,
            screened_at=now,
        )
        db.add(rec)
        db.flush()
    else:
        rec.kyc_status = data.kyc_status
        rec.kyb_status = data.kyb_status
        rec.sanctions_status = data.sanctions_status
        rec.screening_notes = data.screening_notes
        rec.screened_by = staff.user.id
        rec.screened_at = now
    _audit_staff(
        db,
        staff,
        "compliance_screening",
        rec.id,
        "compliance.screened",
        {
            "kyc": data.kyc_status.value,
            "kyb": data.kyb_status.value,
            "sanctions": data.sanctions_status.value,
        },
        org_id=organization_id,
    )
    return rec
