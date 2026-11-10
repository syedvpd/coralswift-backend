"""Super-administrator operations: system settings, email templates, MFA reset, KPI report
(PRD s.14 "notification templates and system settings", s.19, s.20)."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update

from app.common.pagination import PageDep, page_meta
from app.common.responses import ApiResponse, ErrorResponse, ok
from app.common.utilities import utcnow
from app.core.config import Settings, get_settings
from app.core.exceptions import AppError, NotFoundError
from app.database.dependencies import DbSession
from app.modules.admin import lookups, service
from app.modules.admin import settings_service as cfg
from app.modules.admin.models import EnquiryFollowUp, NotificationTemplate
from app.modules.admin.schemas import NotificationRow
from app.modules.applications.constants import PortalStatus
from app.modules.applications.models import EligibilityVerification, PortalApplication
from app.modules.auth import service as auth_service
from app.modules.auth.constants import StaffRole, UserStatus, UserType
from app.modules.auth.dependencies import StaffContext, SuperAdminDep, require_staff
from app.modules.auth.models import MfaRecoveryCode, User
from app.modules.engagement.models import MeetingRequest
from app.modules.enquiries.activity import log_activity
from app.modules.enquiries.constants import ActorType, EnquiryStatus
from app.modules.enquiries.models import Enquiry
from app.modules.notifications.constants import DeliveryStatus, TemplateKey
from app.modules.notifications.models import Notification
from app.modules.notifications.service import dispatch_notifications
from app.modules.notifications.templates import render_override, validate_template
from app.modules.partner_documents.models import PartnerDocumentVersion


class QueueGate(BaseModel):
    owner: bool
    sla_hours: bool
    escalation: bool


class LaunchReadinessOut(BaseModel):
    contact: dict[str, Literal["confirmed", "omitted", "pending"]]
    queues: dict[str, QueueGate]
    ready: bool
    pending_items: list[str]


class SettingDefinition(BaseModel):
    key: str
    group: str
    value_kind: Literal["integer", "boolean", "email", "user_id", "text"]
    unit: str | None = None


class SettingsOut(BaseModel):
    values: dict[str, str]  # only settings that have been set
    allowed_keys: list[str]
    definitions: list[SettingDefinition]


def _describe(key: str) -> dict[str, Any]:
    """Read-only description of a registry key; validation itself stays in settings_service."""
    group = key.split(".")[0]
    if key.startswith("sla.") or key.startswith("retention.") or key == "expiry_reminder_days":
        unit = "hours" if group == "sla" else "days"
        return {"group": group, "value_kind": "integer", "unit": unit}
    if key.startswith("route."):
        return {"group": group, "value_kind": "user_id", "unit": None}
    if key.startswith("escalation.email."):
        return {"group": group, "value_kind": "email", "unit": None}
    if key == "ack_promise_enabled":
        return {"group": "acknowledgement", "value_kind": "boolean", "unit": None}
    return {"group": group, "value_kind": "text", "unit": None}


router = APIRouter(prefix="/admin", tags=["admin-operations"])
SettingsDep = Annotated[Settings, Depends(get_settings)]
AdminDep = Annotated[
    StaffContext,
    Depends(require_staff(StaffRole.SUPER_ADMINISTRATOR, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)),
]
_ERR: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


# ------------------------------------------------------------------ settings
class SettingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str = Field(min_length=1, max_length=200)


@router.get(
    "/settings",
    response_model=ApiResponse[SettingsOut],
    responses=_ERR,
    summary="Stored settings and the keys that can be set",
)
def list_settings(staff: SuperAdminDep, db: DbSession) -> ApiResponse[SettingsOut]:
    return ok(
        SettingsOut(
            values=cfg.list_all(db),
            allowed_keys=sorted(cfg.REGISTRY),
            definitions=[SettingDefinition(key=k, **_describe(k)) for k in sorted(cfg.REGISTRY)],
        )
    )


@router.put("/settings/{key}", response_model=ApiResponse[dict[str, str]], responses=_ERR)
def put_setting(
    key: str, payload: SettingIn, staff: SuperAdminDep, db: DbSession
) -> ApiResponse[dict[str, str]]:
    value = cfg.put(db, key, payload.value, staff.user.id)
    log_activity(
        db,
        "setting",
        uuid.uuid5(uuid.NAMESPACE_URL, key),
        "admin.setting_changed",
        {"key": key},
        ActorType.STAFF,
        actor_user_id=staff.user.id,
    )
    db.commit()
    return ok({key: value}, "Setting saved")


@router.delete("/settings/{key}", response_model=ApiResponse[None], responses=_ERR)
def delete_setting(key: str, staff: SuperAdminDep, db: DbSession) -> ApiResponse[None]:
    cfg.remove(db, key)
    log_activity(
        db,
        "setting",
        uuid.uuid5(uuid.NAMESPACE_URL, key),
        "admin.setting_removed",
        {"key": key},
        ActorType.STAFF,
        actor_user_id=staff.user.id,
    )
    db.commit()
    return ok(None, "Setting removed")


# ------------------------------------------------------------------ templates
class TemplateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=1, max_length=200)
    text_body: str = Field(min_length=1, max_length=20_000)
    html_body: str | None = Field(default=None, max_length=50_000)


class TemplateOut(BaseModel):
    key: str
    customised: bool
    version: int | None
    subject: str | None
    text_body: str | None
    html_body: str | None


def _tkey(key: str) -> TemplateKey:
    try:
        return TemplateKey(key)
    except ValueError:
        raise NotFoundError("Unknown template") from None


@router.get(
    "/notification-templates",
    response_model=ApiResponse[list[TemplateOut]],
    responses=_ERR,
    summary="All template keys; customised ones include their text",
)
def list_templates(staff: SuperAdminDep, db: DbSession) -> ApiResponse[list[TemplateOut]]:
    custom = {t.key: t for t in db.execute(select(NotificationTemplate)).scalars()}
    out = []
    for k in TemplateKey:
        t = custom.get(k.value)
        out.append(
            TemplateOut(
                key=k.value,
                customised=t is not None,
                version=t.version if t else None,
                subject=t.subject if t else None,
                text_body=t.text_body if t else None,
                html_body=t.html_body if t else None,
            )
        )
    return ok(out)


@router.put(
    "/notification-templates/{key}",
    response_model=ApiResponse[TemplateOut],
    responses=_ERR,
    summary="Override a built-in email template (allowed placeholders only)",
)
def put_template(
    key: str, payload: TemplateIn, staff: SuperAdminDep, db: DbSession
) -> ApiResponse[TemplateOut]:
    k = _tkey(key)
    try:
        validate_template(k.value, payload.subject, payload.text_body, payload.html_body)
    except ValueError as exc:
        raise AppError(str(exc), status_code=422, code="INVALID_TEMPLATE") from None
    row = db.get(NotificationTemplate, k.value)
    if row is None:
        row = NotificationTemplate(
            key=k.value,
            subject=payload.subject,
            text_body=payload.text_body,
            html_body=payload.html_body,
            version=1,
            updated_by=staff.user.id,
            updated_at=utcnow(),
        )
        db.add(row)
    else:
        row.subject, row.text_body, row.html_body = (
            payload.subject,
            payload.text_body,
            payload.html_body,
        )
        row.version, row.updated_by, row.updated_at = row.version + 1, staff.user.id, utcnow()
    log_activity(
        db,
        "template",
        uuid.uuid5(uuid.NAMESPACE_URL, k.value),
        "admin.template_changed",
        {"key": k.value, "version": row.version},
        ActorType.STAFF,
        actor_user_id=staff.user.id,
    )
    db.commit()
    return ok(
        TemplateOut(
            key=k.value,
            customised=True,
            version=row.version,
            subject=row.subject,
            text_body=row.text_body,
            html_body=row.html_body,
        )
    )


@router.delete(
    "/notification-templates/{key}",
    response_model=ApiResponse[None],
    responses=_ERR,
    summary="Revert to the built-in template",
)
def delete_template(key: str, staff: SuperAdminDep, db: DbSession) -> ApiResponse[None]:
    k = _tkey(key)
    row = db.get(NotificationTemplate, k.value)
    if row is not None:
        db.delete(row)
        log_activity(
            db,
            "template",
            uuid.uuid5(uuid.NAMESPACE_URL, k.value),
            "admin.template_reverted",
            {"key": k.value},
            ActorType.STAFF,
            actor_user_id=staff.user.id,
        )
        db.commit()
    return ok(None, "Reverted")


@router.post(
    "/notification-templates/{key}/preview",
    response_model=ApiResponse[dict[str, str]],
    responses=_ERR,
    summary="Render a template with sample values (no email is sent)",
)
def preview_template(
    key: str, payload: TemplateIn, staff: SuperAdminDep
) -> ApiResponse[dict[str, str]]:
    _tkey(key)
    sample = {
        "name": "Alex Sample",
        "reference": "CS-ENQ-2026-000000",
        "status_label": "Under review",
        "link": "https://example.invalid/token",
        "enquiry_type": "general",
        "company": "Sample Ltd",
        "category": "registration_proof",
        "expires_on": "2030-01-01",
        "meeting_time": "2030-01-01 10:00 - 10:30 UTC",
    }
    try:
        validate_template(key, payload.subject, payload.text_body, payload.html_body)
    except ValueError as exc:
        raise AppError(str(exc), status_code=422, code="INVALID_TEMPLATE") from None
    subject, text, html = render_override(
        payload.subject, payload.text_body, payload.html_body, sample
    )
    return ok({"subject": subject, "text": text, "html": html})


# ----------------------------------------------------------------- MFA reset
@router.post(
    "/users/{user_id}/mfa-reset",
    response_model=ApiResponse[None],
    responses=_ERR,
    summary="Clear a staff member's MFA after a lost device (they must re-enroll)",
)
def mfa_reset(user_id: uuid.UUID, staff: SuperAdminDep, db: DbSession) -> ApiResponse[None]:
    if user_id == staff.user.id:
        raise AppError("You cannot reset your own MFA", status_code=409, code="SELF_CHANGE")
    user = db.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one_or_none()
    if user is None:
        raise NotFoundError("User not found")
    user.mfa_secret_enc, user.mfa_enabled_at, user.mfa_last_step = None, None, None
    db.execute(
        update(MfaRecoveryCode)
        .where(MfaRecoveryCode.user_id == user.id, MfaRecoveryCode.used_at.is_(None))
        .values(used_at=utcnow())
    )
    auth_service.revoke_all_sessions(db, user.id, "mfa_reset")
    log_activity(
        db, "user", user.id, "admin.mfa_reset", None, ActorType.STAFF, actor_user_id=staff.user.id
    )
    db.commit()
    return ok(None, "MFA cleared")


# ----------------------------------------------------------------------- KPIs
@router.get(
    "/reports/kpis",
    response_model=ApiResponse[dict[str, Any]],
    responses=_ERR,
    summary="Business KPIs (PRD s.20). No targets: the PRD asks for a baseline first",
)
def kpis(
    staff: AdminDep,
    db: DbSession,
    created_from: Annotated[datetime | None, Query()] = None,
    created_to: Annotated[datetime | None, Query()] = None,
) -> ApiResponse[dict[str, Any]]:
    types = service.visible_types(staff)
    base = select(Enquiry).where(Enquiry.enquiry_type.in_(types))
    if created_from:
        base = base.where(Enquiry.created_at >= created_from)
    if created_to:
        base = base.where(Enquiry.created_at < created_to)
    sub = base.subquery()
    by_source = db.execute(
        select(sub.c.enquiry_type, sub.c.source, func.count()).group_by(
            sub.c.enquiry_type, sub.c.source
        )
    ).all()
    by_status = db.execute(
        select(sub.c.enquiry_type, sub.c.status, func.count()).group_by(
            sub.c.enquiry_type, sub.c.status
        )
    ).all()
    follow_up = db.execute(
        select(func.count())
        .select_from(sub)
        .where(sub.c.next_follow_up_at < utcnow(), sub.c.status != EnquiryStatus.CLOSED.value)
    ).scalar_one()
    first_note = (
        select(EnquiryFollowUp.enquiry_id, func.min(EnquiryFollowUp.created_at).label("first_at"))
        .group_by(EnquiryFollowUp.enquiry_id)
        .subquery()
    )
    response_hours = db.execute(
        select(
            func.avg(func.extract("epoch", first_note.c.first_at - sub.c.created_at) / 3600)
        ).select_from(sub.join(first_note, first_note.c.enquiry_id == sub.c.id))
    ).scalar_one()
    out: dict[str, Any] = {
        "avg_hours_to_first_follow_up": round(float(response_hours), 2)
        if response_hours is not None
        else None,
        "enquiries_by_type_and_source": [
            {"type": t.value if hasattr(t, "value") else t, "source": s, "count": n}
            for t, s, n in by_source
        ],
        "enquiries_by_type_and_status": [
            {
                "type": t.value if hasattr(t, "value") else t,
                "status": s.value if hasattr(s, "value") else s,
                "count": n,
            }
            for t, s, n in by_status
        ],
        "overdue_follow_ups": follow_up,
        "meeting_requests_by_status": {
            s.value: n
            for s, n in db.execute(
                select(MeetingRequest.status, func.count()).group_by(MeetingRequest.status)
            ).all()
        },
    }
    if staff.user.staff_role is StaffRole.SUPER_ADMINISTRATOR:
        apps = dict(
            db.execute(
                select(PortalApplication.status, func.count()).group_by(PortalApplication.status)
            ).all()
        )
        total = sum(apps.values())
        submitted_ever = db.execute(
            select(func.count())
            .select_from(PortalApplication)
            .where(PortalApplication.submission_count > 0)
        ).scalar_one()
        out["partner_application_completion"] = {
            "created": total,
            "submitted": submitted_ever,
            "rate": round(submitted_ever / total, 3) if total else None,
            "by_status": {s.value: n for s, n in apps.items() if s is not PortalStatus.DRAFT},
        }
        out["portal_adoption"] = {  # PRD s.20: partners who accepted an invitation and can sign in
            "active_partner_users": db.execute(
                select(func.count())
                .select_from(User)
                .where(User.user_type == UserType.PARTNER, User.status == UserStatus.ACTIVE)
            ).scalar_one()
        }
        # Humans decide eligibility; this only counts what reviewers recorded.
        out["eligibility_outcomes_recorded"] = {
            o.value: n
            for o, n in db.execute(
                select(EligibilityVerification.outcome, func.count()).group_by(
                    EligibilityVerification.outcome
                )
            ).all()
        }
        hours = db.execute(
            select(
                func.avg(
                    func.extract(
                        "epoch",
                        PartnerDocumentVersion.reviewed_at - PartnerDocumentVersion.uploaded_at,
                    )
                    / 3600
                )
            ).where(PartnerDocumentVersion.reviewed_at.is_not(None))
        ).scalar_one()
        out["document_review_turnaround_hours_avg"] = (
            round(float(hours), 2) if hours is not None else None
        )
    return ok(out)


# ------------------------------------------------- notification failure visibility
@router.get(
    "/notifications",
    response_model=ApiResponse[list[NotificationRow]],
    responses=_ERR,
    summary="Outbox rows (default: failed) with filters and sorting",
)
def list_notifications(
    staff: SuperAdminDep,
    db: DbSession,
    page: PageDep,
    status: Annotated[DeliveryStatus | Literal["all"], Query()] = DeliveryStatus.FAILED,
    template: Annotated[TemplateKey | None, Query()] = None,
    q: Annotated[
        str | None, Query(max_length=120, description="Partial match on recipient")
    ] = None,
    created_from: Annotated[datetime | None, Query()] = None,
    created_to: Annotated[datetime | None, Query()] = None,
    sort: Annotated[Literal["created_at", "-created_at"], Query()] = "-created_at",
) -> ApiResponse[list[NotificationRow]]:
    stmt = select(Notification)
    if status != "all":
        stmt = stmt.where(Notification.delivery_status == status)
    if template:
        stmt = stmt.where(Notification.template_key == template)
    if q:
        stmt = stmt.where(Notification.recipient.ilike(service._like(q), escape="\\"))
    if created_from:
        stmt = stmt.where(Notification.created_at >= created_from)
    if created_to:
        stmt = stmt.where(Notification.created_at < created_to)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    # id is the tie-breaker so pages are stable when rows share a timestamp
    order = (
        (Notification.created_at.asc(), Notification.id.asc())
        if sort == "created_at"
        else (Notification.created_at.desc(), Notification.id.desc())
    )
    rows = list(
        db.execute(stmt.order_by(*order).limit(page.page_size).offset(page.offset)).scalars()
    )
    strategic = lookups.strategic_enquiry_ids(db, (n.enquiry_id for n in rows))
    return ok(
        [
            NotificationRow(
                id=n.id,
                recipient=n.recipient,
                template=n.template_key.value,
                notification_type=n.notification_type.value,
                status=n.delivery_status.value,
                retry_count=n.retry_count,
                last_error=n.last_error,
                created_at=n.created_at,
                sent_at=n.sent_at,
                enquiry_id=n.enquiry_id,
                is_strategic=n.enquiry_id in strategic,
            )
            for n in rows
        ],
        meta=page_meta(page, total),
    )


@router.post(
    "/notifications/dispatch",
    status_code=202,
    response_model=ApiResponse[dict[str, int]],
    responses=_ERR,
    summary="Retry eligible emails now (runs after the response; rows past the cap need /retry)",
)
def dispatch_now(
    request: Request,
    staff: SuperAdminDep,
    db: DbSession,
    settings: SettingsDep,
    background: BackgroundTasks,
) -> ApiResponse[dict[str, int]]:
    eligible = db.execute(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.delivery_status.in_([DeliveryStatus.PENDING, DeliveryStatus.FAILED]),
            Notification.retry_count < settings.notification_max_retries,
        )
    ).scalar_one()
    background.add_task(
        dispatch_notifications,
        request.app.state.sessionmaker,
        request.app.state.email_sender,
        settings,
        None,
        100,
    )
    return ok({"queued": eligible})


@router.post(
    "/notifications/{notification_id}/retry",
    response_model=ApiResponse[None],
    responses=_ERR,
    summary="Reset a failed email so it will be attempted again",
)
def retry_notification(
    notification_id: uuid.UUID, staff: SuperAdminDep, db: DbSession
) -> ApiResponse[None]:
    row = db.execute(
        select(Notification).where(Notification.id == notification_id).with_for_update()
    ).scalar_one_or_none()
    if row is None or row.delivery_status is not DeliveryStatus.FAILED:
        raise NotFoundError("No failed notification with that id")
    row.retry_count, row.delivery_status = 0, DeliveryStatus.PENDING
    log_activity(
        db,
        "notification",
        row.id,
        "admin.notification_retry_requested",
        None,
        ActorType.STAFF,
        actor_user_id=staff.user.id,
    )
    db.commit()
    return ok(None, "Queued for retry")


# ------------------------------------------------------------ launch readiness
@router.get(
    "/launch-readiness",
    response_model=ApiResponse[LaunchReadinessOut],
    responses=_ERR,
    summary="PRD s.28 launch gates: contact details and queue configuration",
)
def launch_readiness(staff: SuperAdminDep, db: DbSession) -> ApiResponse[LaunchReadinessOut]:
    values = cfg.list_all(db)
    contact: dict[str, Literal["confirmed", "omitted", "pending"]] = {}
    for item in cfg.CONTACT_ITEMS:
        if f"contact.{item}" in values:
            contact[item] = "confirmed"
        elif values.get(f"contact.{item}.omitted") == "true":
            contact[item] = "omitted"
        else:
            contact[item] = "pending"
    queues = {
        q: QueueGate(
            owner=f"route.owner.{q}" in values,
            sla_hours=f"sla.{q}" in values,
            escalation=f"escalation.email.{q}" in values,
        )
        for q in cfg.QUEUES
    }
    pending = [f"contact.{k}" for k, v in contact.items() if v == "pending"]
    for q, gate in queues.items():
        pending += [f"{q}.{k}" for k, ok_ in gate.model_dump().items() if not ok_]
    return ok(
        LaunchReadinessOut(
            contact=contact, queues=queues, ready=not pending, pending_items=sorted(pending)
        )
    )
