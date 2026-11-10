import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.common.utilities import utcnow
from app.core.config import Settings
from app.core.exceptions import AppError, NotFoundError
from app.modules.auth.dependencies import StaffContext
from app.modules.auth.security import hash_token, new_token
from app.modules.engagement.models import (
    MeetingRequest,
    MeetingStatus,
    NewsletterSubscription,
    PrivacyRequest,
    PrivacyRequestKind,
    PrivacyRequestStatus,
    SubscriptionStatus,
)
from app.modules.engagement.schemas import MeetingRequestIn
from app.modules.enquiries.activity import log_activity
from app.modules.enquiries.constants import ActorType, EnquiryStatus, EnquiryType
from app.modules.enquiries.models import Contact, Enquiry
from app.modules.enquiries.service import Created, create_enquiry
from app.modules.notifications.constants import NotificationType, TemplateKey
from app.modules.notifications.models import Notification
from app.modules.notifications.service import queue_notification


# ----------------------------------------------------------------- meetings
def create_meeting_request(db: Session, settings: Settings, data: MeetingRequestIn) -> Created:
    created = create_enquiry(
        db,
        settings,
        enquiry_type=EnquiryType.MEETING,
        submitter=data,
        company=None,
        subject="Meeting request",
        message=None,
    )
    db.add(
        MeetingRequest(
            enquiry_id=created.enquiry.id,
            purpose=data.purpose,
            preferred_slots=[
                {"start": s.start.isoformat(), "end": s.end.isoformat()}
                for s in data.preferred_slots
            ],
            timezone=data.timezone,
        )
    )
    return created


def _meeting(db: Session, enquiry: Enquiry) -> MeetingRequest:
    m = db.execute(
        select(MeetingRequest).where(MeetingRequest.enquiry_id == enquiry.id).with_for_update()
    ).scalar_one_or_none()
    if m is None:
        raise NotFoundError("Meeting request not found")
    return m


def _notify_requester(
    db: Session, enquiry: Enquiry, label: str, meeting_time: str | None, tz: str
) -> None:
    contact = db.get(Contact, enquiry.contact_id)
    if contact is None:
        return
    ctx = {"reference": enquiry.reference_number, "name": contact.full_name, "status_label": label}
    if meeting_time:
        ctx["meeting_time"] = meeting_time
    queue_notification(
        db,
        recipient=contact.business_email,
        kind=NotificationType.ACKNOWLEDGEMENT,
        template=TemplateKey.MEETING_DECISION,
        context=ctx,
        dedupe_key=f"meeting-{label.lower()}:{enquiry.id}:{utcnow().isoformat()}",
    )


