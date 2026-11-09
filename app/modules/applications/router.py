import uuid
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy import select

from app.common.responses import ApiResponse, ErrorResponse, ok
from app.core.config import Settings, get_settings
from app.core.protection import rate_limit
from app.database.dependencies import DbSession
from app.modules.applications import service
from app.modules.applications.models import PortalApplication
from app.modules.applications.schemas import (
    ApplicationOut,
    DraftIn,
    DraftUpdate,
    PartnerHistoryItem,
    ReadinessOut,
    WithdrawIn,
    application_out,
    partner_history_item,
)
from app.modules.auth.dependencies import PartnerDep
from app.modules.notifications.service import dispatch_notifications
from app.modules.organizations import service as org_service

router = APIRouter(prefix="/partner/applications", tags=["partner-applications"])
SettingsDep = Annotated[Settings, Depends(get_settings)]
_ERR: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}
ACTION_LIMIT = [Depends(rate_limit("application-action"))]


def _out(db: DbSession, app: PortalApplication) -> ApplicationOut:
    return application_out(app, service.open_request_count(db, app.id))


def _dispatch(request: Request, settings: Settings, background: BackgroundTasks) -> None:
    background.add_task(
        dispatch_notifications,
        request.app.state.sessionmaker,
        request.app.state.email_sender,
        settings,
    )


@router.post(
    "",
    status_code=201,
    response_model=ApiResponse[ApplicationOut],
    dependencies=ACTION_LIMIT,
    responses=_ERR,
    summary="Create a draft application",
)
def create(payload: DraftIn, ctx: PartnerDep, db: DbSession) -> ApiResponse[ApplicationOut]:
    app = service.create_draft(db, ctx, payload.pathway, payload.cover_note)
    return ok(_out(db, app), "Draft created")


@router.get(
    "", response_model=ApiResponse[list[ApplicationOut]], responses=_ERR, summary="Own applications"
)
def list_own(ctx: PartnerDep, db: DbSession) -> ApiResponse[list[ApplicationOut]]:
    apps = db.execute(
        select(PortalApplication)
        .where(PortalApplication.organization_id == ctx.organization_id)
        .order_by(PortalApplication.created_at.desc())
    ).scalars()
    return ok([_out(db, a) for a in apps])


@router.get("/{application_id}", response_model=ApiResponse[ApplicationOut], responses=_ERR)
def get_one(
    application_id: uuid.UUID, ctx: PartnerDep, db: DbSession
) -> ApiResponse[ApplicationOut]:
    return ok(_out(db, service.get_owned(db, ctx.organization_id, application_id)))


@router.patch("/{application_id}", response_model=ApiResponse[ApplicationOut], responses=_ERR)
def update(
    application_id: uuid.UUID, payload: DraftUpdate, ctx: PartnerDep, db: DbSession
) -> ApiResponse[ApplicationOut]:
    app = service.update_draft(
        db, ctx, application_id, pathway=payload.pathway, cover_note=payload.cover_note
    )
    return ok(_out(db, app), "Draft saved")


@router.get("/{application_id}/readiness", response_model=ApiResponse[ReadinessOut], responses=_ERR)
def get_readiness(
    application_id: uuid.UUID, ctx: PartnerDep, db: DbSession
) -> ApiResponse[ReadinessOut]:
    service.get_owned(db, ctx.organization_id, application_id)
    ready = service.readiness(db, org_service.get_organization(db, ctx.organization_id))
    return ok(
        ReadinessOut(
            complete=ready.complete,
            missing_profile_fields=ready.missing_profile_fields,
            missing_document_categories=ready.missing_document_categories,
        )
    )


@router.post(
    "/{application_id}/submit",
    response_model=ApiResponse[ApplicationOut],
    dependencies=ACTION_LIMIT,
    responses=_ERR,
    summary="Submit the draft for review (profile and required documents must be complete)",
)
def submit(
    application_id: uuid.UUID,
    request: Request,
    ctx: PartnerDep,
    db: DbSession,
    settings: SettingsDep,
    background: BackgroundTasks,
) -> ApiResponse[ApplicationOut]:
    app = service.submit(db, settings, ctx, application_id)
    _dispatch(request, settings, background)
    return ok(_out(db, app), "Application submitted")


@router.post(
    "/{application_id}/resubmit",
    response_model=ApiResponse[ApplicationOut],
    dependencies=ACTION_LIMIT,
    responses=_ERR,
    summary="Resubmit after answering every information request",
)
def resubmit(
    application_id: uuid.UUID,
    request: Request,
    ctx: PartnerDep,
    db: DbSession,
    settings: SettingsDep,
    background: BackgroundTasks,
) -> ApiResponse[ApplicationOut]:
    app = service.resubmit(db, settings, ctx, application_id)
    _dispatch(request, settings, background)
    return ok(_out(db, app), "Application resubmitted")


@router.post(
    "/{application_id}/withdraw",
    response_model=ApiResponse[ApplicationOut],
    dependencies=ACTION_LIMIT,
    responses=_ERR,
)
def withdraw(
    application_id: uuid.UUID,
    payload: WithdrawIn,
    request: Request,
    ctx: PartnerDep,
    db: DbSession,
    settings: SettingsDep,
    background: BackgroundTasks,
) -> ApiResponse[ApplicationOut]:
    app = service.withdraw(db, settings, ctx, application_id, payload.note)
    _dispatch(request, settings, background)
    return ok(_out(db, app), "Application withdrawn")


@router.get(
    "/{application_id}/history",
    response_model=ApiResponse[list[PartnerHistoryItem]],
    responses=_ERR,
    summary="Status history (partner-visible fields only)",
)
def history(
    application_id: uuid.UUID, ctx: PartnerDep, db: DbSession
) -> ApiResponse[list[PartnerHistoryItem]]:
    service.get_owned(db, ctx.organization_id, application_id)
    return ok([partner_history_item(h) for h in service.partner_history(db, application_id)])
