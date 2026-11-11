import uuid
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel, ConfigDict

from app.common.responses import ApiResponse, ErrorResponse, ok
from app.common.utilities import utcnow
from app.common.validation import Long
from app.core.config import Settings, get_settings
from app.core.protection import rate_limit
from app.database.dependencies import DbSession
from app.modules.applications import service as app_service
from app.modules.applications.models import ApplicationMessage
from app.modules.auth.dependencies import PartnerDep
from app.modules.messaging import service
from app.modules.notifications.service import dispatch_notifications

router = APIRouter(prefix="/partner/applications", tags=["partner-messages"])
_ERR: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


class RespondIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    in_reply_to: uuid.UUID
    body: Long


class PartnerMessageOut(BaseModel):
    """Reviewer identity is not exposed to partners."""

    id: uuid.UUID
    kind: str
    status: str | None
    from_reviewer: bool
    body: str
    requested_categories: list[str] | None
    in_reply_to: uuid.UUID | None
    created_at: datetime
    due_date: date | None = None
    is_overdue: bool = False


def partner_message(m: ApplicationMessage) -> PartnerMessageOut:
    return PartnerMessageOut(
        id=m.id,
        kind=m.kind.value,
        status=m.status.value if m.status else None,
        from_reviewer=m.kind.value == "information_request",
        body=m.body,
        requested_categories=m.requested_categories,
        in_reply_to=m.in_reply_to_id,
        created_at=m.created_at,
        due_date=m.due_date,
        is_overdue=bool(
            m.due_date
            and m.status is not None
            and m.status.value == "open"
            and m.due_date < utcnow().date()
        ),
    )


@router.get(
    "/{application_id}/messages",
    response_model=ApiResponse[list[PartnerMessageOut]],
    responses=_ERR,
    summary="Partner-visible messages (information requests and your responses)",
)
def list_messages(
    application_id: uuid.UUID, ctx: PartnerDep, db: DbSession
) -> ApiResponse[list[PartnerMessageOut]]:
    app_service.get_owned(db, ctx.organization_id, application_id)
    return ok([partner_message(m) for m in service.list_messages(db, application_id)])


@router.post(
    "/{application_id}/messages",
    status_code=201,
    response_model=ApiResponse[PartnerMessageOut],
    dependencies=[Depends(rate_limit("application-action"))],
    responses=_ERR,
    summary="Respond to an open information request",
)
def respond(
    application_id: uuid.UUID,
    payload: RespondIn,
    request: Request,
    ctx: PartnerDep,
    db: DbSession,
    settings: Annotated[Settings, Depends(get_settings)],
    background: BackgroundTasks,
) -> ApiResponse[PartnerMessageOut]:
    reply = service.respond(db, settings, ctx, application_id, payload.in_reply_to, payload.body)
    background.add_task(
        dispatch_notifications,
        request.app.state.sessionmaker,
        request.app.state.email_sender,
        settings,
    )
    return ok(partner_message(reply), "Response sent")
