"""Email provider event webhook (bounces, complaints). Disabled until EMAIL_WEBHOOK_SECRET is set.

Payload shape follows common provider webhooks (`event`, `email`); it has NOT been verified against
a live provider. Only the shared secret authenticates the caller, so it must be long and random."""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.common.responses import ApiResponse, ErrorResponse, ok
from app.core.config import Settings, get_settings
from app.core.exceptions import AppError
from app.core.protection import rate_limit
from app.core.security import constant_time_equals
from app.database.dependencies import DbSession
from app.modules.enquiries.activity import log_activity
from app.modules.enquiries.constants import ActorType
from app.modules.notifications.constants import DeliveryStatus
from app.modules.notifications.models import Notification

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
SettingsDep = Annotated[Settings, Depends(get_settings)]
_ERR: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
}


class EmailEventIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event: Literal["hard_bounce", "soft_bounce", "complaint", "delivered"]
    email: str


@router.post(
    "/email",
    dependencies=[Depends(rate_limit("auth"))],
    response_model=ApiResponse[dict[str, int]],
    responses=_ERR,
    summary="Provider delivery event; header X-Webhook-Secret required (404 while disabled)",
)
def email_event(
    payload: EmailEventIn,
    db: DbSession,
    settings: SettingsDep,
    x_webhook_secret: Annotated[str | None, Header()] = None,
) -> ApiResponse[dict[str, int]]:
    secret = settings.email_webhook_secret
    if secret is None:
        raise AppError("Not found", status_code=404, code="NOT_FOUND")
    if not x_webhook_secret or not constant_time_equals(
        x_webhook_secret, secret.get_secret_value()
    ):
        raise AppError("Invalid webhook secret", status_code=401, code="UNAUTHENTICATED")
    if payload.event == "delivered":
        return ok({"updated": 0})
    latest = db.execute(
        select(Notification)
        .where(
            Notification.recipient == payload.email.strip().lower(),
            Notification.delivery_status == DeliveryStatus.SENT,
        )
        .order_by(Notification.created_at.desc())
        .limit(1)
        .with_for_update()
    ).scalar_one_or_none()
    if latest is None:
        return ok({"updated": 0})
    latest.delivery_status = DeliveryStatus.BOUNCED
    log_activity(
        db,
        "notification",
        latest.id,
        "notification.bounced",
        {"event": payload.event},
        ActorType.SYSTEM,
    )
    db.commit()
    return ok({"updated": 1})
