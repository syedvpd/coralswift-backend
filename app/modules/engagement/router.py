"""Meeting requests (PRD s.12/s.15D), newsletter opt-in (s.15E), privacy requests (s.19)."""

import csv
import io
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from app.common.pagination import PageDep, page_meta
from app.common.responses import ApiResponse, ErrorResponse, ok
from app.core.config import Settings, get_settings
from app.core.protection import SubmissionGuards, rate_limit, require_human
from app.database.dependencies import DbSession
from app.modules.admin import service as admin_service
from app.modules.auth.constants import StaffRole
from app.modules.auth.dependencies import PartnerDep, StaffContext, SuperAdminDep, require_staff
from app.modules.engagement import service
from app.modules.engagement.models import (
    NewsletterSubscription,
    PrivacyRequest,
    PrivacyRequestStatus,
)
from app.modules.engagement.schemas import (
    MeetingConfirmIn,
    MeetingRequestIn,
    NewsletterIn,
    PartnerPrivacyRequestIn,
    PartnerPrivacyRequestOut,
    PrivacyRequestIn,
    PrivacyRequestOut,
    PrivacyUpdateIn,
    PrivacyVerifyIn,
    ReasonIn,
    UnsubscribeIn,
)
from app.modules.enquiries.activity import log_activity
from app.modules.enquiries.constants import ActorType
from app.modules.enquiries.schemas import SubmissionOut
from app.modules.enquiries.submission import IdempotencyKeyHeader, execute_submission
from app.modules.notifications.service import dispatch_notifications

public = APIRouter(tags=["engagement"])
admin = APIRouter(prefix="/admin", tags=["admin-engagement"])
AdminDep = Annotated[
    StaffContext,
    Depends(require_staff(StaffRole.SUPER_ADMINISTRATOR, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)),
]
SettingsDep = Annotated[Settings, Depends(get_settings)]
_ERR: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    429: {"model": ErrorResponse},
}


def _dispatch(request: Request, settings: Settings, background: BackgroundTasks) -> None:
    background.add_task(
        dispatch_notifications,
        request.app.state.sessionmaker,
        request.app.state.email_sender,
        settings,
    )


# ------------------------------------------------------------------ public
@public.post(
    "/meetings",
    status_code=201,
    response_model=ApiResponse[SubmissionOut],
    dependencies=SubmissionGuards,
    responses=_ERR,
    summary="Request an introductory meeting (not a confirmed booking)",
)
def request_meeting(
    payload: MeetingRequestIn,
    request: Request,
    db: DbSession,
    settings: SettingsDep,
    background: BackgroundTasks,
    idempotency_key: IdempotencyKeyHeader = None,
) -> JSONResponse:
    """Slots are preferences only. Staff confirm after checking real calendar availability; status
    can be followed with GET /enquiries/{reference}/status."""
    return execute_submission(
        request=request,
        db=db,
        settings=settings,
        background=background,
        payload=payload,
        idem_key=idempotency_key,
        create=lambda: service.create_meeting_request(db, settings, payload),
    )


@public.post(
    "/newsletter/subscribe",
    response_model=ApiResponse[dict[str, str]],
    dependencies=SubmissionGuards,
    responses=_ERR,
    summary="Newsletter opt-in (consent recorded; nothing is sent by this API)",
)
def newsletter_subscribe(
    payload: NewsletterIn, db: DbSession, settings: SettingsDep
) -> ApiResponse[dict[str, str]]:
    token = service.subscribe(db, settings, payload.email)
    return ok({"unsubscribe_token": token}, "Subscribed")


@public.post(
    "/newsletter/unsubscribe",
    response_model=ApiResponse[None],
    dependencies=[Depends(rate_limit("submit")), Depends(require_human)],
    responses=_ERR,
)
def newsletter_unsubscribe(
    payload: UnsubscribeIn, db: DbSession, settings: SettingsDep
) -> ApiResponse[None]:
    service.unsubscribe(db, settings, payload.email, payload.token)
    return ok(None, "Unsubscribed")


