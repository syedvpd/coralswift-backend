"""Outbox pattern: rows are written in the enquiry transaction; sending happens after commit."""

import logging
import uuid
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.common.utilities import utcnow
from app.core.config import Settings
from app.integrations.email import EmailDeliveryError, EmailMessage, EmailSender
from app.modules.admin.models import NotificationTemplate
from app.modules.enquiries.activity import log_activity
from app.modules.enquiries.constants import ActorType, EnquiryType
from app.modules.notifications import preferences
from app.modules.notifications.constants import DeliveryStatus, NotificationType, TemplateKey
from app.modules.notifications.models import Notification
from app.modules.notifications.templates import render, render_override

logger = logging.getLogger("app.notifications")

SENSITIVE_CONTEXT_KEYS = {"link"}

ACK_TEMPLATE = {
    EnquiryType.GENERAL: TemplateKey.ACK_GENERAL,
    EnquiryType.PROJECT: TemplateKey.ACK_PROJECT,
    EnquiryType.PARTNER: TemplateKey.ACK_PARTNER,
    EnquiryType.STRATEGIC: TemplateKey.ACK_STRATEGIC,
    EnquiryType.MEETING: TemplateKey.ACK_MEETING,
}


def _internal_recipients(settings: Settings, enquiry_type: EnquiryType) -> list[str]:
    return {
        EnquiryType.GENERAL: settings.notify_general_emails,
        EnquiryType.PROJECT: settings.notify_project_emails,
        EnquiryType.PARTNER: settings.notify_partner_emails,
        EnquiryType.STRATEGIC: settings.notify_strategic_emails,
        EnquiryType.MEETING: settings.notify_general_emails,
    }[enquiry_type]


def queue_notification(
    db: Session,
    *,
    recipient: str,
    kind: NotificationType,
    template: TemplateKey,
    context: dict[str, str],
    enquiry_id: uuid.UUID | None = None,
    dedupe_key: str | None = None,
) -> None:
    """Insert an outbox row; ON CONFLICT DO NOTHING on dedupe_key so a re-run never duplicates."""
    key = dedupe_key or f"{enquiry_id}:{template.value}:{recipient.lower()}"
    if preferences.is_muted(db, recipient, kind):
        return  # the partner opted out of this optional category
    db.execute(
        pg_insert(Notification)
        .values(
            id=uuid.uuid4(),
            enquiry_id=enquiry_id,
            recipient=recipient.lower(),
            notification_type=kind,
            template_key=template,
            context=context,
            delivery_status=DeliveryStatus.PENDING,
            retry_count=0,
            dedupe_key=key,
        )
        .on_conflict_do_nothing(index_elements=["dedupe_key"])
    )


def _queue(
    db: Session,
    *,
    enquiry_id: uuid.UUID,
    recipient: str,
    kind: NotificationType,
    template: TemplateKey,
    context: dict[str, str],
) -> None:
    queue_notification(
        db,
        recipient=recipient,
        kind=kind,
        template=template,
        context=context,
        enquiry_id=enquiry_id,
    )


def queue_submission_notifications(
    db: Session,
    settings: Settings,
    *,
    enquiry_id: uuid.UUID,
    enquiry_type: EnquiryType,
    reference: str,
    submitter_email: str,
    submitter_name: str,
    company: str | None,
    response_hours: int | None = None,
) -> None:
    base = {"reference": reference, "enquiry_type": enquiry_type.value}
    if response_hours:  # only when the business enabled acknowledgement promises (PRD s.28)
        base["response_hours"] = str(response_hours)
    _queue(
        db,
        enquiry_id=enquiry_id,
        recipient=submitter_email,
        kind=NotificationType.ACKNOWLEDGEMENT,
        template=ACK_TEMPLATE[enquiry_type],
        context={**base, "name": submitter_name},
    )
    internal_ctx = dict(base)
    if enquiry_type is not EnquiryType.STRATEGIC:
        internal_ctx["name"] = submitter_name
        if company:
            internal_ctx["company"] = company
    for address in _internal_recipients(settings, enquiry_type):
        _queue(
            db,
            enquiry_id=enquiry_id,
            recipient=address,
            kind=NotificationType.INTERNAL,
            template=TemplateKey.INTERNAL_NEW_ENQUIRY,
            context=internal_ctx,
        )


def dispatch_notifications(
    session_factory: Callable[[], Session],
    sender: EmailSender,
    settings: Settings,
    enquiry_id: uuid.UUID | None = None,
    limit: int = 50,
) -> int:
    """Send pending/failed rows (retry cap applies). Safe to run concurrently: rows are locked
    with SKIP LOCKED and committed one by one. Returns the number of rows processed."""
    processed = 0
    attempted: set[uuid.UUID] = set()  # each row is tried at most once per run
    while processed < limit:
        db = session_factory()
        try:
            stmt = (
                select(Notification)
                .where(
                    Notification.delivery_status.in_(
                        [DeliveryStatus.PENDING, DeliveryStatus.FAILED]
                    ),
                    Notification.retry_count < settings.notification_max_retries,
                )
                .order_by(Notification.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if enquiry_id:
                stmt = stmt.where(Notification.enquiry_id == enquiry_id)
            if attempted:
                stmt = stmt.where(Notification.id.not_in(attempted))
            row = db.execute(stmt).scalar_one_or_none()
            if row is None:
                return processed
            attempted.add(row.id)
            _send_one(db, sender, row)
            db.commit()
            processed += 1
        except Exception:
            db.rollback()
            logger.exception("notification dispatch crashed")
            return processed
        finally:
            db.close()
    return processed


def render_with_override(
    db: Session, key: TemplateKey, ctx: dict[str, str]
) -> tuple[str, str, str]:
    """Staff-edited template (PRD s.14) if one is stored, else the built-in."""
    custom = db.get(NotificationTemplate, key.value)
    if custom is None:
        return render(key, ctx)
    return render_override(custom.subject, custom.text_body, custom.html_body, ctx)


def _send_one(db: Session, sender: EmailSender, row: Notification) -> None:
    try:
        subject, text, html = render_with_override(db, row.template_key, row.context)
        result = sender.send(EmailMessage(to=row.recipient, subject=subject, html=html, text=text))
    except EmailDeliveryError as exc:
        row.retry_count += 1
        row.delivery_status = DeliveryStatus.FAILED
        row.last_error = str(exc)[:300]
        logger.error(
            "notification failed",
            extra={"notification_id": str(row.id), "retry_count": row.retry_count},
        )
        action = "notification.failed"
    else:
        row.delivery_status = DeliveryStatus.SENT if result.delivered else DeliveryStatus.LOGGED
        row.provider_reference = result.provider_reference
        row.sent_at = utcnow()
        row.last_error = None
        # One-time links must not outlive the delivery attempt in the outbox.
        row.context = {k: v for k, v in row.context.items() if k not in SENSITIVE_CONTEXT_KEYS}
        action = "notification.sent" if result.delivered else "notification.logged"
    log_activity(db, "notification", row.id, action, actor=ActorType.SYSTEM)
