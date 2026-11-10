"""Reviewer operations. A reviewer sees only applications assigned to them; a super
administrator may act on any submitted application (and is the only role that can assign)."""

import uuid

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.common.utilities import utcnow
from app.core.exceptions import AppError, NotFoundError
from app.modules.admin.feed import notify_staff
from app.modules.applications.constants import PortalStatus
from app.modules.applications.models import (
    EligibilityVerification,
    PortalApplication,
    ReviewerNote,
)
from app.modules.auth.constants import StaffRole, UserStatus, UserType
from app.modules.auth.dependencies import StaffContext
from app.modules.auth.models import User
from app.modules.enquiries.activity import log_activity
from app.modules.enquiries.constants import ActorType
from app.modules.notifications.constants import NotificationType, TemplateKey
from app.modules.notifications.service import queue_notification
from app.modules.partner_documents.constants import DocStatus
from app.modules.partner_documents.models import PartnerDocument, PartnerDocumentVersion
from app.modules.reviews.schemas import DocumentReviewIn, EligibilityIn


def reviewable_query(staff: StaffContext) -> Select[PortalApplication]:
    stmt = select(PortalApplication).where(PortalApplication.status != PortalStatus.DRAFT)
    if not staff.is_super_admin:
        stmt = stmt.where(PortalApplication.assigned_reviewer_id == staff.user.id)
    return stmt


def get_reviewable(
    db: Session, staff: StaffContext, application_id: uuid.UUID, *, lock: bool = False
) -> PortalApplication:
    """404 for drafts, unassigned or foreign applications: existence is not revealed."""
    stmt = reviewable_query(staff).where(PortalApplication.id == application_id)
    if lock:
        stmt = stmt.with_for_update()
    app = db.execute(stmt).scalar_one_or_none()
    if app is None:
        raise NotFoundError("Application not found")
    return app


def assign(
    db: Session, staff: StaffContext, app: PortalApplication, reviewer_id: uuid.UUID | None
) -> None:
    if reviewer_id is None:
        previous_id = app.assigned_reviewer_id
        app.assigned_reviewer_id = None
        log_activity(
            db,
            "portal_application",
            app.id,
            "application.reviewer_cleared",
            {"previous": str(previous_id) if previous_id else None},
            ActorType.REVIEWER,
            actor_user_id=staff.user.id,
            organization_id=app.organization_id,
        )
        return
    reviewer = db.get(User, reviewer_id)
    if (
        reviewer is None
        or reviewer.user_type is not UserType.STAFF
        or reviewer.status is not UserStatus.ACTIVE
        or reviewer.staff_role not in (StaffRole.PARTNER_REVIEWER, StaffRole.SUPER_ADMINISTRATOR)
    ):
        raise AppError("Not a valid reviewer", status_code=422, code="INVALID_REVIEWER")
    previous = app.assigned_reviewer_id
    app.assigned_reviewer_id = reviewer.id
    if previous != reviewer.id:  # PRD s.13/s.14: notify the reviewer of a new assignment
        if reviewer.id != staff.user.id:
            notify_staff(
                db,
                reviewer.id,
                "application_assigned",
                f"Application {app.reference} was assigned to you",
                record_type="portal_application",
                record_id=app.id,
            )
        queue_notification(
            db,
            recipient=reviewer.email,
            kind=NotificationType.INTERNAL,
            template=TemplateKey.REVIEWER_ASSIGNED,
            context={"reference": app.reference},
            dedupe_key=f"assigned:{app.id}:{reviewer.id}:{utcnow().isoformat()}",
        )
    log_activity(
        db,
        "portal_application",
        app.id,
        "application.reviewer_assigned",
        {"reviewer_id": str(reviewer.id), "previous": str(previous) if previous else None},
        ActorType.REVIEWER,
        actor_user_id=staff.user.id,
        organization_id=app.organization_id,
    )