def _decide(
    db: Session,
    staff: StaffContext,
    enquiry: Enquiry,
    status: MeetingStatus,
    note: str | None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> MeetingRequest:
    m = _meeting(db, enquiry)
    if m.status in (MeetingStatus.DECLINED, MeetingStatus.CANCELLED):
        raise AppError(
            "This meeting request is already closed", status_code=409, code="INVALID_TRANSITION"
        )
    if status is MeetingStatus.CONFIRMED and m.status is MeetingStatus.CONFIRMED:
        raise AppError("Already confirmed", status_code=409, code="INVALID_TRANSITION")
    m.status, m.decided_by, m.decided_at, m.decision_note = status, staff.user.id, utcnow(), note
    if status is MeetingStatus.CONFIRMED:
        m.calendar_checked, m.confirmed_start, m.confirmed_end = True, start, end
    if enquiry.status is EnquiryStatus.RECEIVED:
        enquiry.status = EnquiryStatus.IN_REVIEW
    label = {"confirmed": "Confirmed", "declined": "Declined", "cancelled": "Cancelled"}[
        status.value
    ]
    when = None
    if start and end:
        zone = ZoneInfo(m.timezone)
        when = f"{start.astimezone(zone):%Y-%m-%d %H:%M} - {end.astimezone(zone):%H:%M %Z}"
    _notify_requester(db, enquiry, label, when, m.timezone)
    log_activity(
        db,
        "enquiry",
        enquiry.id,
        f"admin.meeting_{status.value}",
        {"calendar_checked": m.calendar_checked},
        ActorType.STAFF,
        actor_user_id=staff.user.id,
    )
    return m


def confirm_meeting(
    db: Session,
    staff: StaffContext,
    enquiry: Enquiry,
    start: datetime,
    end: datetime,
    note: str | None,
) -> MeetingRequest:
    """Staff attest they checked real calendar availability (no calendar integration)."""
    return _decide(db, staff, enquiry, MeetingStatus.CONFIRMED, note, start, end)


def decline_meeting(
    db: Session, staff: StaffContext, enquiry: Enquiry, reason: str
) -> MeetingRequest:
    return _decide(db, staff, enquiry, MeetingStatus.DECLINED, reason)


def cancel_meeting(
    db: Session, staff: StaffContext, enquiry: Enquiry, reason: str
) -> MeetingRequest:
    return _decide(db, staff, enquiry, MeetingStatus.CANCELLED, reason)


# --------------------------------------------------------------- newsletter
def newsletter_token(settings: Settings, email: str) -> str:
    mac = hmac.new(
        settings.secret_key.get_secret_value().encode(),
        f"newsletter:{email}".encode(),
        hashlib.sha256,
    )
    return mac.hexdigest()[:32]


def subscribe(db: Session, settings: Settings, email: str) -> str:
    email = email.strip().lower()
    now = utcnow()
    row = db.execute(
        select(NewsletterSubscription)
        .where(NewsletterSubscription.email == email)
        .with_for_update()
    ).scalar_one_or_none()
    if row is None:
        db.add(
            NewsletterSubscription(
                email=email, consent_at=now, consent_notice_version=settings.privacy_notice_version
            )
        )
    else:
        row.status, row.consent_at, row.unsubscribed_at = SubscriptionStatus.SUBSCRIBED, now, None
        row.consent_notice_version = settings.privacy_notice_version
    db.commit()
    return newsletter_token(settings, email)


def unsubscribe(db: Session, settings: Settings, email: str, token: str) -> None:
    email = email.strip().lower()
    if not hmac.compare_digest(newsletter_token(settings, email), token):
        raise NotFoundError("Subscription not found")
    row = db.execute(
        select(NewsletterSubscription)
        .where(NewsletterSubscription.email == email)
        .with_for_update()
    ).scalar_one_or_none()
    if row is not None and row.status is SubscriptionStatus.SUBSCRIBED:
        row.status, row.unsubscribed_at = SubscriptionStatus.UNSUBSCRIBED, utcnow()
    db.commit()


# ---------------------------------------------------------- privacy requests
PRIVACY_VERIFY_HOURS = 72  # shortcut: fixed window; make it a setting if the owner wants another


def create_privacy_request(
    db: Session,
    settings: Settings,
    email: str,
    kind: PrivacyRequestKind,
    details: str | None,
    *,
    submitted_by: uuid.UUID | None = None,
) -> PrivacyRequest:
    """Public requests must confirm the address by email link; a signed-in partner is already
    identified by the session, so the request is verified at creation."""
    row = PrivacyRequest(
        reference="PR-" + secrets.token_hex(5).upper(),
        email=email.strip().lower(),
        kind=kind,
        details=details,
        submitted_by_user_id=submitted_by,
    )
    context = {"reference": row.reference}
    if submitted_by is not None:
        row.email_verified_at = utcnow()
    else:
        raw = new_token()
        row.verification_token_hash = hash_token(raw)
        row.verification_expires_at = utcnow() + timedelta(hours=PRIVACY_VERIFY_HOURS)
        context["link"] = f"{settings.portal_base_url.rstrip('/')}/privacy/verify?token={raw}"
    db.add(row)
    db.flush()
    queue_notification(
        db,
        recipient=row.email,
        kind=NotificationType.ACKNOWLEDGEMENT,
        template=TemplateKey.PRIVACY_REQUEST_ACK,
        context=context,
        dedupe_key=f"privacy-ack:{row.id}",
    )
    for address in settings.notify_general_emails:
        queue_notification(
            db,
            recipient=address,
            kind=NotificationType.INTERNAL,
            template=TemplateKey.PRIVACY_REQUEST_ACK,
            context={"reference": row.reference},
            dedupe_key=f"privacy-internal:{row.id}:{address.lower()}",
        )
    log_activity(db, "privacy_request", row.id, "privacy.request_received", {"kind": kind.value})
    db.commit()
    return row


def verify_privacy_email(db: Session, token: str) -> PrivacyRequest:
    row = db.execute(
        select(PrivacyRequest)
        .where(PrivacyRequest.verification_token_hash == hash_token(token))
        .with_for_update()
    ).scalar_one_or_none()
    if row is None:
        raise AppError("Invalid or expired link", status_code=400, code="INVALID_OR_EXPIRED_TOKEN")
    if row.verification_expires_at is None or row.verification_expires_at <= utcnow():
        raise AppError("This link has expired", status_code=400, code="TOKEN_EXPIRED")
    row.email_verified_at = utcnow()
    row.verification_token_hash = None  # single use
    row.verification_expires_at = None
    log_activity(db, "privacy_request", row.id, "privacy.email_verified", {})
    db.commit()
    return row


def _require_verified(row: PrivacyRequest) -> None:
    if row.email_verified_at is None:
        raise AppError(
            "The requester has not confirmed their email address yet",
            status_code=409,
            code="EMAIL_NOT_VERIFIED",
        )


def list_privacy_requests(
    db: Session, limit: int, offset: int, status: PrivacyRequestStatus | None
) -> tuple[list[PrivacyRequest], int]:
    stmt = select(PrivacyRequest)
    if status:
        stmt = stmt.where(PrivacyRequest.status == status)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(PrivacyRequest.created_at.desc(), PrivacyRequest.id.desc())
        .limit(limit)
        .offset(offset)
    ).scalars()
    return list(rows), total


