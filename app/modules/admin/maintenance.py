"""Scheduled maintenance (run by scripts/run_maintenance.py, e.g. from cron).

Each job is idempotent and inert until the business sets the matching system setting:
* expiry reminders  (setting expiry_reminder_days)       - PRD s.13 expiry tracking
* retention purge   (setting retention.partner_document_days) - PRD s.13/s.19 retention, deletion
* idempotency-key cleanup, notification retry dispatch.
"""

import logging
from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy import Row, Select, and_, func, or_, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.common import idempotency
from app.common.utilities import utcnow
from app.core.config import Settings
from app.integrations.email import EmailSender
from app.integrations.storage import Storage, StorageError
from app.modules.admin import settings_service as cfg
from app.modules.applications.service import partner_users
from app.modules.content import service as content_service
from app.modules.content.constants import ContentStatus
from app.modules.content.models import ContentItem
from app.modules.documents.constants import attachable_statuses
from app.modules.enquiries.activity import log_activity
from app.modules.enquiries.constants import ActorType, EnquiryStatus
from app.modules.enquiries.models import Enquiry
from app.modules.enquiries.routing import DEFAULT_ESCALATION_HOURS
from app.modules.notifications.constants import DeliveryStatus, NotificationType, TemplateKey
from app.modules.notifications.models import Notification
from app.modules.notifications.service import dispatch_notifications, queue_notification
from app.modules.partner_documents.constants import DocStatus
from app.modules.partner_documents.models import PartnerDocument, PartnerDocumentVersion

logger = logging.getLogger("app.maintenance")


def _expiring(db: Session, days: int) -> Sequence[Row[PartnerDocument, PartnerDocumentVersion]]:
    today = utcnow().date()
    return db.execute(
        select(PartnerDocument, PartnerDocumentVersion)
        .join(
            PartnerDocumentVersion,
            (PartnerDocumentVersion.document_id == PartnerDocument.id)
            & (PartnerDocumentVersion.version_no == PartnerDocument.current_version_no),
        )
        .where(
            PartnerDocument.status == DocStatus.ACTIVE,
            PartnerDocumentVersion.upload_status.in_(attachable_statuses()),
            PartnerDocumentVersion.expires_on.is_not(None),
            PartnerDocumentVersion.expires_on >= today,
            PartnerDocumentVersion.expires_on <= today + timedelta(days=days),
        )
    ).all()


def send_expiry_reminders(db: Session) -> int:
    days = cfg.get_int(db, "expiry_reminder_days")
    if not days:
        return 0
    rows = _expiring(db, days)
    queued = 0
    for doc, ver in rows:
        for user in partner_users(db, doc.organization_id):
            queue_notification(
                db,
                recipient=user.email,
                kind=NotificationType.APPLICATION,
                template=TemplateKey.EXPIRY_REMINDER,
                context={
                    "name": user.full_name,
                    "category": doc.category.value,
                    "expires_on": ver.expires_on.isoformat() if ver.expires_on else "",
                },
                dedupe_key=f"expiry:{ver.id}:{user.id}",  # one reminder per version and user
            )
            queued += 1
    db.commit()
    return queued


def _overdue(db: Session) -> Select[Enquiry]:
    """Enquiries still without a first response after their queue's ESCALATION target
    (default 48 h, setting `sla_escalation.<queue>`; the 24 h first-response target only sets
    `response_due_at`). Counted from creation."""
    now = utcnow()
    per_queue = [
        and_(
            Enquiry.enquiry_type == queue,
            Enquiry.created_at
            < now
            - timedelta(
                hours=cfg.get_int(db, f"sla_escalation.{queue}") or DEFAULT_ESCALATION_HOURS
            ),
        )
        for queue in cfg.QUEUES
    ]
    return select(Enquiry).where(
        or_(*per_queue),
        Enquiry.first_response_at.is_(None),
        Enquiry.escalated_at.is_(None),
        Enquiry.status != EnquiryStatus.CLOSED,
    )


def escalate_overdue(db: Session, settings: Settings) -> int:
    """Tell the escalation contact once when a first-response target is missed (PRD s.28)."""
    rows = db.execute(_overdue(db).with_for_update(skip_locked=True)).scalars().all()
    for e in rows:
        queue = e.enquiry_type.value
        fallback = {
            "general": settings.notify_general_emails,
            "meeting": settings.notify_general_emails,
            "project": settings.notify_project_emails,
            "partner": settings.notify_partner_emails,
            "strategic": settings.notify_strategic_emails,
        }[queue]
        configured = cfg.get(db, f"escalation.email.{queue}")
        for address in [configured] if configured else fallback:
            queue_notification(
                db,
                recipient=address,
                kind=NotificationType.INTERNAL,
                template=TemplateKey.SLA_ESCALATION,
                context={"reference": e.reference_number, "enquiry_type": queue},
                dedupe_key=f"sla:{e.id}:{address.lower()}",
            )
        e.escalated_at = utcnow()
        log_activity(db, "enquiry", e.id, "system.sla_escalated", {"type": queue}, ActorType.SYSTEM)
    db.commit()
    return len(rows)


