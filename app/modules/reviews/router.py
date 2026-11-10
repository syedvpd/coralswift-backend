"""Reviewer / staff endpoints needed for partner application processing (not the Phase 3 admin)."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, model_validator
from sqlalchemy import String, cast, func, or_, select

from app.common.pagination import PageDep, page_meta
from app.common.responses import ApiResponse, ErrorResponse, ok
from app.common.validation import Short
from app.core.config import Settings, get_settings
from app.core.exceptions import AppError, NotFoundError
from app.core.protection import rate_limit
from app.database.dependencies import DbSession
from app.modules.admin import lookups
from app.modules.applications import service as app_service
from app.modules.applications import transitions
from app.modules.applications.constants import PortalStatus
from app.modules.applications.models import (
    ApplicationStatusHistory,
    PortalApplication,
)
from app.modules.applications.transitions import Actor
from app.modules.auth import service as auth_service
from app.modules.auth.dependencies import ReviewerDep, SuperAdminDep
from app.modules.enquiries.constants import ActorType
from app.modules.enquiries.models import Activity, Enquiry
from app.modules.messaging import service as msg_service
from app.modules.notifications.service import dispatch_notifications
from app.modules.organizations import service as org_service
from app.modules.organizations.models import PartnerOrganization
from app.modules.organizations.schemas import OrganizationOut
from app.modules.partner_documents import service as doc_service
from app.modules.partner_documents.schemas import (
    DocumentOut,
    VersionOut,
    document_out,
    version_out,
)
from app.modules.partners.constants import EngagementPathway
from app.modules.reviews import service
from app.modules.reviews.schemas import (
    AssignIn,
    AuditItem,
    DocumentReviewIn,
    EligibilityIn,
    EligibilityOut,
    HistoryItem,
    InformationRequestIn,
    NoteIn,
    NoteOut,
    ReviewerApplicationOut,
    ReviewerMessageOut,
    TransitionIn,
)

router = APIRouter(prefix="/reviewer", tags=["reviewer"])
SettingsDep = Annotated[Settings, Depends(get_settings)]
_ERR: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


def _dispatch(request: Request, settings: Settings, background: BackgroundTasks) -> None:
    background.add_task(
        dispatch_notifications,
        request.app.state.sessionmaker,
        request.app.state.email_sender,
        settings,
    )


def _app_out(
    app: PortalApplication,
    org_name: str,
    *,
    reviewer_name: str | None = None,
    contacts: list[dict[str, Any]] | None = None,
) -> ReviewerApplicationOut:
    return ReviewerApplicationOut(
        id=app.id,
        reference=app.reference,
        organization_id=app.organization_id,
        organization_name=org_name,
        status=app.status,
        pathway=app.pathway.value,
        assigned_reviewer_id=app.assigned_reviewer_id,
        submission_count=app.submission_count,
        submitted_at=app.submitted_at,
        updated_at=app.updated_at,
        decided_at=app.decided_at,
        assigned_reviewer_name=reviewer_name,
        primary_contact=_primary(contacts),
        allowed_next=transitions.allowed_targets(transitions.Actor.REVIEWER, app.status),
    )


def _primary(contacts: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    if not contacts:
        return None
    first = contacts[0]
    return {k: first.get(k) for k in ("name", "email", "phone", "role") if k in first} or None


# ------------------------------------------------------------- invitations
class InvitationIn(BaseModel):
    """Invite a partner user. Either target an existing organization or create a new one."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    full_name: Short
    organization_id: uuid.UUID | None = None
    new_organization_legal_name: Short | None = None
    source_enquiry_reference: str | None = None

    @model_validator(mode="after")
    def _one_target(self) -> "InvitationIn":
        if (self.organization_id is None) == (self.new_organization_legal_name is None):
            raise ValueError(
                "provide exactly one of organization_id or new_organization_legal_name"
            )
        return self


class InvitationOut(BaseModel):
    organization_id: uuid.UUID


