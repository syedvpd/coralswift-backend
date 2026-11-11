"""Partner dashboard extras (PRD s.13): change requests, notifications, enquiry history."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.common.pagination import PageDep, page_meta
from app.common.responses import ApiResponse, ErrorResponse, ok
from app.common.utilities import utcnow
from app.common.validation import Long
from app.core.config import Settings, get_settings
from app.core.exceptions import AppError, NotFoundError
from app.core.protection import rate_limit
from app.database.dependencies import DbSession
from app.modules.auth.dependencies import PartnerContext, PartnerDep, StaffContext, SuperAdminDep
from app.modules.auth.models import User
from app.modules.enquiries.activity import log_activity
from app.modules.enquiries.constants import ActorType
from app.modules.enquiries.models import Contact, Enquiry
from app.modules.notifications.constants import NotificationType, TemplateKey
from app.modules.notifications.models import Notification
from app.modules.notifications.service import dispatch_notifications, queue_notification
from app.modules.organizations import service
from app.modules.organizations.models import PartnerOrganization, ProfileChangeRequest
from app.modules.organizations.schemas import ProfileUpdate

partner = APIRouter(prefix="/partner", tags=["partner-dashboard"])
admin = APIRouter(prefix="/admin/profile-change-requests", tags=["admin-profile-changes"])
SettingsDep = Annotated[Settings, Depends(get_settings)]
_ERR: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


class ChangeRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    changes: ProfileUpdate
    reason: Long


class DecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approve: bool
    note: Long | None = None


class ChangeRequestOut(BaseModel):
    id: uuid.UUID
    changes: dict[str, Any]
    reason: str
    status: str
    decision_note: str | None
    created_at: datetime
    decided_at: datetime | None


class AdminChangeRequestOut(ChangeRequestOut):
    organization_id: uuid.UUID
    organization_name: str | None = None
    before: dict[str, Any] = {}  # current profile values of the requested fields (pending requests)


def _out(r: ProfileChangeRequest) -> ChangeRequestOut:
    return ChangeRequestOut(
        id=r.id,
        changes=r.changes,
        reason=r.reason,
        status=r.status,
        decision_note=r.decision_note,
        created_at=r.created_at,
        decided_at=r.decided_at,
    )


@partner.post(
    "/organization/change-requests",
    status_code=201,
    response_model=ApiResponse[ChangeRequestOut],
    dependencies=[Depends(rate_limit("application-action"))],
    responses=_ERR,
    summary="Ask staff to approve a profile change",
)
def create_request(
    payload: ChangeRequestIn, ctx: PartnerDep, db: DbSession
) -> ApiResponse[ChangeRequestOut]:
    changes = payload.changes.model_dump(
        mode="json", exclude_unset=True, exclude={"expected_version"}
    )  # explicit nulls are kept: they request clearing a value
    if not changes:
        raise AppError("No changes supplied", status_code=422, code="NO_CHANGES")
    if "legal_name" in changes and changes["legal_name"] is None:
        raise AppError("Legal name cannot be cleared", status_code=422, code="FIELD_NOT_CLEARABLE")
    row = ProfileChangeRequest(
        organization_id=ctx.organization_id,
        requested_by=ctx.user.id,
        changes=changes,
        reason=payload.reason,
        created_at=utcnow(),
    )
    db.add(row)
    db.flush()
    log_activity(
        db,
        "organization",
        ctx.organization_id,
        "organization.change_requested",
        {"fields": sorted(changes)},
        ActorType.PARTNER,
        actor_user_id=ctx.user.id,
        organization_id=ctx.organization_id,
    )
    db.commit()
    return ok(_out(row))


@partner.get(
    "/organization/change-requests",
    response_model=ApiResponse[list[ChangeRequestOut]],
    responses=_ERR,
)
def list_requests(ctx: PartnerDep, db: DbSession) -> ApiResponse[list[ChangeRequestOut]]:
    rows = db.execute(
        select(ProfileChangeRequest)
        .where(ProfileChangeRequest.organization_id == ctx.organization_id)
        .order_by(ProfileChangeRequest.created_at.desc())
    ).scalars()
    return ok([_out(r) for r in rows])


TITLES = {
    "application_submitted": "Application submitted",
    "information_requested": "Additional information requested",
    "application_status_changed": "Application status changed",
    "application_decision": "Application decision",
    "expiry_reminder": "A document is about to expire",
    "profile_change_decision": "Profile change request reviewed",
    "privacy_request_ack": "Privacy request received",
    "partner_response_received": "Your response was received",
    "partner_invitation": "Account invitation",
}


DESCRIPTIONS = {
    "application_submitted": "We received your partner application. This is a receipt only.",
    "information_requested": "The reviewer needs more information. Open the application.",
    "application_status_changed": "The stage of your application changed.",
    "application_decision": "A decision was recorded on your application.",
    "expiry_reminder": "One of your documents is close to its expiry date.",
    "profile_change_decision": "Staff reviewed your profile change request.",
    "privacy_request_ack": "We received your privacy request.",
    "partner_response_received": "We received your response.",
    "partner_invitation": "You were invited to the portal.",
}
APPLICATION_TEMPLATES = frozenset(
    {
        "application_submitted",
        "information_requested",
        "application_status_changed",
        "application_decision",
        "partner_response_received",
    }
)


class RelatedRecord(BaseModel):
    type: str  # application
    reference: str


class PartnerNotificationOut(BaseModel):
    id: uuid.UUID
    template: str  # which message it was; email content is never returned
    title: str
    description: str  # fixed text per template, no free text or tokens
    related_record: RelatedRecord | None = None
    # Portal-relative path for the related record (assumed frontend route; null when none)
    link: str | None = None
    category: str  # application | account | acknowledgement | other
    related_reference: str | None  # application / enquiry reference, when the message has one
    delivery_status: str
    created_at: datetime
    read_at: datetime | None
    is_read: bool


class PartnerEnquiryOut(BaseModel):
    reference_number: str
    enquiry_type: str
    status: str
    submitted_at: datetime


def _notification_out(n: Notification) -> PartnerNotificationOut:
    ref = (n.context or {}).get("reference")
    return PartnerNotificationOut(
        id=n.id,
        template=n.template_key.value,
        title=TITLES.get(n.template_key.value, "Message from Coral Swift"),
        description=DESCRIPTIONS.get(n.template_key.value, "A message was sent to you."),
        related_record=(
            RelatedRecord(type="application", reference=ref)
            if isinstance(ref, str) and n.template_key.value in APPLICATION_TEMPLATES
            else None
        ),
        link=(
            f"/applications?reference={ref}"
            if isinstance(ref, str) and n.template_key.value in APPLICATION_TEMPLATES
            else None
        ),
        category=n.notification_type.value
        if n.notification_type.value in ("application", "account", "acknowledgement")
        else "other",
        related_reference=ref if isinstance(ref, str) else None,
        delivery_status=n.delivery_status.value,
        created_at=n.created_at,
        read_at=n.read_at,
        is_read=n.read_at is not None,
    )


def _mine(ctx: PartnerContext) -> list[Any]:
    return [
        Notification.recipient == ctx.user.email,
        Notification.notification_type != NotificationType.ACCOUNT,
    ]


@partner.get(
    "/notifications",
    response_model=ApiResponse[list[PartnerNotificationOut]],
    responses=_ERR,
    summary="Messages sent to you with read state (meta has total and unread counts)",
)
def my_notifications(
    ctx: PartnerDep,
    db: DbSession,
    page: PageDep,
    unread: Annotated[bool, Query(description="Only unread")] = False,
) -> ApiResponse[list[PartnerNotificationOut]]:
    base = select(Notification).where(*_mine(ctx))
    unread_count = db.execute(
        select(func.count()).select_from(base.where(Notification.read_at.is_(None)).subquery())
    ).scalar_one()
    stmt = base.where(Notification.read_at.is_(None)) if unread else base
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(page.page_size)
        .offset(page.offset)
    ).scalars()
    return ok(
        [_notification_out(n) for n in rows],
        meta={**page_meta(page, total), "unread": unread_count},
    )


@partner.get(
    "/notifications/unread-count",
    response_model=ApiResponse[dict[str, int]],
    responses=_ERR,
    summary="Number of unread messages",
)
def unread_count(ctx: PartnerDep, db: DbSession) -> ApiResponse[dict[str, int]]:
    n = db.execute(
        select(func.count())
        .select_from(Notification)
        .where(*_mine(ctx), Notification.read_at.is_(None))
    ).scalar_one()
    return ok({"unread": n})


@partner.post(
    "/notifications/{notification_id}/unread",
    response_model=ApiResponse[PartnerNotificationOut],
    responses=_ERR,
    summary="Mark one message as unread again",
)
def mark_unread(
    notification_id: uuid.UUID, ctx: PartnerDep, db: DbSession
) -> ApiResponse[PartnerNotificationOut]:
    n = db.execute(
        select(Notification).where(Notification.id == notification_id, *_mine(ctx))
    ).scalar_one_or_none()
    if n is None:
        raise NotFoundError("Notification not found")
    n.read_at = None
    db.commit()
    return ok(_notification_out(n))


@partner.post(
    "/notifications/read-all",
    response_model=ApiResponse[dict[str, int]],
    responses=_ERR,
    summary="Mark all your messages as read",
)
def read_all(ctx: PartnerDep, db: DbSession) -> ApiResponse[dict[str, int]]:
    result = db.execute(
        update(Notification)
        .where(*_mine(ctx), Notification.read_at.is_(None))
        .values(read_at=utcnow())
    )
    db.commit()
    return ok({"marked": int(getattr(result, "rowcount", 0))})


@partner.post(
    "/notifications/{notification_id}/read",
    response_model=ApiResponse[PartnerNotificationOut],
    responses=_ERR,
    summary="Mark one message as read (only your own; others are 404)",
)
def read_one(
    notification_id: uuid.UUID, ctx: PartnerDep, db: DbSession
) -> ApiResponse[PartnerNotificationOut]:
    n = db.execute(
        select(Notification).where(Notification.id == notification_id, *_mine(ctx))
    ).scalar_one_or_none()
    if n is None:
        raise NotFoundError("Notification not found")
    if n.read_at is None:
        n.read_at = utcnow()
        db.commit()
    return ok(_notification_out(n))


@partner.get(
    "/enquiries",
    response_model=ApiResponse[list[PartnerEnquiryOut]],
    responses=_ERR,
    summary="Enquiry history: your organization's origin enquiry and your own submissions",
)
def my_enquiries(ctx: PartnerDep, db: DbSession) -> ApiResponse[list[PartnerEnquiryOut]]:
    org = db.get(PartnerOrganization, ctx.organization_id)
    conds = [Contact.business_email == ctx.user.email]
    if org and org.source_enquiry_id:
        conds.append(Enquiry.id == org.source_enquiry_id)
    rows = db.execute(
        select(Enquiry)
        .join(Contact, Contact.id == Enquiry.contact_id)
        .where(or_(*conds))
        .order_by(Enquiry.created_at.desc())
        .limit(50)
    ).scalars()
    return ok(
        [
            PartnerEnquiryOut(
                reference_number=e.reference_number,
                enquiry_type=e.enquiry_type.value,
                status=e.status.value,
                submitted_at=e.created_at,
            )
            for e in rows
        ]
    )


# ---------------------------------------------------------------- staff side
def decide(
    db: Session, staff: StaffContext, request_id: uuid.UUID, approve: bool, note: str | None
) -> ProfileChangeRequest:
    row = db.execute(
        select(ProfileChangeRequest).where(ProfileChangeRequest.id == request_id).with_for_update()
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("Request not found")
    if row.status != "pending":
        raise AppError("Already decided", status_code=409, code="INVALID_TRANSITION")
    if approve:
        service.apply_profile_update(
            db,
            row.organization_id,
            staff.user.id,
            ProfileUpdate(**row.changes),
            ActorType.REVIEWER,
            commit=False,
        )
    row.status, row.reviewed_by, row.decision_note, row.decided_at = (
        ("approved" if approve else "rejected"),
        staff.user.id,
        note,
        utcnow(),
    )
    requester = db.get(User, row.requested_by)
    if requester:
        queue_notification(
            db,
            recipient=requester.email,
            kind=NotificationType.APPLICATION,
            template=TemplateKey.PROFILE_CHANGE_DECISION,
            context={"name": requester.full_name, "status_label": row.status},
            dedupe_key=f"profile-change:{row.id}",
        )
    log_activity(
        db,
        "organization",
        row.organization_id,
        "organization.change_request_decided",
        {"status": row.status},
        ActorType.REVIEWER,
        actor_user_id=staff.user.id,
        organization_id=row.organization_id,
    )
    db.commit()
    return row


@admin.get(
    "",
    response_model=ApiResponse[list[AdminChangeRequestOut]],
    responses=_ERR,
    summary="Profile change requests (super administrator)",
)
def admin_list(
    staff: SuperAdminDep,
    db: DbSession,
    page: PageDep,
    status: Annotated[Literal["pending", "approved", "rejected"], Query()] = "pending",
) -> ApiResponse[list[AdminChangeRequestOut]]:
    stmt = select(ProfileChangeRequest).where(ProfileChangeRequest.status == status)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(ProfileChangeRequest.created_at, ProfileChangeRequest.id)
        .limit(page.page_size)
        .offset(page.offset)
    ).scalars()
    listed = list(rows)
    orgs = {
        o.id: o
        for o in db.execute(
            select(PartnerOrganization).where(
                PartnerOrganization.id.in_({r.organization_id for r in listed})
            )
        ).scalars()
    }
    return ok(
        [
            AdminChangeRequestOut(
                **_out(r).model_dump(),
                organization_id=r.organization_id,
                organization_name=orgs[r.organization_id].legal_name,
                before={
                    f: service._jsonable(getattr(orgs[r.organization_id], f, None))
                    for f in r.changes
                }
                if r.status == "pending"
                else {},
            )
            for r in listed
        ],
        meta=page_meta(page, total),
    )


@admin.post("/{request_id}/decide", response_model=ApiResponse[ChangeRequestOut], responses=_ERR)
def admin_decide(
    request_id: uuid.UUID,
    payload: DecisionIn,
    request: Request,
    staff: SuperAdminDep,
    db: DbSession,
    settings: SettingsDep,
    background: BackgroundTasks,
) -> ApiResponse[ChangeRequestOut]:
    row = decide(db, staff, request_id, payload.approve, payload.note)
    background.add_task(
        dispatch_notifications,
        request.app.state.sessionmaker,
        request.app.state.email_sender,
        settings,
    )
    return ok(_out(row), "Decision recorded")