@public.post(
    "/privacy/requests",
    status_code=201,
    response_model=ApiResponse[dict[str, str]],
    dependencies=SubmissionGuards,
    responses=_ERR,
    summary="Data access / correction / deletion request",
)
def privacy_request(
    payload: PrivacyRequestIn,
    request: Request,
    db: DbSession,
    settings: SettingsDep,
    background: BackgroundTasks,
) -> ApiResponse[dict[str, str]]:
    row = service.create_privacy_request(db, settings, payload.email, payload.kind, payload.details)
    _dispatch(request, settings, background)
    return ok({"reference": row.reference}, "Request received")


@public.post(
    "/privacy/requests/verify",
    response_model=ApiResponse[dict[str, str]],
    dependencies=[Depends(rate_limit("submit"))],
    responses=_ERR,
    summary="Confirm the email address of a privacy request (link from the email, single use)",
)
def privacy_verify(payload: PrivacyVerifyIn, db: DbSession) -> ApiResponse[dict[str, str]]:
    row = service.verify_privacy_email(db, payload.token)
    return ok({"reference": row.reference}, "Email confirmed")


partner = APIRouter(prefix="/partner/privacy-requests", tags=["partner-privacy"])


def _partner_privacy_out(r: PrivacyRequest) -> PartnerPrivacyRequestOut:
    closed = r.status in (PrivacyRequestStatus.COMPLETED, PrivacyRequestStatus.REJECTED)
    return PartnerPrivacyRequestOut(
        reference=r.reference,
        kind=r.kind,
        status=r.status,
        details=r.details,
        resolution_note=r.resolution_note if closed else None,
        created_at=r.created_at,
    )


@partner.post(
    "",
    status_code=201,
    response_model=ApiResponse[PartnerPrivacyRequestOut],
    dependencies=[Depends(rate_limit("submit"))],
    responses=_ERR,
    summary="Submit a data access / correction / deletion request as the signed-in partner",
)
def partner_privacy_request(
    payload: PartnerPrivacyRequestIn,
    request: Request,
    ctx: PartnerDep,
    db: DbSession,
    settings: SettingsDep,
    background: BackgroundTasks,
) -> ApiResponse[PartnerPrivacyRequestOut]:
    row = service.create_privacy_request(
        db, settings, ctx.user.email, payload.kind, payload.details, submitted_by=ctx.user.id
    )
    _dispatch(request, settings, background)
    return ok(_partner_privacy_out(row), "Request received")


@partner.get(
    "",
    response_model=ApiResponse[list[PartnerPrivacyRequestOut]],
    responses=_ERR,
    summary="Your own privacy requests",
)
def my_privacy_requests(
    ctx: PartnerDep, db: DbSession, page: PageDep
) -> ApiResponse[list[PartnerPrivacyRequestOut]]:
    stmt = select(PrivacyRequest).where(PrivacyRequest.submitted_by_user_id == ctx.user.id)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(PrivacyRequest.created_at.desc(), PrivacyRequest.id.desc())
        .limit(page.page_size)
        .offset(page.offset)
    ).scalars()
    return ok([_partner_privacy_out(r) for r in rows], meta=page_meta(page, total))


# ------------------------------------------------------------------- admin
def _meeting_action(
    db: DbSession, staff: StaffContext, enquiry_id: uuid.UUID, fn: Any
) -> ApiResponse[None]:
    enquiry = admin_service.get_visible(db, staff, enquiry_id, lock=True)
    fn(enquiry)
    db.commit()
    return ok(None, "Meeting request updated")


@admin.post(
    "/meetings/{enquiry_id}/confirm",
    response_model=ApiResponse[None],
    responses=_ERR,
    summary="Confirm after checking real calendar availability",
)
def confirm(
    enquiry_id: uuid.UUID,
    payload: MeetingConfirmIn,
    request: Request,
    staff: AdminDep,
    db: DbSession,
    settings: SettingsDep,
    background: BackgroundTasks,
) -> ApiResponse[None]:
    out = _meeting_action(
        db,
        staff,
        enquiry_id,
        lambda e: service.confirm_meeting(db, staff, e, payload.start, payload.end, payload.note),
    )
    _dispatch(request, settings, background)
    return out


