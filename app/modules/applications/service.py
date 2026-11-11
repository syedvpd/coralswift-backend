"""Application lifecycle. All status changes go through `transition` (see transitions.py)."""

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.utilities import utcnow
from app.core.config import Settings
from app.core.exceptions import AppError, NotFoundError
from app.modules.applications.constants import (
    APPLICATION_SEQUENCE,
    PARTNER_LABELS,
    TERMINAL,
    MessageKind,
    MessageStatus,
    PortalStatus,
)
from app.modules.applications.models import (
    ApplicationMessage,
    ApplicationStatusHistory,
    ApplicationSubmission,
    EligibilityVerification,
    PortalApplication,
)
from app.modules.applications.transitions import (
    DEDICATED_TARGETS,
    Actor,
    find_rule,
    invalid,
    resume_rule,
)
from app.modules.auth.constants import UserStatus
from app.modules.auth.dependencies import PartnerContext
from app.modules.auth.models import User
from app.modules.enquiries.activity import log_activity
from app.modules.enquiries.constants import ActorType
from app.modules.notifications.constants import NotificationType, TemplateKey
from app.modules.notifications.service import queue_notification
from app.modules.organizations import service as org_service
from app.modules.organizations.constants import MembershipStatus
from app.modules.organizations.models import PartnerMembership, PartnerOrganization
from app.modules.partner_documents import service as doc_service
from app.modules.partner_documents.constants import DocStatus
from app.modules.partner_documents.models import PartnerDocument, PartnerDocumentVersion
from app.modules.partners.constants import EngagementPathway


# ----------------------------------------------------------------- lookups
def next_reference(db: Session) -> str:
    n = db.execute(select(func.nextval(APPLICATION_SEQUENCE))).scalar_one()
    return f"CS-APP-{utcnow().year}-{n:06d}"


def lock_application(
    db: Session, application_id: uuid.UUID, organization_id: uuid.UUID | None = None
) -> PortalApplication:
    """SELECT ... FOR UPDATE. With organization_id, foreign applications look nonexistent."""
    stmt = select(PortalApplication).where(PortalApplication.id == application_id)
    if organization_id is not None:
        stmt = stmt.where(PortalApplication.organization_id == organization_id)
    app = db.execute(stmt.with_for_update()).scalar_one_or_none()
    if app is None:
        raise NotFoundError("Application not found")
    return app


