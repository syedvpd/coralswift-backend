"""Additional-document requests (PRD s.13): a reviewer asks an organisation for a document with a
deadline; uploading a document against the request fulfils it. Partners see only their own
organisation's requests, and never the staff member's identity."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.pagination import PageDep, page_meta
from app.common.responses import ApiResponse, ErrorResponse, ok
from app.common.utilities import utcnow
from app.common.validation import Long
from app.core.config import Settings, get_settings
from app.core.exceptions import AppError, NotFoundError
from app.database.dependencies import DbSession
from app.modules.admin import lookups
from app.modules.applications.constants import TERMINAL
from app.modules.applications.models import PortalApplication
from app.modules.applications.service import partner_users
from app.modules.auth.dependencies import PartnerContext, PartnerDep, ReviewerDep
from app.modules.enquiries.activity import log_activity
from app.modules.enquiries.constants import ActorType
from app.modules.notifications.constants import NotificationType, TemplateKey
from app.modules.notifications.service import dispatch_notifications, queue_notification
from app.modules.partner_documents.constants import PartnerDocCategory
from app.modules.partner_documents.models import DocumentRequest
from app.modules.reviews import service as review_service

staff_router = APIRouter(prefix="/reviewer", tags=["document-requests"])
partner_router = APIRouter(prefix="/partner/document-requests", tags=["document-requests"])
SettingsDep = Annotated[Settings, Depends(get_settings)]
_ERR: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}
Status = Literal["open", "fulfilled", "cancelled"]


class DocumentRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: PartnerDocCategory
    note: Long
    due_at: datetime | None = None


class PartnerDocumentRequestOut(BaseModel):
    id: uuid.UUID
    application_reference: str | None
    category: PartnerDocCategory
    note: str
    due_at: datetime | None
    status: Status
    is_overdue: bool
    fulfilled_document_id: uuid.UUID | None
    fulfilled_at: datetime | None
    created_at: datetime


class StaffDocumentRequestOut(PartnerDocumentRequestOut):
    application_id: uuid.UUID | None
    created_by_name: str | None


def _overdue(r: DocumentRequest) -> bool:
    return r.status == "open" and r.due_at is not None and r.due_at < utcnow()


def _partner_out(r: DocumentRequest, reference: str | None) -> PartnerDocumentRequestOut:
    return PartnerDocumentRequestOut(
        id=r.id,
        application_reference=reference,
        category=PartnerDocCategory(r.category),
        note=r.note,
        due_at=r.due_at,
        status=r.status,
        is_overdue=_overdue(r),
        fulfilled_document_id=r.fulfilled_document_id,
        fulfilled_at=r.fulfilled_at,
        created_at=r.created_at,
    )


def _references(db: Session, rows: list[DocumentRequest]) -> dict[uuid.UUID, str]:
    ids = {r.application_id for r in rows if r.application_id}
    if not ids:
        return {}
    return {
        i: ref
        for i, ref in db.execute(
            select(PortalApplication.id, PortalApplication.reference).where(
                PortalApplication.id.in_(ids)
            )
        )
    }


# ----------------------------------------------------------------------- service
def create_request(
    db: Session, staff_id: uuid.UUID, app: PortalApplication, data: DocumentRequestIn
) -> DocumentRequest:
    if app.status in TERMINAL:
        raise AppError("The application is closed", status_code=409, code="APPLICATION_CLOSED")
    if data.due_at is not None and data.due_at <= utcnow():
        raise AppError("The deadline must be in the future", status_code=422, code="DUE_IN_PAST")
    duplicate = db.execute(
        select(DocumentRequest.id).where(
            DocumentRequest.organization_id == app.organization_id,
            DocumentRequest.category == data.category.value,
            DocumentRequest.status == "open",
        )
    ).first()
    if duplicate:
        raise AppError(
            "An open request for this category already exists",
            status_code=409,
            code="DUPLICATE_OPEN_REQUEST",
        )
    row = DocumentRequest(
        organization_id=app.organization_id,
        application_id=app.id,
        category=data.category.value,
        note=data.note,
        due_at=data.due_at,
        created_by=staff_id,
    )
    db.add(row)
    db.flush()
    for user in partner_users(db, app.organization_id):
        queue_notification(
            db,
            recipient=user.email,
            kind=NotificationType.APPLICATION,
            template=TemplateKey.INFORMATION_REQUESTED,
            context={"name": user.full_name, "reference": app.reference},
            dedupe_key=f"docreq:{row.id}:{user.id}",
        )
    log_activity(
        db,
        "document_request",
        row.id,
        "document_request.created",
        {"category": row.category, "due": data.due_at is not None},
        ActorType.REVIEWER,
        actor_user_id=staff_id,
        organization_id=app.organization_id,
    )
    db.commit()
    return row


def open_request_for_upload(
    db: Session, ctx: PartnerContext, request_id: uuid.UUID, category: PartnerDocCategory
) -> DocumentRequest:
    """Checked before the file is stored, so a bad request id never leaves an orphan upload."""
    row = db.execute(
        select(DocumentRequest)
        .where(
            DocumentRequest.id == request_id, DocumentRequest.organization_id == ctx.organization_id
        )
        .with_for_update()
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("Document request not found")  # foreign ids look the same
    if row.status != "open":
        raise AppError("This request is no longer open", status_code=409, code="REQUEST_CLOSED")
    if row.category != category.value:
        raise AppError(
            "The document category does not match the request",
            status_code=422,
            code="CATEGORY_MISMATCH",
        )
    return row


def mark_fulfilled(
    db: Session, row: DocumentRequest, document_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    row.status = "fulfilled"
    row.fulfilled_document_id = document_id
    row.fulfilled_at = utcnow()
    log_activity(
        db,
        "document_request",
        row.id,
        "document_request.fulfilled",
        {},
        ActorType.PARTNER,
        actor_user_id=user_id,
        organization_id=row.organization_id,
    )
    db.commit()


# ------------------------------------------------------------------- staff routes
def _staff_out(db: Session, rows: list[DocumentRequest]) -> list[StaffDocumentRequestOut]:
    refs = _references(db, rows)
    names = lookups.user_names(db, (r.created_by for r in rows))
    return [
        StaffDocumentRequestOut(
            **_partner_out(
                r, refs.get(r.application_id) if r.application_id else None
            ).model_dump(),
            application_id=r.application_id,
            created_by_name=names.get(r.created_by),
        )
        for r in rows
    ]


@staff_router.post(
    "/applications/{application_id}/document-requests",
    status_code=201,
    response_model=ApiResponse[StaffDocumentRequestOut],
    responses=_ERR,
    summary="Ask the partner for an additional document, with an optional deadline",
)
def create(
    application_id: uuid.UUID,
    payload: DocumentRequestIn,
    request: Request,
    staff: ReviewerDep,
    db: DbSession,
    settings: SettingsDep,
    background: BackgroundTasks,
) -> ApiResponse[StaffDocumentRequestOut]:
    app = review_service.get_reviewable(db, staff, application_id, lock=True)
    row = create_request(db, staff.user.id, app, payload)
    background.add_task(
        dispatch_notifications,
        request.app.state.sessionmaker,
        request.app.state.email_sender,
        settings,
    )
    return ok(_staff_out(db, [row])[0], "Request sent")


@staff_router.get(
    "/applications/{application_id}/document-requests",
    response_model=ApiResponse[list[StaffDocumentRequestOut]],
    responses=_ERR,
    summary="Document requests of one application",
)
def list_for_application(
    application_id: uuid.UUID,
    staff: ReviewerDep,
    db: DbSession,
    page: PageDep,
    status: Annotated[Status | None, Query()] = None,
) -> ApiResponse[list[StaffDocumentRequestOut]]:
    app = review_service.get_reviewable(db, staff, application_id)
    stmt = select(DocumentRequest).where(DocumentRequest.application_id == app.id)
    if status:
        stmt = stmt.where(DocumentRequest.status == status)
    from sqlalchemy import func

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = list(
        db.execute(
            stmt.order_by(DocumentRequest.created_at.desc(), DocumentRequest.id.desc())
            .limit(page.page_size)
            .offset(page.offset)
        ).scalars()
    )
    return ok(_staff_out(db, rows), meta=page_meta(page, total))


@staff_router.post(
    "/document-requests/{request_id}/cancel",
    response_model=ApiResponse[StaffDocumentRequestOut],
    responses=_ERR,
    summary="Withdraw an open request",
)
def cancel(
    request_id: uuid.UUID, staff: ReviewerDep, db: DbSession
) -> ApiResponse[StaffDocumentRequestOut]:
    row = db.execute(
        select(DocumentRequest).where(DocumentRequest.id == request_id).with_for_update()
    ).scalar_one_or_none()
    if row is None or row.application_id is None:
        raise NotFoundError("Document request not found")
    review_service.get_reviewable(db, staff, row.application_id)  # same access as the application
    if row.status != "open":
        raise AppError(
            "Only open requests can be cancelled", status_code=409, code="REQUEST_CLOSED"
        )
    row.status = "cancelled"
    log_activity(
        db,
        "document_request",
        row.id,
        "document_request.cancelled",
        {},
        ActorType.REVIEWER,
        actor_user_id=staff.user.id,
        organization_id=row.organization_id,
    )
    db.commit()
    return ok(_staff_out(db, [row])[0], "Request withdrawn")


# ----------------------------------------------------------------- partner routes
@partner_router.get(
    "",
    response_model=ApiResponse[list[PartnerDocumentRequestOut]],
    responses=_ERR,
    summary="Document requests for your organisation (meta.open counts open ones)",
)
def my_requests(
    ctx: PartnerDep,
    db: DbSession,
    page: PageDep,
    status: Annotated[Status | None, Query()] = None,
) -> ApiResponse[list[PartnerDocumentRequestOut]]:
    from sqlalchemy import func

    base = select(DocumentRequest).where(DocumentRequest.organization_id == ctx.organization_id)
    open_count = db.execute(
        select(func.count()).select_from(base.where(DocumentRequest.status == "open").subquery())
    ).scalar_one()
    stmt = base.where(DocumentRequest.status == status) if status else base
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = list(
        db.execute(
            stmt.order_by(DocumentRequest.created_at.desc(), DocumentRequest.id.desc())
            .limit(page.page_size)
            .offset(page.offset)
        ).scalars()
    )
    refs = _references(db, rows)
    return ok(
        [_partner_out(r, refs.get(r.application_id) if r.application_id else None) for r in rows],
        meta={**page_meta(page, total), "open": open_count},
    )


@partner_router.get(
    "/{request_id}",
    response_model=ApiResponse[PartnerDocumentRequestOut],
    responses=_ERR,
    summary="One document request (other organisations' ids return 404)",
)
def my_request(
    request_id: uuid.UUID, ctx: PartnerDep, db: DbSession
) -> ApiResponse[PartnerDocumentRequestOut]:
    row = db.execute(
        select(DocumentRequest).where(
            DocumentRequest.id == request_id, DocumentRequest.organization_id == ctx.organization_id
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("Document request not found")
    refs = _references(db, [row])
    return ok(_partner_out(row, refs.get(row.application_id) if row.application_id else None))