@router.post(
    "/invitations",
    status_code=201,
    response_model=ApiResponse[InvitationOut],
    dependencies=[Depends(rate_limit("invite"))],
    responses=_ERR,
    summary="Invite a partner user (super administrator only)",
)
def invite(
    payload: InvitationIn,
    request: Request,
    staff: SuperAdminDep,
    db: DbSession,
    settings: SettingsDep,
    background: BackgroundTasks,
) -> ApiResponse[InvitationOut]:
    """Partner accounts are invitation-only (the PRD does not define self-registration)."""
    if payload.organization_id is not None:
        org = org_service.get_organization_or_none(db, payload.organization_id)
        if org is None:
            raise NotFoundError("Organization not found")
    else:
        source_id = None
        if payload.source_enquiry_reference:
            enquiry = db.execute(
                select(Enquiry).where(Enquiry.reference_number == payload.source_enquiry_reference)
            ).scalar_one_or_none()
            if enquiry is None:
                raise AppError("Unknown enquiry reference", status_code=422, code="UNKNOWN_ENQUIRY")
            source_id = enquiry.id
        if payload.new_organization_legal_name is None:
            raise AppError("organization is required", status_code=422, code="VALIDATION_ERROR")
        org = org_service.create_organization(
            db,
            creator=staff.user,
            legal_name=payload.new_organization_legal_name,
            source_enquiry_id=source_id,
        )
    auth_service.invite_partner_user(
        db,
        settings,
        inviter=staff.user,
        email=payload.email,
        full_name=payload.full_name,
        organization=org,
    )
    db.commit()
    _dispatch(request, settings, background)
    return ok(InvitationOut(organization_id=org.id), "Invitation issued")


# ------------------------------------------------------------ applications
@router.get(
    "/applications",
    response_model=ApiResponse[list[ReviewerApplicationOut]],
    responses=_ERR,
    summary="Applications you may review (assigned to you; super administrators see all submitted)",
)
def list_applications(
    staff: ReviewerDep,
    db: DbSession,
    page: PageDep,
    status: Annotated[PortalStatus | None, Query()] = None,
    unassigned: Annotated[bool, Query()] = False,
    assigned_reviewer_id: Annotated[uuid.UUID | None, Query()] = None,
    q: Annotated[
        str | None, Query(max_length=100, description="reference, organisation, contact name/email")
    ] = None,
    pathway: Annotated[EngagementPathway | None, Query()] = None,
    submitted_from: Annotated[datetime | None, Query()] = None,
    submitted_to: Annotated[datetime | None, Query()] = None,
    updated_from: Annotated[datetime | None, Query()] = None,
    updated_to: Annotated[datetime | None, Query()] = None,
    sort: Annotated[
        Literal["submitted_at", "-submitted_at", "updated_at", "-updated_at", "reference"], Query()
    ] = "submitted_at",
) -> ApiResponse[list[ReviewerApplicationOut]]:
    base = service.reviewable_query(staff).join(
        PartnerOrganization, PartnerOrganization.id == PortalApplication.organization_id
    )
    if status is not None:
        base = base.where(PortalApplication.status == status)
    if unassigned:
        base = base.where(PortalApplication.assigned_reviewer_id.is_(None))
    if assigned_reviewer_id:
        base = base.where(PortalApplication.assigned_reviewer_id == assigned_reviewer_id)
    if pathway:
        base = base.where(PortalApplication.pathway == pathway)
    if submitted_from:
        base = base.where(PortalApplication.submitted_at >= submitted_from)
    if submitted_to:
        base = base.where(PortalApplication.submitted_at < submitted_to)
    if updated_from:
        base = base.where(PortalApplication.updated_at >= updated_from)
    if updated_to:
        base = base.where(PortalApplication.updated_at < updated_to)
    if q:
        like = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        base = base.where(
            or_(
                PortalApplication.reference.ilike(like, escape="\\"),
                PartnerOrganization.legal_name.ilike(like, escape="\\"),
                cast(PartnerOrganization.authorized_contacts, String).ilike(like, escape="\\"),
            )
        )
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    orders: dict[str, tuple[Any, ...]] = {
        "submitted_at": (
            PortalApplication.submitted_at.asc().nulls_last(),
            PortalApplication.id.asc(),
        ),
        "-submitted_at": (
            PortalApplication.submitted_at.desc().nulls_last(),
            PortalApplication.id.desc(),
        ),
        "updated_at": (PortalApplication.updated_at.asc(), PortalApplication.id.asc()),
        "-updated_at": (PortalApplication.updated_at.desc(), PortalApplication.id.desc()),
        "reference": (PortalApplication.reference.asc(),),
    }
    rows = db.execute(
        base.add_columns(PartnerOrganization.legal_name, PartnerOrganization.authorized_contacts)
        .order_by(*orders[sort])
        .limit(page.page_size)
        .offset(page.offset)
    ).all()
    names = lookups.user_names(db, (a.assigned_reviewer_id for a, _, _ in rows))
    return ok(
        [
            _app_out(
                a,
                name,
                reviewer_name=names.get(a.assigned_reviewer_id) if a.assigned_reviewer_id else None,
                contacts=contacts,
            )
            for a, name, contacts in rows
        ],
        meta=page_meta(page, total),
    )