def get_owned(
    db: Session, organization_id: uuid.UUID, application_id: uuid.UUID
) -> PortalApplication:
    app = db.execute(
        select(PortalApplication).where(
            PortalApplication.id == application_id,
            PortalApplication.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if app is None:
        raise NotFoundError("Application not found")
    return app


def partner_users(db: Session, organization_id: uuid.UUID) -> list[User]:
    return list(
        db.execute(
            select(User)
            .join(PartnerMembership, PartnerMembership.user_id == User.id)
            .where(
                PartnerMembership.organization_id == organization_id,
                PartnerMembership.status == MembershipStatus.ACTIVE,
                User.status == UserStatus.ACTIVE,
            )
        ).scalars()
    )


# --------------------------------------------------------------- readiness
@dataclass(frozen=True)
class Readiness:
    missing_profile_fields: list[str]
    missing_document_categories: list[str]

    @property
    def complete(self) -> bool:
        return not self.missing_profile_fields and not self.missing_document_categories


def readiness(db: Session, org: PartnerOrganization) -> Readiness:
    return Readiness(
        org_service.completion(org).missing_fields,
        doc_service.missing_required_categories(db, org.id),
    )


# ------------------------------------------------------------------ drafts
def create_draft(
    db: Session, ctx: PartnerContext, pathway: EngagementPathway, cover_note: str | None
) -> PortalApplication:
    app = PortalApplication(
        reference=next_reference(db),
        organization_id=ctx.organization_id,
        pathway=pathway,
        status=PortalStatus.DRAFT,
        cover_note=cover_note,
        created_by=ctx.user.id,
    )
    db.add(app)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise AppError(
            "Your organization already has an open application",
            status_code=409,
            code="APPLICATION_ALREADY_OPEN",
        ) from None
    _history(db, app, None, PortalStatus.DRAFT, ActorType.PARTNER, ctx.user.id, None, None)
    log_activity(
        db,
        "portal_application",
        app.id,
        "application.created",
        {"reference": app.reference},
        ActorType.PARTNER,
        actor_user_id=ctx.user.id,
        organization_id=ctx.organization_id,
    )
    db.commit()
    return app


def update_draft(
    db: Session,
    ctx: PartnerContext,
    application_id: uuid.UUID,
    *,
    pathway: EngagementPathway | None,
    cover_note: str | None,
) -> PortalApplication:
    app = lock_application(db, application_id, ctx.organization_id)
    if app.status is not PortalStatus.DRAFT:
        raise AppError("Only a draft can be edited", status_code=409, code="NOT_A_DRAFT")
    if pathway is not None:
        app.pathway = pathway
    if cover_note is not None:
        app.cover_note = cover_note
    log_activity(
        db,
        "portal_application",
        app.id,
        "application.draft_saved",
        None,
        ActorType.PARTNER,
        actor_user_id=ctx.user.id,
        organization_id=ctx.organization_id,
    )
    db.commit()
    return app


# ------------------------------------------------------------- transitions
def _history(
    db: Session,
    app: PortalApplication,
    from_status: PortalStatus | None,
    to_status: PortalStatus,
    actor_type: ActorType,
    actor_user_id: uuid.UUID,
    reason: str | None,
    partner_note: str | None,
) -> ApplicationStatusHistory:
    row = ApplicationStatusHistory(
        application_id=app.id,
        from_status=from_status,
        to_status=to_status,
        actor_type=actor_type.value,
        actor_user_id=actor_user_id,
        reason=reason,
        partner_note=partner_note,
        created_at=utcnow(),
    )
    db.add(row)
    db.flush()
    return row


def transition(
    db: Session,
    settings: Settings,
    *,
    app: PortalApplication,
    target: PortalStatus,
    actor: Actor,
    user: User,
    reason: str | None = None,
    partner_note: str | None = None,
    resume: bool = False,
    dedicated: bool = False,
) -> None:
    """The only place that assigns `app.status`. Caller must hold the row lock and commits."""
    source = app.status
    if resume:
        rule = resume_rule(source, target)
    else:
        if actor is Actor.REVIEWER and target in DEDICATED_TARGETS and not dedicated:
            raise invalid()
        rule = find_rule(actor, source, target)
    if rule.needs_reason and not (reason and reason.strip()):
        raise AppError(
            "A reason is required for this change", status_code=422, code="REASON_REQUIRED"
        )
    if rule.needs_assignee and app.assigned_reviewer_id is None:
        raise AppError("Assign a reviewer first", status_code=422, code="ASSIGNMENT_REQUIRED")
    if target is PortalStatus.CAPABILITY_REVIEW and not _has_verification(db, app.id):
        raise AppError(
            "Record an eligibility verification before moving on",
            status_code=422,
            code="ELIGIBILITY_RECORD_REQUIRED",
        )
    app.status = target
    app.resume_status = source if target is PortalStatus.INFORMATION_REQUESTED else None
    if target in TERMINAL or target in (PortalStatus.PILOT_ONBOARDING, PortalStatus.SCALE_UP):
        app.decided_at = utcnow()
    actor_type = ActorType.PARTNER if actor is Actor.PARTNER else ActorType.REVIEWER
    row = _history(db, app, source, target, actor_type, user.id, reason, partner_note)
    log_activity(
        db,
        "portal_application",
        app.id,
        "application.status_changed",
        {"from": source.value, "to": target.value, "decision": reason is not None},
        actor_type,
        actor_user_id=user.id,
        organization_id=app.organization_id,
    )
    _notify_transition(db, app, row, actor, target, user)


def _has_verification(db: Session, application_id: uuid.UUID) -> bool:
    return (
        db.execute(
            select(func.count())
            .select_from(EligibilityVerification)
            .where(EligibilityVerification.application_id == application_id)
        ).scalar_one()
        > 0
    )


def _notify_transition(
    db: Session,
    app: PortalApplication,
    row: ApplicationStatusHistory,
    actor: Actor,
    target: PortalStatus,
    user: User,
) -> None:
    label = PARTNER_LABELS[target]
    if actor is Actor.REVIEWER and target is not PortalStatus.INFORMATION_REQUESTED:
        decision = target in (
            PortalStatus.REJECTED,
            PortalStatus.PILOT_ONBOARDING,
            PortalStatus.SCALE_UP,
        )
        template = (
            TemplateKey.APPLICATION_DECISION if decision else TemplateKey.APPLICATION_STATUS_CHANGED
        )
        for u in partner_users(db, app.organization_id):
            queue_notification(
                db,
                recipient=u.email,
                kind=NotificationType.APPLICATION,
                template=template,
                context={"reference": app.reference, "name": u.full_name, "status_label": label},
                dedupe_key=f"app-status:{row.id}:{u.id}",
            )


def _internal_recipients(db: Session, settings: Settings, app: PortalApplication) -> list[str]:
    if app.assigned_reviewer_id:
        reviewer = db.get(User, app.assigned_reviewer_id)
        if reviewer and reviewer.status is UserStatus.ACTIVE:
            return [reviewer.email]
    return list(settings.notify_partner_emails)


def _snapshot(db: Session, org: PartnerOrganization) -> dict[str, Any]:
    profile = {
        name: org_service._jsonable(getattr(org, name))  # noqa: SLF001 - same module family
        for name in (
            "legal_name",
            "registration_number",
            "year_established",
            "employee_count",
            "annual_turnover_inr_crore",
            "registered_address",
            "country",
            "website",
            "service_categories",
            "technical_capabilities",
            "infrastructure_summary",
            "business_description",
            "client_references",
            "authorized_contacts",
        )
    }
    docs = db.execute(
        select(PartnerDocument, PartnerDocumentVersion)
        .join(
            PartnerDocumentVersion,
            (PartnerDocumentVersion.document_id == PartnerDocument.id)
            & (PartnerDocumentVersion.version_no == PartnerDocument.current_version_no),
        )
        .where(
            PartnerDocument.organization_id == org.id, PartnerDocument.status == DocStatus.ACTIVE
        )
    ).all()
    return {
        "profile_version": org.profile_version,
        "profile": profile,
        "documents": [
            {
                "document_id": str(d.id),
                "category": d.category.value,
                "version_id": str(v.id),
                "version_no": v.version_no,
                "checksum": v.checksum,
            }
            for d, v in docs
        ],
    }


def _take_submission(
    db: Session, app: PortalApplication, org: PartnerOrganization, user: User
) -> int:
    app.submission_count += 1
    db.add(
        ApplicationSubmission(
            application_id=app.id,
            submission_no=app.submission_count,
            submitted_by=user.id,
            submitted_at=utcnow(),
            snapshot=_snapshot(db, org),
        )
    )
    return app.submission_count


def submit(
    db: Session, settings: Settings, ctx: PartnerContext, application_id: uuid.UUID
) -> PortalApplication:
    app = lock_application(db, application_id, ctx.organization_id)
    if app.status is not PortalStatus.DRAFT:
        raise invalid()
    org = org_service.get_organization(db, ctx.organization_id)
    ready = readiness(db, org)
    if not ready.complete:
        raise AppError(
            "The application is incomplete",
            status_code=422,
            code="APPLICATION_INCOMPLETE",
            details=[
                {"field": "profile", "missing": ready.missing_profile_fields},
                {"field": "documents", "missing": ready.missing_document_categories},
            ],
        )
    _take_submission(db, app, org, ctx.user)
    transition(
        db, settings, app=app, target=PortalStatus.SUBMITTED, actor=Actor.PARTNER, user=ctx.user
    )
    app.submitted_at = utcnow()
    row_id = app.id
    for u in partner_users(db, org.id):
        queue_notification(
            db,
            recipient=u.email,
            kind=NotificationType.APPLICATION,
            template=TemplateKey.APPLICATION_SUBMITTED,
            context={"reference": app.reference, "name": u.full_name},
            dedupe_key=f"app-submitted:{row_id}:{app.submission_count}:{u.id}",
        )
    for address in _internal_recipients(db, settings, app):
        queue_notification(
            db,
            recipient=address,
            kind=NotificationType.INTERNAL,
            template=TemplateKey.INTERNAL_NEW_ENQUIRY,
            context={
                "reference": app.reference,
                "enquiry_type": "partner",
                "name": ctx.user.full_name,
                "company": org.legal_name,
            },
            dedupe_key=f"app-submitted-internal:{row_id}:{app.submission_count}:{address.lower()}",
        )
    db.commit()
    return app


def withdraw(
    db: Session,
    settings: Settings,
    ctx: PartnerContext,
    application_id: uuid.UUID,
    note: str | None,
) -> PortalApplication:
    app = lock_application(db, application_id, ctx.organization_id)
    transition(
        db,
        settings,
        app=app,
        target=PortalStatus.WITHDRAWN,
        actor=Actor.PARTNER,
        user=ctx.user,
        reason=note,
    )
    db.commit()
    return app


def resubmit(
    db: Session, settings: Settings, ctx: PartnerContext, application_id: uuid.UUID
) -> PortalApplication:
    app = lock_application(db, application_id, ctx.organization_id)
    if app.status is not PortalStatus.INFORMATION_REQUESTED or app.resume_status is None:
        raise invalid()
    open_requests = db.execute(
        select(func.count())
        .select_from(ApplicationMessage)
        .where(
            ApplicationMessage.application_id == app.id,
            ApplicationMessage.kind == MessageKind.INFORMATION_REQUEST,
            ApplicationMessage.status == MessageStatus.OPEN,
        )
    ).scalar_one()
    if open_requests:
        raise AppError(
            "Answer all open information requests first", status_code=409, code="OPEN_REQUESTS"
        )
    org = org_service.get_organization(db, ctx.organization_id)
    _take_submission(db, app, org, ctx.user)
    target = app.resume_status
    transition(
        db,
        settings,
        app=app,
        target=target,
        actor=Actor.PARTNER,
        user=ctx.user,
        resume=True,
        partner_note="Resubmitted with additional information",
    )
    for address in _internal_recipients(db, settings, app):
        queue_notification(
            db,
            recipient=address,
            kind=NotificationType.INTERNAL,
            template=TemplateKey.PARTNER_RESPONSE_RECEIVED,
            context={"reference": app.reference},
            dedupe_key=f"app-resubmitted:{app.id}:{app.submission_count}:{address.lower()}",
        )
    db.commit()
    return app


# -------------------------------------------------------------- read models
def open_request_count(db: Session, application_id: uuid.UUID) -> int:
    return db.execute(
        select(func.count())
        .select_from(ApplicationMessage)
        .where(
            ApplicationMessage.application_id == application_id,
            ApplicationMessage.kind == MessageKind.INFORMATION_REQUEST,
            ApplicationMessage.status == MessageStatus.OPEN,
        )
    ).scalar_one()


def decision_explanation(db: Session, app: PortalApplication) -> str | None:
    """Latest reviewer-written, partner-safe note on a decision (never the internal reason)."""
    if app.decided_at is None:
        return None
    return db.execute(
        select(ApplicationStatusHistory.partner_note)
        .where(
            ApplicationStatusHistory.application_id == app.id,
            ApplicationStatusHistory.partner_note.is_not(None),
            ApplicationStatusHistory.to_status.in_(
                [PortalStatus.REJECTED, PortalStatus.PILOT_ONBOARDING, PortalStatus.SCALE_UP]
            ),
        )
        .order_by(ApplicationStatusHistory.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def next_information_due(db: Session, application_id: uuid.UUID) -> date | None:
    return db.execute(
        select(func.min(ApplicationMessage.due_date)).where(
            ApplicationMessage.application_id == application_id,
            ApplicationMessage.kind == MessageKind.INFORMATION_REQUEST,
            ApplicationMessage.status == MessageStatus.OPEN,
        )
    ).scalar_one()


def partner_history(db: Session, application_id: uuid.UUID) -> list[ApplicationStatusHistory]:
    return list(
        db.execute(
            select(ApplicationStatusHistory)
            .where(ApplicationStatusHistory.application_id == application_id)
            .order_by(ApplicationStatusHistory.created_at)
        ).scalars()
    )