def _purgeable() -> Select[PartnerDocumentVersion]:
    return (
        select(PartnerDocumentVersion)
        .join(PartnerDocument, PartnerDocument.id == PartnerDocumentVersion.document_id)
        .where(
            PartnerDocument.status == DocStatus.REMOVED,
            PartnerDocumentVersion.retention_date < utcnow(),
            PartnerDocumentVersion.purged_at.is_(None),
        )
    )


def purge_retained(db: Session, storage: Storage) -> int:
    """Delete blobs of removed documents whose retention date has passed. Rows are kept (audit)."""
    rows = db.execute(_purgeable().with_for_update(skip_locked=True)).scalars().all()
    purged = 0
    for ver in rows:
        try:
            storage.delete(ver.storage_key)
        except StorageError:
            logger.error("retention purge failed", extra={"version_id": str(ver.id)})
            continue
        ver.purged_at = utcnow()
        log_activity(
            db,
            "partner_document",
            ver.document_id,
            "document.purged",
            {"version": ver.version_no},
            ActorType.SYSTEM,
        )
        purged += 1
    db.commit()
    return purged


def publish_scheduled_content(db: Session) -> int:
    now = utcnow()
    rows = db.execute(
        select(ContentItem)
        .where(
            ContentItem.status == ContentStatus.APPROVED,
            ContentItem.scheduled_publish_at <= now,
        )
        .order_by(ContentItem.scheduled_publish_at, ContentItem.id)
        .limit(100)
        .with_for_update(skip_locked=True)
    ).scalars()
    published = 0
    for item in rows:
        if content_service.claim_problems(db, item):
            continue
        item.status = ContentStatus.PUBLISHED
        item.published_at = now
        item.scheduled_publish_at = None
        log_activity(
            db, "content", item.id, "content.published", {"slug": item.slug}, ActorType.SYSTEM
        )
        published += 1
    db.commit()
    return published


def scheduled_content_due(db: Session) -> int:
    now = utcnow()
    rows = db.execute(
        select(ContentItem).where(
            ContentItem.status == ContentStatus.APPROVED,
            ContentItem.scheduled_publish_at <= now,
        )
    ).scalars()
    return sum(1 for item in rows if not content_service.claim_problems(db, item))


def run_all(
    factory: sessionmaker[Session], settings: Settings, storage: Storage, sender: EmailSender
) -> dict[str, int]:
    with factory() as db:
        result = {"idempotency_purged": idempotency.purge_expired(db)}
    with factory() as db:
        result["sla_escalations"] = escalate_overdue(db, settings)
    with factory() as db:
        result["expiry_reminders_queued"] = send_expiry_reminders(db)
    with factory() as db:
        result["documents_purged"] = purge_retained(db, storage)
    with factory() as db:
        result["content_published"] = publish_scheduled_content(db)
    result["notifications_dispatched"] = dispatch_notifications(factory, sender, settings)
    return result


def preview(factory: sessionmaker[Session], settings: Settings) -> dict[str, int]:
    """Dry run: count what run_all would act on. One READ ONLY transaction, so the database
    itself rejects any write; nothing is deleted, modified, queued or sent."""
    with factory() as db:
        db.execute(text("SET LOCAL transaction_read_only = on"))
        days = cfg.get_int(db, "expiry_reminder_days")
        reminders = 0
        if days:
            for doc, _ver in _expiring(db, days):
                reminders += len(partner_users(db, doc.organization_id))
        result = {
            "idempotency_would_purge": int(
                db.scalar(
                    select(func.count())
                    .select_from(idempotency.IdempotencyKey)
                    .where(idempotency.IdempotencyKey.expires_at <= utcnow())
                )
                or 0
            ),
            "sla_would_escalate": len(db.execute(_overdue(db)).scalars().all()),
            "expiry_reminders_would_queue": reminders,
            "documents_would_purge": len(db.execute(_purgeable()).scalars().all()),
            "content_would_publish": scheduled_content_due(db),
            "notifications_would_dispatch": int(
                db.scalar(
                    select(func.count())
                    .select_from(Notification)
                    .where(
                        Notification.delivery_status.in_(
                            [DeliveryStatus.PENDING, DeliveryStatus.FAILED]
                        ),
                        Notification.retry_count < settings.notification_max_retries,
                    )
                )
                or 0
            ),
        }
        db.rollback()
    return result
