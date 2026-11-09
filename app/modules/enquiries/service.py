import hashlib
import hmac
import re
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.utilities import utcnow
from app.core.config import Settings
from app.modules.admin import settings_service as cfg
from app.modules.enquiries.activity import log_activity
from app.modules.enquiries.constants import (
    REFERENCE_SEQUENCE,
    SOURCE_WEBSITE,
    ConsentStatus,
    EnquiryType,
)
from app.modules.enquiries.models import Company, Contact, Enquiry
from app.modules.enquiries.routing import apply_routing
from app.modules.enquiries.schemas import ContactEnquiryIn, SubmissionOut, SubmitterIn
from app.modules.notifications.service import queue_submission_notifications

REFERENCE_RE = re.compile(r"^CS-ENQ-\d{4}-\d{6,}$")


def next_reference(db: Session) -> str:
    """Server-side, concurrency-safe (PostgreSQL sequence), never reused (gaps are fine)."""
    n = db.execute(select(func.nextval(REFERENCE_SEQUENCE))).scalar_one()
    return f"CS-ENQ-{utcnow().year}-{n:06d}"


def lookup_token(settings: Settings, reference: str) -> str:
    """Unguessable status token derived from the reference with the server secret (no storage).
    Rotating SECRET_KEY invalidates previously issued tokens."""
    mac = hmac.new(
        settings.secret_key.get_secret_value().encode(),
        f"status-lookup:{reference}".encode(),
        hashlib.sha256,
    )
    return mac.hexdigest()[:40]


@dataclass(frozen=True)
class Created:
    enquiry: Enquiry
    contact: Contact
    out: SubmissionOut


def create_enquiry(
    db: Session,
    settings: Settings,
    *,
    enquiry_type: EnquiryType,
    submitter: SubmitterIn,
    company: Company | None,
    subject: str,
    message: str | None,
) -> Created:
    """Insert company/contact/enquiry/activity/notifications. Caller commits.
    Never merges with existing companies or contacts."""
    now = utcnow()
    if company is None and submitter.company_name:
        company = Company(legal_name=submitter.company_name, country=submitter.country)
    if company is not None:
        db.add(company)
        db.flush()
    contact = Contact(
        company_id=company.id if company else None,
        full_name=submitter.full_name,
        designation=submitter.designation,
        business_email=submitter.business_email,
        phone=submitter.phone,
        country=submitter.country,
        consent_status=ConsentStatus.GRANTED,
        consent_timestamp=now,
        consent_notice_version=settings.privacy_notice_version,
    )
    db.add(contact)
    db.flush()
    reference = next_reference(db)
    enquiry = Enquiry(
        reference_number=reference,
        enquiry_type=enquiry_type,
        company_id=company.id if company else None,
        contact_id=contact.id,
        subject=subject[:200],
        message=message,
        source=submitter.lead_source or SOURCE_WEBSITE,
    )
    db.add(enquiry)
    db.flush()
    log_activity(db, "enquiry", enquiry.id, "enquiry.submitted", {"type": enquiry_type.value})
    sla_hours = apply_routing(db, enquiry, now)
    promise = sla_hours if sla_hours and cfg.is_true(db, "ack_promise_enabled") else None
    queue_submission_notifications(
        db,
        settings,
        response_hours=promise,
        enquiry_id=enquiry.id,
        enquiry_type=enquiry_type,
        reference=reference,
        submitter_email=contact.business_email,
        submitter_name=contact.full_name,
        company=company.legal_name if company else None,
    )
    out = SubmissionOut(
        reference_number=reference,
        lookup_token=lookup_token(settings, reference),
        enquiry_type=enquiry_type,
        status=enquiry.status,
        submitted_at=now,
    )
    return Created(enquiry, contact, out)


def create_contact_enquiry(db: Session, settings: Settings, data: ContactEnquiryIn) -> Created:
    return create_enquiry(
        db,
        settings,
        enquiry_type=EnquiryType.GENERAL,
        submitter=data,
        company=None,
        subject=data.enquiry_type.value,
        message=data.message,
    )


def find_status(
    db: Session, settings: Settings, reference: str, token: str | None
) -> Enquiry | None:
    """None for unknown reference AND for wrong/missing token: callers cannot tell them apart."""
    expected = lookup_token(settings, reference)  # computed even for unknown refs (uniform work)
    if not REFERENCE_RE.match(reference) or not token or not hmac.compare_digest(expected, token):
        return None
    return db.execute(
        select(Enquiry).where(Enquiry.reference_number == reference)
    ).scalar_one_or_none()