def update_privacy_request(
    db: Session,
    staff: StaffContext,
    request_id: uuid.UUID,
    status: PrivacyRequestStatus,
    note: str | None,
) -> PrivacyRequest:
    row = db.execute(
        select(PrivacyRequest).where(PrivacyRequest.id == request_id).with_for_update()
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("Request not found")
    if status is not PrivacyRequestStatus.REJECTED:  # an unverified request may only be rejected
        _require_verified(row)
    row.status, row.resolution_note, row.handled_by = status, note, staff.user.id
    log_activity(
        db,
        "privacy_request",
        row.id,
        "admin.privacy_request_updated",
        {"status": status.value},
        ActorType.STAFF,
        actor_user_id=staff.user.id,
    )
    db.commit()
    return row


def execute_deletion(db: Session, staff: StaffContext, request_id: uuid.UUID) -> dict[str, int]:
    """Carry out an in-progress deletion request (PRD s.19 secure deletion / s.28 retention).

    Anonymises the person's contact records and outbox addresses and removes the newsletter row.
    Business records (enquiry text, documents, audit trail) are kept: whether they must be erased
    depends on the retention policy, which the business has not approved. Staff review those
    manually; the counts returned show what was changed.
    """
    row = db.execute(
        select(PrivacyRequest).where(PrivacyRequest.id == request_id).with_for_update()
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("Request not found")
    _require_verified(row)
    if (
        row.kind is not PrivacyRequestKind.DELETION
        or row.status is not PrivacyRequestStatus.IN_PROGRESS
    ):
        raise AppError(
            "Only in-progress deletion requests can be executed",
            status_code=409,
            code="INVALID_TRANSITION",
        )
    email = row.email
    contacts = (
        db.execute(select(Contact).where(Contact.business_email == email).with_for_update())
        .scalars()
        .all()
    )
    for c in contacts:
        c.full_name, c.designation, c.business_email, c.phone = (
            "Deleted contact",
            None,
            f"deleted-{c.id}@deleted.invalid",
            "+0000000",
        )
    notified = db.execute(
        update(Notification)
        .where(Notification.recipient == email)
        .values(recipient="deleted@deleted.invalid", context={})
    )
    subs = db.execute(delete(NewsletterSubscription).where(NewsletterSubscription.email == email))
    counts = {
        "contacts_anonymised": len(contacts),
        "outbox_rows_anonymised": int(getattr(notified, "rowcount", 0) or 0),
        "newsletter_rows_removed": int(getattr(subs, "rowcount", 0) or 0),
    }
    row.status, row.executed_at, row.handled_by = (
        PrivacyRequestStatus.COMPLETED,
        utcnow(),
        staff.user.id,
    )
    row.email = f"deleted-{row.reference.lower()}@deleted.invalid"
    row.resolution_note = (
        f"Executed: {counts}. Free-text enquiry content and documents need manual review."
    )
    log_activity(
        db,
        "privacy_request",
        row.id,
        "admin.privacy_deletion_executed",
        counts,
        ActorType.STAFF,
        actor_user_id=staff.user.id,
    )
    db.commit()
    return counts
