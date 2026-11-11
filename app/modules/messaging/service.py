"""Partner-visible conversation tied to an application. Internal reviewer notes live elsewhere."""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.utilities import utcnow
from app.core.config import Settings
from app.core.exceptions import AppError, NotFoundError
from app.modules.applications import service as app_service
from app.modules.applications.constants import MessageKind, MessageStatus, PortalStatus
from app.modules.applications.models import ApplicationMessage, PortalApplication
from app.modules.applications.transitions import Actor
from app.modules.auth.dependencies import PartnerContext, StaffContext
from app.modules.enquiries.activity import log_activity
from app.modules.enquiries.constants import ActorType
from app.modules.notifications.constants import NotificationType, TemplateKey
from app.modules.notifications.service import queue_notification
from app.modules.partner_documents.constants import PartnerDocCategory


def create_information_request(
    db: Session,
    settings: Settings,
    staff: StaffContext,
    app: PortalApplication,
    body: str,
    categories: list[PartnerDocCategory],
    due_date: date | None = None,
) -> ApplicationMessage:
    """Caller holds the application row lock. Moves the application to information_requested."""
    app_service.transition(
        db,
        settings,
        app=app,
        target=PortalStatus.INFORMATION_REQUESTED,
        actor=Actor.REVIEWER,
        user=staff.user,
        reason="Information requested",
        partner_note="Additional information requested",
        dedicated=True,
    )
    message = ApplicationMessage(
        application_id=app.id,
        kind=MessageKind.INFORMATION_REQUEST,
        status=MessageStatus.OPEN,
        author_user_id=staff.user.id,
        body=body,
        requested_categories=[c.value for c in categories] or None,
        due_date=due_date,
        created_at=utcnow(),
    )
    db.add(message)
    db.flush()
    log_activity(
        db,
        "portal_application",
        app.id,
        "application.information_requested",
        {"message_id": str(message.id), "categories": [c.value for c in categories]},
        ActorType.REVIEWER,
        actor_user_id=staff.user.id,
        organization_id=app.organization_id,
    )
    for u in app_service.partner_users(db, app.organization_id):
        queue_notification(
            db,
            recipient=u.email,
            kind=NotificationType.APPLICATION,
            template=TemplateKey.INFORMATION_REQUESTED,
            context={"reference": app.reference, "name": u.full_name},
            dedupe_key=f"info-request:{message.id}:{u.id}",
        )
    return message


def respond(
    db: Session,
    settings: Settings,
    ctx: PartnerContext,
    application_id: uuid.UUID,
    in_reply_to: uuid.UUID,
    body: str,
) -> ApplicationMessage:
    app = app_service.lock_application(db, application_id, ctx.organization_id)
    request = db.execute(
        select(ApplicationMessage)
        .where(
            ApplicationMessage.id == in_reply_to,
            ApplicationMessage.application_id == app.id,
            ApplicationMessage.kind == MessageKind.INFORMATION_REQUEST,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if request is None:
        raise NotFoundError("Information request not found")
    if (
        request.status is not MessageStatus.OPEN
        or app.status is not PortalStatus.INFORMATION_REQUESTED
    ):
        raise AppError("This request is not open", status_code=409, code="REQUEST_NOT_OPEN")
    now = utcnow()
    request.status = MessageStatus.ANSWERED
    request.answered_at = now
    reply = ApplicationMessage(
        application_id=app.id,
        kind=MessageKind.PARTNER_RESPONSE,
        author_user_id=ctx.user.id,
        body=body,
        in_reply_to_id=request.id,
        created_at=now,
    )
    db.add(reply)
    db.flush()
    log_activity(
        db,
        "portal_application",
        app.id,
        "application.partner_responded",
        {"message_id": str(reply.id), "in_reply_to": str(request.id)},
        ActorType.PARTNER,
        actor_user_id=ctx.user.id,
        organization_id=ctx.organization_id,
    )
    for address in app_service._internal_recipients(db, settings, app):  # noqa: SLF001
        queue_notification(
            db,
            recipient=address,
            kind=NotificationType.INTERNAL,
            template=TemplateKey.PARTNER_RESPONSE_RECEIVED,
            context={"reference": app.reference},
            dedupe_key=f"partner-response:{reply.id}:{address.lower()}",
        )
    db.commit()
    return reply


def list_messages(db: Session, application_id: uuid.UUID) -> list[ApplicationMessage]:
    return list(
        db.execute(
            select(ApplicationMessage)
            .where(ApplicationMessage.application_id == application_id)
            .order_by(ApplicationMessage.created_at)
        ).scalars()
    )