@router.get(
    "/transitions",
    response_model=ApiResponse[list[dict[str, Any]]],
    responses=_ERR,
    summary="Every status change a reviewer may make, with its requirements",
)
def reviewer_transitions(staff: ReviewerDep) -> ApiResponse[list[dict[str, Any]]]:
    return ok(transitions.transition_table(transitions.Actor.REVIEWER))


class ReviewDetailOut(BaseModel):
    application: ReviewerApplicationOut
    organization: OrganizationOut
    documents: list[DocumentOut]
    eligibility_verifications: list[EligibilityOut]
    status_history: list[HistoryItem]
    open_information_requests: int


@router.get(
    "/applications/{application_id}",
    response_model=ApiResponse[ReviewDetailOut],
    responses=_ERR,
    summary="Review details: profile, documents, eligibility records, history",
)
def detail(
    application_id: uuid.UUID, staff: ReviewerDep, db: DbSession
) -> ApiResponse[ReviewDetailOut]:
    app = service.get_reviewable(db, staff, application_id)
    org = org_service.get_organization(db, app.organization_id)
    history = list(
        db.execute(
            select(ApplicationStatusHistory)
            .where(ApplicationStatusHistory.application_id == app.id)
            .order_by(ApplicationStatusHistory.created_at)
        ).scalars()
    )
    names = lookups.user_names(db, [h.actor_user_id for h in history] + [app.assigned_reviewer_id])
    items = [HistoryItem.model_validate(h, from_attributes=True) for h in history]
    for item in items:
        item.actor_name = names.get(item.actor_user_id)
    return ok(
        ReviewDetailOut(
            application=_app_out(
                app,
                org.legal_name,
                reviewer_name=names.get(app.assigned_reviewer_id)
                if app.assigned_reviewer_id
                else None,
                contacts=org.authorized_contacts,
            ),
            organization=OrganizationOut.model_validate(org),
            documents=[document_out(d, v) for d, v in doc_service.list_documents(db, org.id)],
            eligibility_verifications=[
                EligibilityOut.model_validate(e, from_attributes=True)
                for e in service.list_eligibility(db, app.id)
            ],
            status_history=items,
            open_information_requests=app_service.open_request_count(db, app.id),
        )
    )


