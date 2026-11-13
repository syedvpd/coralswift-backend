"""Super-administrator operations: system settings, email templates, KPI report
(PRD s.14 "notification templates and system settings", s.19, s.20)."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case, exists, func, literal_column, select
from sqlalchemy.orm import Session

from app.common.pagination import PageDep, page_meta
from app.common.responses import ApiResponse, ErrorResponse, ok
from app.common.utilities import utcnow
from app.core.config import Settings, get_settings
from app.core.exceptions import AppError, NotFoundError
from app.database.dependencies import DbSession
from app.modules.admin import lookups, service
from app.modules.admin import settings_service as cfg
from app.modules.admin.models import (
    EnquiryFollowUp,
    NotificationTemplate,
    NotificationTemplateVersion,
)
from app.modules.admin.schemas import (
    CommunicationReportOut,
    DocumentReviewReportOut,
    FollowUpReportOut,
    KpisOut,
    NotificationRow,
    ReportCountOut,
    ReportPeriodCountOut,
)
from app.modules.applications.constants import PortalStatus
from app.modules.applications.models import EligibilityVerification, PortalApplication
from app.modules.auth.constants import StaffRole, UserStatus, UserType
from app.modules.auth.dependencies import StaffContext, SuperAdminDep, require_staff
from app.modules.auth.models import User
from app.modules.engagement.models import MeetingRequest
from app.modules.enquiries.activity import log_activity
from app.modules.enquiries.constants import ActorType, EnquiryStatus
from app.modules.enquiries.models import Enquiry
from app.modules.notifications.constants import DeliveryStatus, TemplateKey
from app.modules.notifications.models import Notification
from app.modules.notifications.service import dispatch_notifications
from app.modules.notifications.templates import (
    ALLOWED_PLACEHOLDERS,
    render_override,
    validate_template,
)
from app.modules.onboarding.models import OnboardingRecord
from app.modules.partner_documents.models import PartnerDocumentVersion
from app.modules.projects.constants import ProjectCategory
from app.modules.projects.models import ProjectEnquiry


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


ReportStaffDep = Annotated[
    StaffContext,
    Depends(require_staff(StaffRole.SUPER_ADMINISTRATOR, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)),
]


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


class TemplatePlaceholderOut(BaseModel):
    name: str


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


@router.get(
    "/notification-templates/placeholders",
    response_model=ApiResponse[list[TemplatePlaceholderOut]],
    responses=_ERR,
    summary="List placeholders accepted by notification templates",
)
def list_template_placeholders(
    staff: SuperAdminDep,
) -> ApiResponse[list[TemplatePlaceholderOut]]:
    return ok([TemplatePlaceholderOut(name=name) for name in sorted(ALLOWED_PLACEHOLDERS)])


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
    _record_version(db, staff, row)
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


def _record_version(
    db: Session, staff: StaffContext, row: NotificationTemplate, note: str | None = None
) -> None:
    db.add(
        NotificationTemplateVersion(
            key=row.key,
            version_no=row.version,
            subject=row.subject,
            text_body=row.text_body,
            html_body=row.html_body,
            note=note,
            created_by=staff.user.id,
            created_at=utcnow(),
        )
    )


class TemplateVersionOut(BaseModel):
    version_no: int
    subject: str
    text_body: str
    html_body: str | None
    note: str | None
    created_by_name: str | None
    created_at: datetime


@router.get(
    "/notification-templates/{key}/versions",
    response_model=ApiResponse[list[TemplateVersionOut]],
    responses=_ERR,
    summary="Saved versions of a template override, newest first",
)
def template_versions(
    key: str, staff: SuperAdminDep, db: DbSession, page: PageDep
) -> ApiResponse[list[TemplateVersionOut]]:
    k = _tkey(key)
    base = select(NotificationTemplateVersion).where(NotificationTemplateVersion.key == k.value)
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = list(
        db.execute(
            base.order_by(NotificationTemplateVersion.version_no.desc())
            .limit(page.page_size)
            .offset(page.offset)
        ).scalars()
    )
    names = lookups.user_names(db, (r.created_by for r in rows))
    return ok(
        [
            TemplateVersionOut(
                version_no=r.version_no,
                subject=r.subject,
                text_body=r.text_body,
                html_body=r.html_body,
                note=r.note,
                created_by_name=names.get(r.created_by),
                created_at=r.created_at,
            )
            for r in rows
        ],
        meta=page_meta(page, total),
    )


@router.post(
    "/notification-templates/{key}/versions/{version_no}/activate",
    response_model=ApiResponse[TemplateOut],
    responses=_ERR,
    summary="Make an earlier version active again (saved as a new version)",
)
def activate_template_version(
    key: str, version_no: int, staff: SuperAdminDep, db: DbSession
) -> ApiResponse[TemplateOut]:
    k = _tkey(key)
    old = db.execute(
        select(NotificationTemplateVersion).where(
            NotificationTemplateVersion.key == k.value,
            NotificationTemplateVersion.version_no == version_no,
        )
    ).scalar_one_or_none()
    if old is None:
        raise NotFoundError("Template version not found")
    row = db.get(NotificationTemplate, k.value)
    if row is None:  # the override was reverted; recreate it from history
        row = NotificationTemplate(
            key=k.value,
            subject=old.subject,
            text_body=old.text_body,
            html_body=old.html_body,
            version=0,
            updated_by=staff.user.id,
            updated_at=utcnow(),
        )
        db.add(row)
    row.subject, row.text_body, row.html_body = old.subject, old.text_body, old.html_body
    latest = db.execute(
        select(func.max(NotificationTemplateVersion.version_no)).where(
            NotificationTemplateVersion.key == k.value
        )
    ).scalar_one()
    row.version, row.updated_by, row.updated_at = (latest or 0) + 1, staff.user.id, utcnow()
    _record_version(db, staff, row, note=f"Reactivated version {version_no}")
    log_activity(
        db,
        "template",
        uuid.uuid5(uuid.NAMESPACE_URL, k.value),
        "admin.template_version_activated",
        {"key": k.value, "from_version": version_no, "version": row.version},
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


# ----------------------------------------------------------------------- KPIs
@router.get(
    "/reports/kpis",
    response_model=ApiResponse[KpisOut],
    responses=_ERR,
    summary="Business KPIs (PRD s.20). No targets: the PRD asks for a baseline first",
)
def kpis(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    staff: AdminDep,
    db: DbSession,
    created_from: Annotated[datetime | None, Query()] = None,
    created_to: Annotated[datetime | None, Query()] = None,
    assignee_id: Annotated[
        uuid.UUID | None, Query(description="enquiries assigned to this staff member")
    ] = None,
    category: Annotated[
        ProjectCategory | None,
        Query(description="project category of project enquiries"),
    ] = None,
) -> ApiResponse[KpisOut]:
    # Output varies only by super-admin vs BDM and the filters, so that is the cache key.
    is_super = staff.user.staff_role is StaffRole.SUPER_ADMINISTRATOR
    key = f"kpis:{is_super}:{created_from}:{created_to}:{assignee_id}:{category}"
    return ok(
        request.app.state.cache.get_or_set(
            key,
            settings.cache_ttl_seconds,
            lambda: _kpis(staff, db, created_from, created_to, assignee_id, category),
        )
    )


def _kpis(
    staff: StaffContext,
    db: Session,
    created_from: datetime | None,
    created_to: datetime | None,
    assignee_id: uuid.UUID | None,
    category: ProjectCategory | None,
) -> dict[str, Any]:
    types = service.visible_types(staff)
    base = select(Enquiry).where(Enquiry.enquiry_type.in_(types))
    if created_from:
        base = base.where(Enquiry.created_at >= created_from)
    if created_to:
        base = base.where(Enquiry.created_at < created_to)
    if assignee_id:
        base = base.where(Enquiry.assigned_user_id == assignee_id)
    if category:
        base = base.where(
            exists().where(
                ProjectEnquiry.enquiry_id == Enquiry.id, ProjectEnquiry.project_category == category
            )
        )
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
        decided = select(PortalApplication).where(
            PortalApplication.submitted_at.is_not(None), PortalApplication.decided_at.is_not(None)
        )
        if created_from:
            decided = decided.where(PortalApplication.submitted_at >= created_from)
        if created_to:
            decided = decided.where(PortalApplication.submitted_at < created_to)
        dsub = decided.subquery()
        turnaround = db.execute(
            select(
                func.count(),
                func.avg(func.extract("epoch", dsub.c.decided_at - dsub.c.submitted_at) / 3600),
            ).select_from(dsub)
        ).one()
        out["applications_decided"] = turnaround[0]
        out["application_decision_turnaround_hours_avg"] = (
            round(float(turnaround[1]), 2) if turnaround[1] is not None else None
        )
        span = OnboardingRecord.completed_at - OnboardingRecord.started_at
        onboarded = db.execute(
            select(func.count(), func.avg(func.extract("epoch", span) / 86400)).where(
                OnboardingRecord.completed_at.is_not(None)
            )
        ).one()
        out["onboarding_completed"] = onboarded[0]
        out["onboarding_duration_days_avg"] = (
            round(float(onboarded[1]), 2) if onboarded[1] is not None else None
        )
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
    return out


def _date_filters(
    column: Any, created_from: datetime | None, created_to: datetime | None
) -> list[Any]:
    filters: list[Any] = []
    if created_from is not None:
        filters.append(column >= created_from)
    if created_to is not None:
        filters.append(column < created_to)
    return filters


@router.get(
    "/reports/follow-ups",
    response_model=ApiResponse[FollowUpReportOut],
    responses=_ERR,
    summary="Follow-up counts by kind and open/completed/cancelled state",
)
def follow_up_report(
    staff: ReportStaffDep,
    db: DbSession,
    created_from: Annotated[datetime | None, Query()] = None,
    created_to: Annotated[datetime | None, Query()] = None,
) -> ApiResponse[FollowUpReportOut]:
    filters = [Enquiry.enquiry_type.in_(service.visible_types(staff))]
    filters.extend(_date_filters(EnquiryFollowUp.created_at, created_from, created_to))
    # literal_column keeps the CASE and GROUP BY expressions textually identical (no bind params)
    state = case(
        (EnquiryFollowUp.cancelled_at.is_not(None), literal_column("'cancelled'")),
        (EnquiryFollowUp.completed_at.is_not(None), literal_column("'completed'")),
        else_=literal_column("'open'"),
    )
    month = func.date_trunc(literal_column("'month'"), EnquiryFollowUp.created_at)
    by_kind = db.execute(
        select(EnquiryFollowUp.kind, func.count())
        .join(Enquiry, Enquiry.id == EnquiryFollowUp.enquiry_id)
        .where(*filters)
        .group_by(EnquiryFollowUp.kind)
        .order_by(EnquiryFollowUp.kind)
    ).all()
    by_status = db.execute(
        select(state, func.count())
        .join(Enquiry, Enquiry.id == EnquiryFollowUp.enquiry_id)
        .where(*filters)
        .group_by(state)
        .order_by(state)
    ).all()
    by_month = db.execute(
        select(month, func.count())
        .join(Enquiry, Enquiry.id == EnquiryFollowUp.enquiry_id)
        .where(*filters)
        .group_by(month)
        .order_by(month)
    ).all()
    return ok(
        FollowUpReportOut(
            total=sum(count for _key, count in by_kind),
            by_kind=[ReportCountOut(key=str(key), count=count) for key, count in by_kind],
            by_status=[ReportCountOut(key=str(key), count=count) for key, count in by_status],
            by_month=[
                ReportPeriodCountOut(period=period, count=count) for period, count in by_month
            ],
        )
    )


@router.get(
    "/reports/document-review",
    response_model=ApiResponse[DocumentReviewReportOut],
    responses=_ERR,
    summary="Partner document version review counts and observed average turnaround",
)
def document_review_report(
    staff: SuperAdminDep,
    db: DbSession,
    created_from: Annotated[datetime | None, Query()] = None,
    created_to: Annotated[datetime | None, Query()] = None,
) -> ApiResponse[DocumentReviewReportOut]:
    filters = _date_filters(PartnerDocumentVersion.uploaded_at, created_from, created_to)
    rows = db.execute(
        select(PartnerDocumentVersion.review_status, func.count())
        .where(*filters)
        .group_by(PartnerDocumentVersion.review_status)
        .order_by(PartnerDocumentVersion.review_status)
    ).all()
    avg = db.execute(
        select(
            func.avg(
                func.extract(
                    "epoch", PartnerDocumentVersion.reviewed_at - PartnerDocumentVersion.uploaded_at
                )
                / 3600
            )
        ).where(*filters, PartnerDocumentVersion.reviewed_at.is_not(None))
    ).scalar_one()
    return ok(
        DocumentReviewReportOut(
            total_versions=sum(count for _status, count in rows),
            by_review_status=[
                ReportCountOut(key=status.value, count=count) for status, count in rows
            ],
            avg_turnaround_hours=round(float(avg), 2) if avg is not None else None,
        )
    )


@router.get(
    "/reports/communications",
    response_model=ApiResponse[CommunicationReportOut],
    responses=_ERR,
    summary="Email outbox counts by delivery status and template",
)
def communication_report(
    staff: SuperAdminDep,
    db: DbSession,
    created_from: Annotated[datetime | None, Query()] = None,
    created_to: Annotated[datetime | None, Query()] = None,
) -> ApiResponse[CommunicationReportOut]:
    filters = _date_filters(Notification.created_at, created_from, created_to)
    by_status = db.execute(
        select(Notification.delivery_status, func.count())
        .where(*filters)
        .group_by(Notification.delivery_status)
        .order_by(Notification.delivery_status)
    ).all()
    by_template = db.execute(
        select(Notification.template_key, func.count())
        .where(*filters)
        .group_by(Notification.template_key)
        .order_by(Notification.template_key)
    ).all()
    return ok(
        CommunicationReportOut(
            total=sum(count for _key, count in by_status),
            by_delivery_status=[
                ReportCountOut(key=status.value, count=count) for status, count in by_status
            ],
            by_template=[
                ReportCountOut(key=template.value, count=count) for template, count in by_template
            ],
        )
    )


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
