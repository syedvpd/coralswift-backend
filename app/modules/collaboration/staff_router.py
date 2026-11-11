"""Staff side (super administrator and partner reviewers within their assigned organisations)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.common.pagination import PageDep, page_meta
from app.common.responses import ApiResponse, ErrorResponse, ok
from app.common.utilities import utcnow
from app.core.exceptions import AppError, NotFoundError
from app.database.dependencies import DbSession
from app.modules.auth.dependencies import CollabReadDep, ReviewerDep, StaffContext
from app.modules.collaboration import service
from app.modules.collaboration.constants import (
    PROJECT_LABELS,
    CollabAction,
    CollabKind,
    CollabStatus,
    MessageDirection,
    MilestoneStatus,
    ProjectStatus,
)
from app.modules.collaboration.models import (
    CollabItem,
    CollabResponse,
    PartnerMessage,
    PartnerMessageAttachment,
    PartnerProject,
    ProjectDocumentLink,
    ProjectMilestone,
)
from app.modules.collaboration.partner_router import (
    _collab_row,
    collab_responses,
    project_detail,
)
from app.modules.collaboration.schemas import (
    CollabCreate,
    CollabUpdate,
    LinkDocumentIn,
    MilestoneIn,
    MilestoneOut,
    MilestoneUpdate,
    ProjectCreate,
    ProjectUpdate,
    StaffCollabDetail,
    StaffCollabRow,
    StaffInboxRow,
    StaffMessageIn,
    StaffProjectDetail,
    StaffProjectRow,
    StaffReplyIn,
)
from app.modules.enquiries.activity import log_activity
from app.modules.enquiries.constants import ActorType
from app.modules.organizations.models import PartnerOrganization

router = APIRouter(prefix="/reviewer", tags=["reviewer-collaboration"])
_ERR: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


def _audit(
    db: Session,
    staff: StaffContext,
    rtype: str,
    rid: uuid.UUID,
    action: str,
    org: uuid.UUID,
    meta: dict[str, Any] | None = None,
) -> None:
    log_activity(
        db,
        rtype,
        rid,
        action,
        meta,
        ActorType.STAFF,
        actor_user_id=staff.user.id,
        organization_id=org,
    )


def _like(q: str) -> str:
    return "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


# ================================================================ projects
def _proj(
    db: Session, staff: StaffContext, project_id: uuid.UUID, lock: bool = False
) -> PartnerProject:
    stmt = select(PartnerProject).where(
        PartnerProject.id == project_id, service.org_scope(staff, PartnerProject.organization_id)
    )
    p = db.execute(stmt.with_for_update() if lock else stmt).scalar_one_or_none()
    if p is None:
        raise NotFoundError("Project not found")
    return p


def _staff_project(db: Session, p: PartnerProject) -> StaffProjectDetail:
    org = db.get(PartnerOrganization, p.organization_id)
    detail = project_detail(db, p)
    return StaffProjectDetail(
        **detail,
        organization_id=p.organization_id,
        organization_name=org.legal_name if org else "",
        is_shared=p.shared_at is not None,
    )


@router.post(
    "/projects",
    status_code=201,
    response_model=ApiResponse[StaffProjectDetail],
    responses=_ERR,
    summary="Create a project for an organisation (not visible to the partner until shared)",
)
def create_project(
    payload: ProjectCreate, staff: ReviewerDep, db: DbSession
) -> ApiResponse[StaffProjectDetail]:
    org = service.require_org(db, staff, payload.organization_id)
    p = PartnerProject(
        reference=service.reference("PRJ"),
        organization_id=org.id,
        title=payload.title,
        category=payload.category,
        summary=payload.summary,
        contact_name=payload.contact_name,
        contact_email=payload.contact_email,
        contact_phone=payload.contact_phone,
        created_by=staff.user.id,
    )
    db.add(p)
    db.flush()
    for i, m in enumerate(payload.milestones):
        db.add(ProjectMilestone(project_id=p.id, title=m.title, due_date=m.due_date, position=i))
    _audit(db, staff, "project", p.id, "project.created", org.id)
    db.commit()
    db.refresh(p)
    return ok(_staff_project(db, p), "Project created")


@router.get(
    "/projects",
    response_model=ApiResponse[list[StaffProjectRow]],
    responses=_ERR,
    summary="Projects in the organisations you may work with",
)
def list_projects(
    staff: CollabReadDep,
    db: DbSession,
    page: PageDep,
    organization_id: Annotated[uuid.UUID | None, Query()] = None,
    status: Annotated[ProjectStatus | None, Query()] = None,
    shared: Annotated[bool | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=100, description="title or reference")] = None,
) -> ApiResponse[list[StaffProjectRow]]:
    stmt = (
        select(PartnerProject, PartnerOrganization.legal_name)
        .join(PartnerOrganization, PartnerOrganization.id == PartnerProject.organization_id)
        .where(service.org_scope(staff, PartnerProject.organization_id))
    )
    if organization_id:
        stmt = stmt.where(PartnerProject.organization_id == organization_id)
    if status:
        stmt = stmt.where(PartnerProject.status == status)
    if shared is not None:
        stmt = stmt.where(
            PartnerProject.shared_at.is_not(None) if shared else PartnerProject.shared_at.is_(None)
        )
    if q:
        stmt = stmt.where(
            or_(PartnerProject.title.ilike(_like(q)), PartnerProject.reference.ilike(_like(q)))
        )
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(PartnerProject.updated_at.desc(), PartnerProject.id)
        .limit(page.page_size)
        .offset(page.offset)
    ).all()
    return ok(
        [
            StaffProjectRow(
                id=p.id,
                reference=p.reference,
                title=p.title,
                category=p.category,
                status=p.status,
                status_label=PROJECT_LABELS[p.status],
                shared_at=p.shared_at,
                updated_at=p.updated_at,
                organization_id=p.organization_id,
                organization_name=name,
                is_shared=p.shared_at is not None,
            )
            for p, name in rows
        ],
        meta=page_meta(page, total),
    )


@router.get(
    "/projects/{project_id}",
    response_model=ApiResponse[StaffProjectDetail],
    responses=_ERR,
    summary="Project detail including partner responses (also before it is shared)",
)
def get_project(
    project_id: uuid.UUID, staff: CollabReadDep, db: DbSession
) -> ApiResponse[StaffProjectDetail]:
    return ok(_staff_project(db, _proj(db, staff, project_id)))


@router.patch(
    "/projects/{project_id}",
    response_model=ApiResponse[StaffProjectDetail],
    responses=_ERR,
    summary="Edit a project; omit = unchanged, null clears nullable fields",
)
def update_project(
    project_id: uuid.UUID, payload: ProjectUpdate, staff: ReviewerDep, db: DbSession
) -> ApiResponse[StaffProjectDetail]:
    p = _proj(db, staff, project_id, lock=True)
    changes = payload.model_dump(exclude_unset=True)
    for required in ("title", "status"):
        if required in changes and changes[required] is None:
            raise AppError(f"{required} cannot be cleared", status_code=422, code="REQUIRED_FIELD")
    for field, value in changes.items():
        setattr(p, field, value)
    _audit(
        db,
        staff,
        "project",
        p.id,
        "project.updated",
        p.organization_id,
        {"fields": sorted(changes)},
    )
    db.commit()
    db.refresh(p)
    return ok(_staff_project(db, p), "Project updated")


@router.post(
    "/projects/{project_id}/share",
    response_model=ApiResponse[StaffProjectDetail],
    responses=_ERR,
    summary="Make the project visible to the partner organisation",
)
def share_project(
    project_id: uuid.UUID, staff: ReviewerDep, db: DbSession
) -> ApiResponse[StaffProjectDetail]:
    p = _proj(db, staff, project_id, lock=True)
    if p.shared_at is None:
        p.shared_at, p.shared_by = utcnow(), staff.user.id
        if p.status is ProjectStatus.PLANNING:
            p.status = ProjectStatus.AWAITING_PARTNER
        _audit(db, staff, "project", p.id, "project.shared", p.organization_id)
        db.commit()
        db.refresh(p)
    return ok(_staff_project(db, p), "Shared with partner")


@router.post(
    "/projects/{project_id}/unshare",
    response_model=ApiResponse[StaffProjectDetail],
    responses=_ERR,
    summary="Hide the project from the partner again (history is kept)",
)
def unshare_project(
    project_id: uuid.UUID, staff: ReviewerDep, db: DbSession
) -> ApiResponse[StaffProjectDetail]:
    p = _proj(db, staff, project_id, lock=True)
    if p.shared_at is not None:
        p.shared_at, p.shared_by = None, None
        _audit(db, staff, "project", p.id, "project.unshared", p.organization_id)
        db.commit()
        db.refresh(p)
    return ok(_staff_project(db, p), "Hidden from partner")


@router.post(
    "/projects/{project_id}/milestones",
    status_code=201,
    response_model=ApiResponse[MilestoneOut],
    responses=_ERR,
    summary="Add a milestone",
)
def add_milestone(
    project_id: uuid.UUID, payload: MilestoneIn, staff: ReviewerDep, db: DbSession
) -> ApiResponse[MilestoneOut]:
    p = _proj(db, staff, project_id, lock=True)
    position = db.execute(
        select(func.count())
        .select_from(ProjectMilestone)
        .where(ProjectMilestone.project_id == p.id)
    ).scalar_one()
    m = ProjectMilestone(
        project_id=p.id, title=payload.title, due_date=payload.due_date, position=position
    )
    db.add(m)
    db.flush()
    _audit(db, staff, "project", p.id, "project.milestone_added", p.organization_id)
    db.commit()
    return ok(
        MilestoneOut(
            id=m.id,
            title=m.title,
            due_date=m.due_date,
            status=m.status,
            completed_at=m.completed_at,
        )
    )


@router.patch(
    "/projects/{project_id}/milestones/{milestone_id}",
    response_model=ApiResponse[MilestoneOut],
    responses=_ERR,
    summary="Edit a milestone; status done records the completion time",
)
def update_milestone(
    project_id: uuid.UUID,
    milestone_id: uuid.UUID,
    payload: MilestoneUpdate,
    staff: ReviewerDep,
    db: DbSession,
) -> ApiResponse[MilestoneOut]:
    p = _proj(db, staff, project_id, lock=True)
    m = db.execute(
        select(ProjectMilestone).where(
            ProjectMilestone.id == milestone_id, ProjectMilestone.project_id == p.id
        )
    ).scalar_one_or_none()
    if m is None:
        raise NotFoundError("Milestone not found")
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("title", "x") is None or changes.get("status", "x") is None:
        raise AppError("Field cannot be cleared", status_code=422, code="REQUIRED_FIELD")
    for field, value in changes.items():
        setattr(m, field, value)
    if "status" in changes:
        m.completed_at = utcnow() if m.status is MilestoneStatus.DONE else None
    _audit(db, staff, "project", p.id, "project.milestone_updated", p.organization_id)
    db.commit()
    return ok(
        MilestoneOut(
            id=m.id,
            title=m.title,
            due_date=m.due_date,
            status=m.status,
            completed_at=m.completed_at,
        )
    )


@router.post(
    "/projects/{project_id}/documents",
    status_code=201,
    response_model=ApiResponse[StaffProjectDetail],
    responses=_ERR,
    summary="Link an existing document of the organisation to the project",
)
def link_document(
    project_id: uuid.UUID, payload: LinkDocumentIn, staff: ReviewerDep, db: DbSession
) -> ApiResponse[StaffProjectDetail]:
    p = _proj(db, staff, project_id, lock=True)
    service.owned_documents(db, p.organization_id, [payload.document_id])
    exists = db.execute(
        select(ProjectDocumentLink.id).where(
            ProjectDocumentLink.project_id == p.id,
            ProjectDocumentLink.document_id == payload.document_id,
        )
    ).first()
    if exists is None:
        db.add(
            ProjectDocumentLink(
                project_id=p.id,
                document_id=payload.document_id,
                linked_by=staff.user.id,
                created_at=utcnow(),
            )
        )
        _audit(db, staff, "project", p.id, "project.document_linked", p.organization_id)
        db.commit()
    return ok(_staff_project(db, p))


# ================================================================ messages
@router.post(
    "/partner-messages",
    status_code=201,
    response_model=ApiResponse[StaffInboxRow],
    responses=_ERR,
    summary="Send a message to a partner organisation (partner_visible=false: internal note)",
)
def send_partner_message(
    payload: StaffMessageIn, staff: ReviewerDep, db: DbSession
) -> ApiResponse[StaffInboxRow]:
    org = service.require_org(db, staff, payload.organization_id)
    if payload.project_id is not None:
        owned = db.execute(
            select(PartnerProject.id).where(
                PartnerProject.id == payload.project_id, PartnerProject.organization_id == org.id
            )
        ).first()
        if owned is None:
            raise NotFoundError("Project not found")
    docs = service.owned_documents(db, org.id, payload.document_ids)
    m = PartnerMessage(
        organization_id=org.id,
        project_id=payload.project_id,
        direction=MessageDirection.OUTBOUND,
        subject=payload.subject,
        body=payload.body,
        sender_user_id=staff.user.id,
        sender_label=service.STAFF_LABEL,
        partner_visible=payload.partner_visible,
        created_at=utcnow(),
    )
    db.add(m)
    db.flush()
    for d in docs:
        db.add(PartnerMessageAttachment(message_id=m.id, document_id=d))
    _audit(
        db,
        staff,
        "partner_message",
        m.id,
        "message.staff_sent" if payload.partner_visible else "message.staff_note",
        org.id,
        {"attachments": len(docs)},
    )
    db.commit()
    return ok(_staff_msg(m, org.legal_name, bool(docs)), "Message recorded")


def _staff_msg(m: PartnerMessage, org_name: str, has_att: bool) -> StaffInboxRow:
    return StaffInboxRow(
        id=m.id,
        direction=m.direction.value,
        subject=m.subject,
        sender_label=m.sender_label,
        project_id=m.project_id,
        is_read=True,
        has_attachments=has_att,
        created_at=m.created_at,
        organization_id=m.organization_id,
        organization_name=org_name,
        partner_visible=m.partner_visible,
        body=m.body,
    )


@router.get(
    "/partner-messages",
    response_model=ApiResponse[list[StaffInboxRow]],
    responses=_ERR,
    summary="Organisation inbox as staff see it (partner messages and what was sent)",
)
def list_partner_messages(
    staff: CollabReadDep,
    db: DbSession,
    page: PageDep,
    organization_id: Annotated[uuid.UUID | None, Query()] = None,
    direction: Annotated[MessageDirection | None, Query()] = None,
    partner_visible: Annotated[bool | None, Query()] = None,
) -> ApiResponse[list[StaffInboxRow]]:
    stmt = (
        select(PartnerMessage, PartnerOrganization.legal_name)
        .join(PartnerOrganization, PartnerOrganization.id == PartnerMessage.organization_id)
        .where(service.org_scope(staff, PartnerMessage.organization_id))
    )
    if organization_id:
        stmt = stmt.where(PartnerMessage.organization_id == organization_id)
    if direction:
        stmt = stmt.where(PartnerMessage.direction == direction)
    if partner_visible is not None:
        stmt = stmt.where(PartnerMessage.partner_visible.is_(partner_visible))
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(PartnerMessage.created_at.desc(), PartnerMessage.id)
        .limit(page.page_size)
        .offset(page.offset)
    ).all()
    att = set(
        db.execute(
            select(PartnerMessageAttachment.message_id).where(
                PartnerMessageAttachment.message_id.in_([m.id for m, _ in rows])
            )
        ).scalars()
    )
    return ok([_staff_msg(m, n, m.id in att) for m, n in rows], meta=page_meta(page, total))


# ===================================================== collaboration items
_PREFIX = {
    CollabKind.DISCUSSION: "DSC",
    CollabKind.MEETING: "MTG",
    CollabKind.FOLLOW_UP: "FUP",
}


def _item(db: Session, staff: StaffContext, item_id: uuid.UUID, lock: bool = False) -> CollabItem:
    stmt = select(CollabItem).where(
        CollabItem.id == item_id, service.org_scope(staff, CollabItem.organization_id)
    )
    c = db.execute(stmt.with_for_update() if lock else stmt).scalar_one_or_none()
    if c is None:
        raise NotFoundError("Item not found")
    return c


def _staff_item(db: Session, c: CollabItem) -> StaffCollabDetail:
    org = db.get(PartnerOrganization, c.organization_id)
    return StaffCollabDetail(
        **_collab_row(c),
        body=c.body,
        responses=collab_responses(db, c.id),
        allowed_actions=[],
        organization_id=c.organization_id,
        organization_name=org.legal_name if org else "",
        is_shared=c.shared_at is not None,
    )


@router.post(
    "/collaboration",
    status_code=201,
    response_model=ApiResponse[StaffCollabDetail],
    responses=_ERR,
    summary="Create a discussion, meeting or follow-up (not visible to the partner until shared)",
)
def create_item(
    payload: CollabCreate, staff: ReviewerDep, db: DbSession
) -> ApiResponse[StaffCollabDetail]:
    org = service.require_org(db, staff, payload.organization_id)
    if payload.kind is CollabKind.MEETING and payload.starts_at is None:
        raise AppError("A meeting needs a start time", status_code=422, code="STARTS_AT_REQUIRED")
    if payload.starts_at and payload.ends_at and payload.ends_at <= payload.starts_at:
        raise AppError("End must be after start", status_code=422, code="INVALID_RANGE")
    if payload.project_id is not None:
        owned = db.execute(
            select(PartnerProject.id).where(
                PartnerProject.id == payload.project_id, PartnerProject.organization_id == org.id
            )
        ).first()
        if owned is None:
            raise NotFoundError("Project not found")
    c = CollabItem(
        reference=service.reference(_PREFIX[payload.kind]),
        kind=payload.kind,
        organization_id=org.id,
        project_id=payload.project_id,
        title=payload.title,
        body=payload.body,
        due_at=payload.due_at,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        location=payload.location,
        created_by=staff.user.id,
    )
    db.add(c)
    db.flush()
    _audit(db, staff, "collab_item", c.id, "collab.created", org.id, {"kind": c.kind.value})
    db.commit()
    db.refresh(c)
    return ok(_staff_item(db, c), "Created")


@router.get(
    "/collaboration",
    response_model=ApiResponse[list[StaffCollabRow]],
    responses=_ERR,
    summary="Discussions, meetings and follow-ups, with partner response counts",
)
def list_items(
    staff: CollabReadDep,
    db: DbSession,
    page: PageDep,
    kind: Annotated[CollabKind | None, Query()] = None,
    organization_id: Annotated[uuid.UUID | None, Query()] = None,
    status: Annotated[CollabStatus | None, Query()] = None,
    shared: Annotated[bool | None, Query()] = None,
    has_partner_response: Annotated[bool | None, Query()] = None,
) -> ApiResponse[list[StaffCollabRow]]:
    counts = (
        select(CollabResponse.item_id, func.count().label("n"))
        .group_by(CollabResponse.item_id)
        .subquery()
    )
    stmt = (
        select(CollabItem, PartnerOrganization.legal_name, func.coalesce(counts.c.n, 0))
        .join(PartnerOrganization, PartnerOrganization.id == CollabItem.organization_id)
        .outerjoin(counts, counts.c.item_id == CollabItem.id)
        .where(service.org_scope(staff, CollabItem.organization_id))
    )
    if kind:
        stmt = stmt.where(CollabItem.kind == kind)
    if organization_id:
        stmt = stmt.where(CollabItem.organization_id == organization_id)
    if status:
        stmt = stmt.where(CollabItem.status == status)
    if shared is not None:
        stmt = stmt.where(
            CollabItem.shared_at.is_not(None) if shared else CollabItem.shared_at.is_(None)
        )
    if has_partner_response is not None:
        stmt = stmt.where(
            func.coalesce(counts.c.n, 0) > 0 if has_partner_response else counts.c.n.is_(None)
        )
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(CollabItem.updated_at.desc(), CollabItem.id)
        .limit(page.page_size)
        .offset(page.offset)
    ).all()
    return ok(
        [
            StaffCollabRow(
                **_collab_row(c),
                organization_id=c.organization_id,
                organization_name=name,
                is_shared=c.shared_at is not None,
                response_count=n,
            )
            for c, name, n in rows
        ],
        meta=page_meta(page, total),
    )


@router.get(
    "/collaboration/{item_id}",
    response_model=ApiResponse[StaffCollabDetail],
    responses=_ERR,
    summary="Item with every partner and staff response",
)
def get_item(
    item_id: uuid.UUID, staff: CollabReadDep, db: DbSession
) -> ApiResponse[StaffCollabDetail]:
    return ok(_staff_item(db, _item(db, staff, item_id)))


@router.patch(
    "/collaboration/{item_id}",
    response_model=ApiResponse[StaffCollabDetail],
    responses=_ERR,
    summary="Edit an item; omit = unchanged, null clears nullable fields",
)
def update_item(
    item_id: uuid.UUID, payload: CollabUpdate, staff: ReviewerDep, db: DbSession
) -> ApiResponse[StaffCollabDetail]:
    c = _item(db, staff, item_id, lock=True)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("title", "x") is None:
        raise AppError("title cannot be cleared", status_code=422, code="REQUIRED_FIELD")
    for field, value in changes.items():
        setattr(c, field, value)
    if c.starts_at and c.ends_at and c.ends_at <= c.starts_at:
        raise AppError("End must be after start", status_code=422, code="INVALID_RANGE")
    _audit(
        db,
        staff,
        "collab_item",
        c.id,
        "collab.updated",
        c.organization_id,
        {"fields": sorted(changes)},
    )
    db.commit()
    db.refresh(c)
    return ok(_staff_item(db, c), "Updated")


@router.post(
    "/collaboration/{item_id}/share",
    response_model=ApiResponse[StaffCollabDetail],
    responses=_ERR,
    summary="Share with the partner; it then awaits their response",
)
def share_item(
    item_id: uuid.UUID, staff: ReviewerDep, db: DbSession
) -> ApiResponse[StaffCollabDetail]:
    c = _item(db, staff, item_id, lock=True)
    if c.shared_at is None:
        c.shared_at, c.shared_by = utcnow(), staff.user.id
        if c.status is CollabStatus.OPEN:
            c.status = CollabStatus.AWAITING_PARTNER
        _audit(db, staff, "collab_item", c.id, "collab.shared", c.organization_id)
        db.commit()
        db.refresh(c)
    return ok(_staff_item(db, c), "Shared")


@router.post(
    "/collaboration/{item_id}/unshare",
    response_model=ApiResponse[StaffCollabDetail],
    responses=_ERR,
    summary="Hide from the partner (responses are kept)",
)
def unshare_item(
    item_id: uuid.UUID, staff: ReviewerDep, db: DbSession
) -> ApiResponse[StaffCollabDetail]:
    c = _item(db, staff, item_id, lock=True)
    if c.shared_at is not None:
        c.shared_at, c.shared_by = None, None
        _audit(db, staff, "collab_item", c.id, "collab.unshared", c.organization_id)
        db.commit()
        db.refresh(c)
    return ok(_staff_item(db, c), "Hidden from partner")


@router.post(
    "/collaboration/{item_id}/reply",
    response_model=ApiResponse[StaffCollabDetail],
    responses=_ERR,
    summary="Staff reply (visible to the partner once the item is shared)",
)
def staff_reply(
    item_id: uuid.UUID, payload: StaffReplyIn, staff: ReviewerDep, db: DbSession
) -> ApiResponse[StaffCollabDetail]:

    c = _item(db, staff, item_id, lock=True)
    if c.status in (CollabStatus.COMPLETED, CollabStatus.CANCELLED):
        raise AppError("This item is closed", status_code=409, code="ITEM_CLOSED")
    db.add(
        CollabResponse(
            item_id=c.id,
            user_id=staff.user.id,
            action=CollabAction.REPLY,
            body=payload.body,
            created_at=utcnow(),
        )
    )
    if c.shared_at is not None:
        c.status = CollabStatus.AWAITING_PARTNER
    _audit(db, staff, "collab_item", c.id, "collab.staff_reply", c.organization_id)
    db.commit()
    db.refresh(c)
    return ok(_staff_item(db, c), "Reply recorded")


@router.post(
    "/collaboration/{item_id}/close",
    response_model=ApiResponse[StaffCollabDetail],
    responses=_ERR,
    summary="Mark completed (outcome=completed) or cancelled",
)
def close_item(
    item_id: uuid.UUID,
    staff: ReviewerDep,
    db: DbSession,
    outcome: Annotated[CollabStatus, Query()] = CollabStatus.COMPLETED,
) -> ApiResponse[StaffCollabDetail]:
    if outcome not in (CollabStatus.COMPLETED, CollabStatus.CANCELLED):
        raise AppError(
            "outcome must be completed or cancelled", status_code=422, code="INVALID_OUTCOME"
        )
    c = _item(db, staff, item_id, lock=True)
    c.status = outcome
    _audit(db, staff, "collab_item", c.id, f"collab.{outcome.value}", c.organization_id)
    db.commit()
    db.refresh(c)
    return ok(_staff_item(db, c))