@admin.post("/meetings/{enquiry_id}/decline", response_model=ApiResponse[None], responses=_ERR)
def decline(
    enquiry_id: uuid.UUID,
    payload: ReasonIn,
    request: Request,
    staff: AdminDep,
    db: DbSession,
    settings: SettingsDep,
    background: BackgroundTasks,
) -> ApiResponse[None]:
    out = _meeting_action(
        db, staff, enquiry_id, lambda e: service.decline_meeting(db, staff, e, payload.reason)
    )
    _dispatch(request, settings, background)
    return out


@admin.post("/meetings/{enquiry_id}/cancel", response_model=ApiResponse[None], responses=_ERR)
def cancel(
    enquiry_id: uuid.UUID,
    payload: ReasonIn,
    request: Request,
    staff: AdminDep,
    db: DbSession,
    settings: SettingsDep,
    background: BackgroundTasks,
) -> ApiResponse[None]:
    out = _meeting_action(
        db, staff, enquiry_id, lambda e: service.cancel_meeting(db, staff, e, payload.reason)
    )
    _dispatch(request, settings, background)
    return out


@admin.get(
    "/privacy-requests",
    response_model=ApiResponse[list[PrivacyRequestOut]],
    responses=_ERR,
    summary="Privacy requests (super administrator)",
)
def list_privacy(
    staff: SuperAdminDep,
    db: DbSession,
    page: PageDep,
    status: Annotated[PrivacyRequestStatus | None, Query()] = None,
) -> ApiResponse[list[PrivacyRequestOut]]:
    rows, total = service.list_privacy_requests(db, page.page_size, page.offset, status)
    return ok(
        [PrivacyRequestOut.model_validate(r, from_attributes=True) for r in rows],
        meta=page_meta(page, total),
    )


@admin.post(
    "/privacy-requests/{request_id}", response_model=ApiResponse[PrivacyRequestOut], responses=_ERR
)
def update_privacy(
    request_id: uuid.UUID, payload: PrivacyUpdateIn, staff: SuperAdminDep, db: DbSession
) -> ApiResponse[PrivacyRequestOut]:
    row = service.update_privacy_request(
        db, staff, request_id, payload.status, payload.resolution_note
    )
    return ok(PrivacyRequestOut.model_validate(row, from_attributes=True))


@admin.get(
    "/reports/newsletter.csv",
    responses={**_ERR, 200: {"content": {"text/csv": {}}}},
    summary="Newsletter subscribers (super administrator; audited)",
)
def newsletter_csv(staff: SuperAdminDep, db: DbSession) -> Response:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["email", "status", "consent_at", "consent_notice_version"])
    for s in db.execute(
        select(NewsletterSubscription).order_by(NewsletterSubscription.created_at)
    ).scalars():
        w.writerow(
            [admin_service._safe(s.email), s.status.value, s.consent_at, s.consent_notice_version]
        )  # noqa: SLF001
    log_activity(
        db,
        "report",
        uuid.uuid4(),
        "admin.report_exported",
        {"report": "newsletter"},
        ActorType.STAFF,
        actor_user_id=staff.user.id,
    )
    db.commit()
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="newsletter.csv"',
            "Cache-Control": "private, no-store",
        },
    )


@admin.post(
    "/privacy-requests/{request_id}/execute",
    response_model=ApiResponse[dict[str, int]],
    responses=_ERR,
    summary="Execute an in-progress deletion request (anonymises contact data)",
)
def execute_privacy_deletion(
    request_id: uuid.UUID, staff: SuperAdminDep, db: DbSession
) -> ApiResponse[dict[str, int]]:
    return ok(service.execute_deletion(db, staff, request_id), "Deletion executed")