def add_eligibility(
    db: Session, staff: StaffContext, app: PortalApplication, data: EligibilityIn
) -> EligibilityVerification:
    ids = [str(i) for i in dict.fromkeys(data.supporting_version_ids)]
    if ids:
        found = set(
            str(v)
            for v in db.execute(
                select(PartnerDocumentVersion.id)
                .join(PartnerDocument, PartnerDocument.id == PartnerDocumentVersion.document_id)
                .where(
                    PartnerDocumentVersion.id.in_([uuid.UUID(i) for i in ids]),
                    PartnerDocument.organization_id == app.organization_id,
                )
            ).scalars()
        )
        if found != set(ids):
            raise AppError(
                "Unknown supporting document version",
                status_code=422,
                code="INVALID_DOCUMENT_REFERENCE",
            )
    row = EligibilityVerification(
        application_id=app.id,
        submission_no=max(app.submission_count, 1),
        verified_by=staff.user.id,
        verified_at=utcnow(),
        verified_operating_years=data.verified_operating_years,
        verified_personnel=data.verified_personnel,
        verified_turnover_inr_crore=data.verified_turnover_inr_crore,
        outcome=data.outcome,
        exception_note=data.exception_note,
        notes=data.notes,
        supporting_version_ids=ids,
    )
    db.add(row)
    db.flush()
    log_activity(
        db,
        "portal_application",
        app.id,
        "application.eligibility_verified",
        {"outcome": data.outcome.value, "verification_id": str(row.id)},
        ActorType.REVIEWER,
        actor_user_id=staff.user.id,
        organization_id=app.organization_id,
    )
    return row


def list_eligibility(db: Session, application_id: uuid.UUID) -> list[EligibilityVerification]:
    return list(
        db.execute(
            select(EligibilityVerification)
            .where(EligibilityVerification.application_id == application_id)
            .order_by(EligibilityVerification.verified_at)
        ).scalars()
    )


def add_note(db: Session, staff: StaffContext, app: PortalApplication, body: str) -> ReviewerNote:
    note = ReviewerNote(
        application_id=app.id, author_id=staff.user.id, body=body, created_at=utcnow()
    )
    db.add(note)
    db.flush()
    # The note text is deliberately NOT copied into the audit metadata.
    log_activity(
        db,
        "portal_application",
        app.id,
        "application.note_added",
        {"note_id": str(note.id)},
        ActorType.REVIEWER,
        actor_user_id=staff.user.id,
        organization_id=app.organization_id,
    )
    return note


def list_notes(db: Session, application_id: uuid.UUID) -> list[ReviewerNote]:
    return list(
        db.execute(
            select(ReviewerNote)
            .where(ReviewerNote.application_id == application_id)
            .order_by(ReviewerNote.created_at)
        ).scalars()
    )


def get_application_document(
    db: Session, app: PortalApplication, document_id: uuid.UUID
) -> PartnerDocument:
    doc = db.execute(
        select(PartnerDocument).where(
            PartnerDocument.id == document_id,
            PartnerDocument.organization_id == app.organization_id,
            PartnerDocument.status == DocStatus.ACTIVE,
        )
    ).scalar_one_or_none()
    if doc is None:
        raise NotFoundError("Document not found")
    return doc


def review_document(
    db: Session,
    staff: StaffContext,
    app: PortalApplication,
    doc: PartnerDocument,
    data: DocumentReviewIn,
) -> PartnerDocumentVersion:
    number = data.version_no or doc.current_version_no
    version = db.execute(
        select(PartnerDocumentVersion)
        .where(
            PartnerDocumentVersion.document_id == doc.id,
            PartnerDocumentVersion.version_no == number,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if version is None:
        raise NotFoundError("Document version not found")
    version.review_status = data.status
    version.review_comment = data.comment
    version.reviewed_by = staff.user.id
    version.reviewed_at = utcnow()
    log_activity(
        db,
        "partner_document",
        doc.id,
        "document.reviewed",
        {"status": data.status.value, "version": version.version_no},
        ActorType.REVIEWER,
        actor_user_id=staff.user.id,
        organization_id=app.organization_id,
    )
    return version