@router.post(
    "/applications/{application_id}/assign",
    response_model=ApiResponse[ReviewerApplicationOut],
    responses=_ERR,
)
def assign(
    application_id: uuid.UUID,
    payload: AssignIn,
    request: Request,
    staff: SuperAdminDep,
    db: DbSession,
    settings: SettingsDep,
    background: BackgroundTasks,
) -> ApiResponse[ReviewerApplicationOut]:
    app = service.get_reviewable(db, staff, application_id, lock=True)
    service.assign(db, staff, app, payload.reviewer_id)
    db.commit()
    _dispatch(request, settings, background)
    org = org_service.get_organization(db, app.organization_id)
    names = lookups.user_names(db, [app.assigned_reviewer_id])
    return ok(
        _app_out(
            app,
            org.legal_name,
            reviewer_name=names.get(app.assigned_reviewer_id) if app.assigned_reviewer_id else None,
            contacts=org.authorized_contacts,
        ),
        "Reviewer updated",
    )


@router.post(
    "/applications/{application_id}/transition",
    response_model=ApiResponse[ReviewerApplicationOut],
    responses=_ERR,
    summary="Move the application to another permitted stage",
)
def transition(
    application_id: uuid.UUID,
    payload: TransitionIn,
    request: Request,
    staff: ReviewerDep,
    db: DbSession,
    settings: SettingsDep,
    background: BackgroundTasks,
) -> ApiResponse[ReviewerApplicationOut]:
    app = service.get_reviewable(db, staff, application_id, lock=True)
    app_service.transition(
        db,
        settings,
        app=app,
        target=payload.to_status,
        actor=Actor.REVIEWER,
        user=staff.user,
        reason=payload.reason,
        partner_note=payload.partner_note,
    )
    db.commit()
    _dispatch(request, settings, background)
    org = org_service.get_organization(db, app.organization_id)
    return ok(_app_out(app, org.legal_name), "Status updated")


@router.post(
    "/applications/{application_id}/information-requests",
    status_code=201,
    response_model=ApiResponse[ReviewerMessageOut],
    responses=_ERR,
    summary="Request additional information (moves the application to information_requested)",
)
def request_information(
    application_id: uuid.UUID,
    payload: InformationRequestIn,
    request: Request,
    staff: ReviewerDep,
    db: DbSession,
    settings: SettingsDep,
    background: BackgroundTasks,
) -> ApiResponse[ReviewerMessageOut]:
    app = service.get_reviewable(db, staff, application_id, lock=True)
    message = msg_service.create_information_request(
        db, settings, staff, app, payload.body, payload.requested_categories
    )
    db.commit()
    _dispatch(request, settings, background)
    return ok(_message_out(message), "Information requested")


def _message_out(m) -> ReviewerMessageOut:  # type: ignore[no-untyped-def]
    return ReviewerMessageOut(
        id=m.id,
        kind=m.kind.value,
        status=m.status.value if m.status else None,
        author_user_id=m.author_user_id,
        body=m.body,
        requested_categories=m.requested_categories,
        in_reply_to=m.in_reply_to_id,
        created_at=m.created_at,
    )


@router.get(
    "/applications/{application_id}/messages",
    response_model=ApiResponse[list[ReviewerMessageOut]],
    responses=_ERR,
)
def messages(
    application_id: uuid.UUID, staff: ReviewerDep, db: DbSession
) -> ApiResponse[list[ReviewerMessageOut]]:
    app = service.get_reviewable(db, staff, application_id)
    return ok([_message_out(m) for m in msg_service.list_messages(db, app.id)])


@router.post(
    "/applications/{application_id}/notes",
    status_code=201,
    response_model=ApiResponse[NoteOut],
    responses=_ERR,
    summary="Add an internal note (never visible to partners)",
)
def add_note(
    application_id: uuid.UUID, payload: NoteIn, staff: ReviewerDep, db: DbSession
) -> ApiResponse[NoteOut]:
    app = service.get_reviewable(db, staff, application_id, lock=True)
    note = service.add_note(db, staff, app, payload.body)
    db.commit()
    return ok(
        NoteOut(id=note.id, author_id=note.author_id, body=note.body, created_at=note.created_at)
    )


