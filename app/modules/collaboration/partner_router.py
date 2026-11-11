"""Partner side: shared projects, org-wide inbox, discussions / meetings / follow-ups.

The organisation always comes from the session (PartnerDep); no id from the client selects it.
Records that are not shared (or belong to another organisation) answer 404.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.pagination import PageDep, page_meta
from app.common.responses import ApiResponse, ErrorResponse, ok
from app.common.utilities import utcnow
from app.core.exceptions import AppError, NotFoundError
from app.database.dependencies import DbSession
from app.modules.auth.dependencies import PartnerContext, PartnerDep
from app.modules.auth.models import User
from app.modules.collaboration import service
from app.modules.collaboration.constants import (
    KIND_ACTIONS,
    PROJECT_LABELS,
    CollabAction,
    CollabKind,
    CollabStatus,
    MessageDirection,
    ProjectResponseKind,
    ProjectStatus,
)
from app.modules.collaboration.models import (
    CollabItem,
    CollabResponse,
    PartnerMessage,
    PartnerMessageAttachment,
    PartnerMessageRead,
    PartnerProject,
    ProjectDocumentLink,
    ProjectMilestone,
    ProjectResponse,
)
from app.modules.collaboration.schemas import (
    CollabDetail,
    CollabRespondIn,
    CollabResponseOut,
    CollabRow,
    LinkedDocument,
    MessageAttachmentOut,
    MilestoneOut,
    PartnerInboxDetail,
    PartnerInboxRow,
    PartnerMessageIn,
    PartnerProjectDetail,
    PartnerProjectRow,
    ProjectActionIn,
    ProjectContact,
    ProjectResponseOut,
    SubmitInformationIn,
)
from app.modules.enquiries.activity import log_activity
from app.modules.enquiries.constants import ActorType
from app.modules.partner_documents.models import PartnerDocument

_ERR: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}
projects = APIRouter(prefix="/partner/projects", tags=["partner-projects"])
inbox = APIRouter(prefix="/partner/messages", tags=["partner-messages"])


# ============================================================== projects
def _project(
    db: Session, ctx: PartnerContext, project_id: uuid.UUID, lock: bool = False
) -> PartnerProject:
    stmt = select(PartnerProject).where(
        PartnerProject.id == project_id,
        PartnerProject.organization_id == ctx.organization_id,
        PartnerProject.shared_at.is_not(None),
    )
    p = db.execute(stmt.with_for_update() if lock else stmt).scalar_one_or_none()
    if p is None:
        raise NotFoundError("Project not found")
    return p


def project_row(p: PartnerProject) -> dict[str, Any]:
    return {
        "id": p.id,
        "reference": p.reference,
        "title": p.title,
        "category": p.category,
        "status": p.status,
        "status_label": PROJECT_LABELS[p.status],
        "shared_at": p.shared_at,
        "updated_at": p.updated_at,
    }


def project_detail(db: Session, p: PartnerProject) -> dict[str, Any]:
    """Shared by the partner and staff views; nothing here is staff-only."""
    milestones = db.execute(
        select(ProjectMilestone)
        .where(ProjectMilestone.project_id == p.id)
        .order_by(ProjectMilestone.position, ProjectMilestone.created_at)
    ).scalars()
    responses = db.execute(
        select(ProjectResponse, User)
        .join(User, User.id == ProjectResponse.user_id)
        .where(ProjectResponse.project_id == p.id)
        .order_by(ProjectResponse.created_at)
    ).all()
    docs = db.execute(
        select(PartnerDocument.id, PartnerDocument.category)
        .join(ProjectDocumentLink, ProjectDocumentLink.document_id == PartnerDocument.id)
        .where(ProjectDocumentLink.project_id == p.id)
    ).all()
    message_ids = list(
        db.execute(
            select(PartnerMessage.id).where(
                PartnerMessage.project_id == p.id, PartnerMessage.partner_visible.is_(True)
            )
        ).scalars()
    )
    return {
        **project_row(p),
        "summary": p.summary,
        "contact": ProjectContact(
            name=p.contact_name, email=p.contact_email, phone=p.contact_phone
        ),
        "milestones": [
            MilestoneOut(
                id=m.id,
                title=m.title,
                due_date=m.due_date,
                status=m.status,
                completed_at=m.completed_at,
            )
            for m in milestones
        ],
        "responses": [
            ProjectResponseOut(
                id=r.id,
                kind=r.kind,
                body=r.body,
                author=service.author_label(u),
                document_ids=list(r.document_ids or []),
                created_at=r.created_at,
            )
            for r, u in responses
        ],
        "documents": [LinkedDocument(id=i, category=c.value) for i, c in docs],
        "message_ids": message_ids,
        "acknowledged_at": p.acknowledged_at,
        "confirmed_at": p.confirmed_at,
    }


@projects.get(
    "",
    response_model=ApiResponse[list[PartnerProjectRow]],
    responses=_ERR,
    summary="Projects staff have shared with your organisation",
)
def list_projects(
    ctx: PartnerDep,
    db: DbSession,
    page: PageDep,
    status: Annotated[ProjectStatus | None, Query()] = None,
) -> ApiResponse[list[PartnerProjectRow]]:
    stmt = select(PartnerProject).where(
        PartnerProject.organization_id == ctx.organization_id,
        PartnerProject.shared_at.is_not(None),
    )
    if status:
        stmt = stmt.where(PartnerProject.status == status)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(PartnerProject.updated_at.desc(), PartnerProject.id)
        .limit(page.page_size)
        .offset(page.offset)
    ).scalars()
    return ok([PartnerProjectRow(**project_row(p)) for p in rows], meta=page_meta(page, total))


@projects.get(
    "/{project_id}",
    response_model=ApiResponse[PartnerProjectDetail],
    responses=_ERR,
    summary="One shared project with milestones, responses, linked documents and messages",
)
def get_project(
    project_id: uuid.UUID, ctx: PartnerDep, db: DbSession
) -> ApiResponse[PartnerProjectDetail]:
    return ok(PartnerProjectDetail(**project_detail(db, _project(db, ctx, project_id))))


def _act(
    db: Session,
    ctx: PartnerContext,
    project_id: uuid.UUID,
    kind: ProjectResponseKind,
    body: str | None,
    document_ids: list[uuid.UUID] | None = None,
) -> PartnerProject:
    p = _project(db, ctx, project_id, lock=True)
    if p.status in (ProjectStatus.COMPLETED, ProjectStatus.CANCELLED):
        raise AppError("This project is closed", status_code=409, code="PROJECT_CLOSED")
    docs = service.owned_documents(db, ctx.organization_id, document_ids or [])
    needs_text = kind is ProjectResponseKind.RESPOND and not body
    if needs_text or (kind is ProjectResponseKind.SUBMIT_INFORMATION and not (body or docs)):
        raise AppError("Provide text or documents", status_code=422, code="BODY_REQUIRED")
    now = utcnow()
    if kind is ProjectResponseKind.ACKNOWLEDGE:
        if p.acknowledged_at is None:
            p.acknowledged_at = now
        if p.status in (ProjectStatus.PLANNING, ProjectStatus.AWAITING_PARTNER):
            p.status = ProjectStatus.ACKNOWLEDGED
    elif kind is ProjectResponseKind.CONFIRM:
        if p.confirmed_at is not None:
            raise AppError("Already confirmed", status_code=409, code="ALREADY_CONFIRMED")
        p.confirmed_at = now
        p.acknowledged_at = p.acknowledged_at or now
        if p.status in (
            ProjectStatus.PLANNING,
            ProjectStatus.AWAITING_PARTNER,
            ProjectStatus.ACKNOWLEDGED,
        ):
            p.status = ProjectStatus.CONFIRMED
    for doc_id in docs:
        exists = db.execute(
            select(ProjectDocumentLink.id).where(
                ProjectDocumentLink.project_id == p.id, ProjectDocumentLink.document_id == doc_id
            )
        ).first()
        if exists is None:
            db.add(
                ProjectDocumentLink(
                    project_id=p.id, document_id=doc_id, linked_by=ctx.user.id, created_at=now
                )
            )
    db.add(
        ProjectResponse(
            project_id=p.id,
            kind=kind,
            body=body,
            user_id=ctx.user.id,
            document_ids=docs or None,
            created_at=now,
        )
    )
    log_activity(
        db,
        "project",
        p.id,
        f"project.partner_{kind.value}",
        {"documents": len(docs)},
        ActorType.PARTNER,
        actor_user_id=ctx.user.id,
        organization_id=ctx.organization_id,
    )
    db.commit()
    db.refresh(p)
    return p


@projects.post(
    "/{project_id}/acknowledge",
    response_model=ApiResponse[PartnerProjectDetail],
    responses=_ERR,
    summary="Acknowledge receipt of a shared project",
)
def acknowledge(
    project_id: uuid.UUID, payload: ProjectActionIn, ctx: PartnerDep, db: DbSession
) -> ApiResponse[PartnerProjectDetail]:
    p = _act(db, ctx, project_id, ProjectResponseKind.ACKNOWLEDGE, payload.body)
    return ok(PartnerProjectDetail(**project_detail(db, p)), "Acknowledged")


@projects.post(
    "/{project_id}/confirm",
    response_model=ApiResponse[PartnerProjectDetail],
    responses=_ERR,
    summary="Confirm participation (409 ALREADY_CONFIRMED when repeated)",
)
def confirm(
    project_id: uuid.UUID, payload: ProjectActionIn, ctx: PartnerDep, db: DbSession
) -> ApiResponse[PartnerProjectDetail]:
    p = _act(db, ctx, project_id, ProjectResponseKind.CONFIRM, payload.body)
    return ok(PartnerProjectDetail(**project_detail(db, p)), "Confirmed")


@projects.post(
    "/{project_id}/respond",
    response_model=ApiResponse[PartnerProjectDetail],
    responses=_ERR,
    summary="Send a written response on a project",
)
def respond(
    project_id: uuid.UUID, payload: ProjectActionIn, ctx: PartnerDep, db: DbSession
) -> ApiResponse[PartnerProjectDetail]:
    p = _act(db, ctx, project_id, ProjectResponseKind.RESPOND, payload.body)
    return ok(PartnerProjectDetail(**project_detail(db, p)), "Response recorded")


@projects.post(
    "/{project_id}/submit-information",
    response_model=ApiResponse[PartnerProjectDetail],
    responses=_ERR,
    summary="Submit information and/or existing documents of your organisation",
)
def submit_information(
    project_id: uuid.UUID, payload: SubmitInformationIn, ctx: PartnerDep, db: DbSession
) -> ApiResponse[PartnerProjectDetail]:
    p = _act(
        db,
        ctx,
        project_id,
        ProjectResponseKind.SUBMIT_INFORMATION,
        payload.body,
        payload.document_ids,
    )
    return ok(PartnerProjectDetail(**project_detail(db, p)), "Information submitted")


# ================================================================== inbox
def _inbox_stmt(ctx: PartnerContext):  # type: ignore[no-untyped-def]
    return select(PartnerMessage).where(
        PartnerMessage.organization_id == ctx.organization_id,
        PartnerMessage.partner_visible.is_(True),
    )


def _read_ids(db: Session, ctx: PartnerContext, ids: list[uuid.UUID]) -> set[uuid.UUID]:
    if not ids:
        return set()
    return set(
        db.execute(
            select(PartnerMessageRead.message_id).where(
                PartnerMessageRead.user_id == ctx.user.id,
                PartnerMessageRead.message_id.in_(ids),
            )
        ).scalars()
    )


def _attachments(
    db: Session, message_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[MessageAttachmentOut]]:
    out: dict[uuid.UUID, list[MessageAttachmentOut]] = {}
    if not message_ids:
        return out
    for mid, did, cat in db.execute(
        select(PartnerMessageAttachment.message_id, PartnerDocument.id, PartnerDocument.category)
        .join(PartnerDocument, PartnerDocument.id == PartnerMessageAttachment.document_id)
        .where(PartnerMessageAttachment.message_id.in_(message_ids))
    ):
        out.setdefault(mid, []).append(MessageAttachmentOut(document_id=did, category=cat.value))
    return out


def _inbox_row(
    m: PartnerMessage, read: set[uuid.UUID], att: dict[uuid.UUID, list[Any]]
) -> dict[str, Any]:
    return {
        "id": m.id,
        "direction": m.direction.value,
        "subject": m.subject,
        "sender_label": m.sender_label,
        "project_id": m.project_id,
        # messages the partner sent themselves never count as unread
        "is_read": m.direction is MessageDirection.INBOUND or m.id in read,
        "has_attachments": bool(att.get(m.id)),
        "created_at": m.created_at,
    }


@inbox.get(
    "",
    response_model=ApiResponse[list[PartnerInboxRow]],
    responses=_ERR,
    summary="Organisation-wide inbox (sent and received), with read state",
)
def list_inbox(
    ctx: PartnerDep,
    db: DbSession,
    page: PageDep,
    unread: Annotated[bool, Query()] = False,
    direction: Annotated[MessageDirection | None, Query()] = None,
    project_id: Annotated[uuid.UUID | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=100, description="subject")] = None,
) -> ApiResponse[list[PartnerInboxRow]]:
    stmt = _inbox_stmt(ctx)
    if direction:
        stmt = stmt.where(PartnerMessage.direction == direction)
    if project_id:
        stmt = stmt.where(PartnerMessage.project_id == project_id)
    if q:
        like = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        stmt = stmt.where(PartnerMessage.subject.ilike(like))
    if unread:
        stmt = stmt.where(
            PartnerMessage.direction == MessageDirection.OUTBOUND,
            ~PartnerMessage.id.in_(
                select(PartnerMessageRead.message_id).where(
                    PartnerMessageRead.user_id == ctx.user.id
                )
            ),
        )
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    unread_total = db.execute(
        select(func.count()).select_from(
            _inbox_stmt(ctx)
            .where(
                PartnerMessage.direction == MessageDirection.OUTBOUND,
                ~PartnerMessage.id.in_(
                    select(PartnerMessageRead.message_id).where(
                        PartnerMessageRead.user_id == ctx.user.id
                    )
                ),
            )
            .subquery()
        )
    ).scalar_one()
    msgs = list(
        db.execute(
            stmt.order_by(PartnerMessage.created_at.desc(), PartnerMessage.id)
            .limit(page.page_size)
            .offset(page.offset)
        ).scalars()
    )
    ids = [m.id for m in msgs]
    read, att = _read_ids(db, ctx, ids), _attachments(db, ids)
    meta = page_meta(page, total) | {"unread": unread_total}
    return ok([PartnerInboxRow(**_inbox_row(m, read, att)) for m in msgs], meta=meta)


def _message(db: Session, ctx: PartnerContext, message_id: uuid.UUID) -> PartnerMessage:
    m = db.execute(_inbox_stmt(ctx).where(PartnerMessage.id == message_id)).scalar_one_or_none()
    if m is None:
        raise NotFoundError("Message not found")
    return m  # type: ignore[no-any-return]


@inbox.get(
    "/{message_id}",
    response_model=ApiResponse[PartnerInboxDetail],
    responses=_ERR,
    summary="One message with attachments (does not change read state)",
)
def get_message(
    message_id: uuid.UUID, ctx: PartnerDep, db: DbSession
) -> ApiResponse[PartnerInboxDetail]:
    m = _message(db, ctx, message_id)
    read, att = _read_ids(db, ctx, [m.id]), _attachments(db, [m.id])
    return ok(
        PartnerInboxDetail(**_inbox_row(m, read, att), body=m.body, attachments=att.get(m.id, []))
    )


@inbox.post(
    "/{message_id}/read",
    response_model=ApiResponse[None],
    responses=_ERR,
    summary="Mark a message read for you",
)
def mark_read(message_id: uuid.UUID, ctx: PartnerDep, db: DbSession) -> ApiResponse[None]:
    m = _message(db, ctx, message_id)
    if not _read_ids(db, ctx, [m.id]):
        db.add(PartnerMessageRead(message_id=m.id, user_id=ctx.user.id, read_at=utcnow()))
        db.commit()
    return ok(None)


@inbox.post(
    "/{message_id}/unread",
    response_model=ApiResponse[None],
    responses=_ERR,
    summary="Mark a message unread for you",
)
def mark_unread(message_id: uuid.UUID, ctx: PartnerDep, db: DbSession) -> ApiResponse[None]:
    m = _message(db, ctx, message_id)
    row = db.get(PartnerMessageRead, (m.id, ctx.user.id))
    if row is not None:
        db.delete(row)
        db.commit()
    return ok(None)


@inbox.post(
    "",
    status_code=201,
    response_model=ApiResponse[PartnerInboxDetail],
    responses=_ERR,
    summary="Send a message to the CoralSwift team (optionally about a shared project)",
)
def send_message(
    payload: PartnerMessageIn, ctx: PartnerDep, db: DbSession
) -> ApiResponse[PartnerInboxDetail]:
    if payload.project_id is not None:
        _project(db, ctx, payload.project_id)
    docs = service.owned_documents(db, ctx.organization_id, payload.document_ids)
    m = PartnerMessage(
        organization_id=ctx.organization_id,
        project_id=payload.project_id,
        direction=MessageDirection.INBOUND,
        subject=payload.subject,
        body=payload.body,
        sender_user_id=ctx.user.id,
        sender_label=ctx.user.full_name,
        partner_visible=True,
        created_at=utcnow(),
    )
    db.add(m)
    db.flush()
    for d in docs:
        db.add(PartnerMessageAttachment(message_id=m.id, document_id=d))
    log_activity(
        db,
        "partner_message",
        m.id,
        "message.partner_sent",
        {"attachments": len(docs)},
        ActorType.PARTNER,
        actor_user_id=ctx.user.id,
        organization_id=ctx.organization_id,
    )
    db.commit()
    att = _attachments(db, [m.id])
    return ok(
        PartnerInboxDetail(**_inbox_row(m, set(), att), body=m.body, attachments=att.get(m.id, [])),
        "Message sent",
    )


# ====================================================== collaboration items
def _collab_row(c: CollabItem) -> dict[str, Any]:
    return {
        "id": c.id,
        "reference": c.reference,
        "kind": c.kind,
        "title": c.title,
        "status": c.status,
        "project_id": c.project_id,
        "due_at": c.due_at,
        "starts_at": c.starts_at,
        "ends_at": c.ends_at,
        "location": c.location,
        "shared_at": c.shared_at,
        "updated_at": c.updated_at,
    }


def collab_responses(db: Session, item_id: uuid.UUID) -> list[CollabResponseOut]:
    rows = db.execute(
        select(CollabResponse, User)
        .join(User, User.id == CollabResponse.user_id)
        .where(CollabResponse.item_id == item_id)
        .order_by(CollabResponse.created_at)
    ).all()
    return [
        CollabResponseOut(
            id=r.id,
            action=r.action,
            body=r.body,
            author=service.author_label(u),
            from_partner=u.user_type.value == "partner",
            created_at=r.created_at,
        )
        for r, u in rows
    ]


def _open_actions(c: CollabItem) -> list[CollabAction]:
    if c.status in (CollabStatus.COMPLETED, CollabStatus.CANCELLED):
        return []
    return sorted(KIND_ACTIONS[c.kind], key=lambda a: a.value)


def _collab_router(kind: CollabKind, prefix: str) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=["partner-collaboration"])

    def _get(
        db: Session, ctx: PartnerContext, item_id: uuid.UUID, lock: bool = False
    ) -> CollabItem:
        stmt = select(CollabItem).where(
            CollabItem.id == item_id,
            CollabItem.kind == kind,
            CollabItem.organization_id == ctx.organization_id,
            CollabItem.shared_at.is_not(None),
        )
        c = db.execute(stmt.with_for_update() if lock else stmt).scalar_one_or_none()
        if c is None:
            raise NotFoundError("Item not found")
        return c

    @router.get(
        "",
        name=f"list_{kind.value}",
        response_model=ApiResponse[list[CollabRow]],
        responses=_ERR,
        summary=f"{kind.value.replace('_', ' ').title()}s shared with your organisation",
    )
    def list_items(
        ctx: PartnerDep,
        db: DbSession,
        page: PageDep,
        status: Annotated[CollabStatus | None, Query()] = None,
    ) -> ApiResponse[list[CollabRow]]:
        stmt = select(CollabItem).where(
            CollabItem.kind == kind,
            CollabItem.organization_id == ctx.organization_id,
            CollabItem.shared_at.is_not(None),
        )
        if status:
            stmt = stmt.where(CollabItem.status == status)
        total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        rows = db.execute(
            stmt.order_by(CollabItem.updated_at.desc(), CollabItem.id)
            .limit(page.page_size)
            .offset(page.offset)
        ).scalars()
        return ok([CollabRow(**_collab_row(c)) for c in rows], meta=page_meta(page, total))

    @router.get(
        "/{item_id}",
        name=f"get_{kind.value}",
        response_model=ApiResponse[CollabDetail],
        responses=_ERR,
        summary="Detail with the full conversation and the actions you may take",
    )
    def get_item(item_id: uuid.UUID, ctx: PartnerDep, db: DbSession) -> ApiResponse[CollabDetail]:
        c = _get(db, ctx, item_id)
        return ok(
            CollabDetail(
                **_collab_row(c),
                body=c.body,
                responses=collab_responses(db, c.id),
                allowed_actions=_open_actions(c),
            )
        )

    @router.post(
        "/{item_id}/respond",
        name=f"respond_{kind.value}",
        response_model=ApiResponse[CollabDetail],
        responses=_ERR,
        summary="Reply, accept/decline (meetings) or complete (follow-ups)",
    )
    def respond_item(
        item_id: uuid.UUID, payload: CollabRespondIn, ctx: PartnerDep, db: DbSession
    ) -> ApiResponse[CollabDetail]:
        c = _get(db, ctx, item_id, lock=True)
        if c.status in (CollabStatus.COMPLETED, CollabStatus.CANCELLED):
            raise AppError("This item is closed", status_code=409, code="ITEM_CLOSED")
        if payload.action not in KIND_ACTIONS[kind]:
            raise AppError(
                f"Action {payload.action.value} is not available here",
                status_code=422,
                code="ACTION_NOT_ALLOWED",
            )
        if payload.action is CollabAction.REPLY and not payload.body:
            raise AppError("A reply needs text", status_code=422, code="BODY_REQUIRED")
        db.add(
            CollabResponse(
                item_id=c.id,
                user_id=ctx.user.id,
                action=payload.action,
                body=payload.body,
                created_at=utcnow(),
            )
        )
        c.status = (
            CollabStatus.COMPLETED
            if payload.action is CollabAction.COMPLETE
            else CollabStatus.RESPONDED
        )
        log_activity(
            db,
            "collab_item",
            c.id,
            f"collab.partner_{payload.action.value}",
            {"kind": kind.value},
            ActorType.PARTNER,
            actor_user_id=ctx.user.id,
            organization_id=ctx.organization_id,
        )
        db.commit()
        db.refresh(c)
        return ok(
            CollabDetail(
                **_collab_row(c),
                body=c.body,
                responses=collab_responses(db, c.id),
                allowed_actions=_open_actions(c),
            ),
            "Response recorded",
        )

    return router


discussions = _collab_router(CollabKind.DISCUSSION, "/partner/discussions")
meetings = _collab_router(CollabKind.MEETING, "/partner/meetings")
follow_ups = _collab_router(CollabKind.FOLLOW_UP, "/partner/follow-ups")