@router.get(
    "/applications/{application_id}/notes",
    response_model=ApiResponse[list[NoteOut]],
    responses=_ERR,
)
def list_notes(
    application_id: uuid.UUID, staff: ReviewerDep, db: DbSession
) -> ApiResponse[list[NoteOut]]:
    app = service.get_reviewable(db, staff, application_id)
    notes = service.list_notes(db, app.id)
    names = lookups.user_names(db, (n.author_id for n in notes))
    return ok(
        [
            NoteOut(
                id=n.id,
                author_id=n.author_id,
                body=n.body,
                created_at=n.created_at,
                author_name=names.get(n.author_id),
            )
            for n in notes
        ]
    )


@router.post(
    "/applications/{application_id}/eligibility-verifications",
    status_code=201,
    response_model=ApiResponse[EligibilityOut],
    responses=_ERR,
    summary="Record a human eligibility verification (no automatic approval or rejection)",
)
def add_eligibility(
    application_id: uuid.UUID, payload: EligibilityIn, staff: ReviewerDep, db: DbSession
) -> ApiResponse[EligibilityOut]:
    app = service.get_reviewable(db, staff, application_id, lock=True)
    row = service.add_eligibility(db, staff, app, payload)
    db.commit()
    return ok(EligibilityOut.model_validate(row, from_attributes=True), "Verification recorded")


@router.get(
    "/applications/{application_id}/eligibility-verifications",
    response_model=ApiResponse[list[EligibilityOut]],
    responses=_ERR,
)
def list_eligibility(
    application_id: uuid.UUID, staff: ReviewerDep, db: DbSession
) -> ApiResponse[list[EligibilityOut]]:
    app = service.get_reviewable(db, staff, application_id)
    return ok(
        [
            EligibilityOut.model_validate(e, from_attributes=True)
            for e in service.list_eligibility(db, app.id)
        ]
    )


@router.post(
    "/applications/{application_id}/documents/{document_id}/review",
    response_model=ApiResponse[VersionOut],
    responses=_ERR,
    summary="Record a document review outcome (comment is visible to the partner)",
)
def review_document(
    application_id: uuid.UUID,
    document_id: uuid.UUID,
    payload: DocumentReviewIn,
    staff: ReviewerDep,
    db: DbSession,
) -> ApiResponse[VersionOut]:
    app = service.get_reviewable(db, staff, application_id)
    doc = service.get_application_document(db, app, document_id)
    version = service.review_document(db, staff, app, doc, payload)
    db.commit()
    return ok(version_out(version), "Document reviewed")


@router.get(
    "/applications/{application_id}/documents/{document_id}/download",
    responses={**_ERR, 200: {"content": {"application/octet-stream": {}}}},
    summary="Download a document of an application you review (audited)",
)
def download_document(
    application_id: uuid.UUID,
    document_id: uuid.UUID,
    request: Request,
    staff: ReviewerDep,
    db: DbSession,
    version: Annotated[int | None, Query(ge=1)] = None,
) -> Response:
    app = service.get_reviewable(db, staff, application_id)
    doc = service.get_application_document(db, app, document_id)
    data, ver = doc_service.read_version(
        db,
        request.app.state.storage,
        doc,
        version,
        actor_type=ActorType.REVIEWER,
        actor_user_id=staff.user.id,
    )
    return Response(
        content=data,
        media_type=ver.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="document-{ver.version_no}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get(
    "/applications/{application_id}/history",
    response_model=ApiResponse[list[AuditItem]],
    responses=_ERR,
    summary="Audit trail for the application (reviewer-only)",
)
def audit_history(
    application_id: uuid.UUID, staff: ReviewerDep, db: DbSession
) -> ApiResponse[list[AuditItem]]:
    app = service.get_reviewable(db, staff, application_id)
    rows = db.execute(
        select(Activity)
        .where(Activity.record_type == "portal_application", Activity.record_id == app.id)
        .order_by(Activity.created_at)
    ).scalars()
    return ok(
        [
            AuditItem(
                action=a.action,
                actor_type=a.actor_type.value,
                actor_user_id=a.actor_user_id,
                request_id=a.request_id,
                meta=a.meta,
                created_at=a.created_at,
            )
            for a in rows
        ]
    )
