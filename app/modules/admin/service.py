"""Phase 3 admin operations. Permission model (PRD s.14):

* super_administrator: everything below, including strategic (M&A) enquiries, financial data, users.
* business_development_manager: general / project / partner enquiries (assignment, follow-ups),
  limited partner view. Strategic enquiries and financial data are NOT visible (restricted by
  default; whether BDMs handle "partnership discussions" is a business decision).
Partner Reviewer keeps the Phase 2 reviewer API only.
"""

import csv
import io
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.common.utilities import utcnow
from app.core.exceptions import AppError, NotFoundError
from app.integrations.storage import Storage, StorageError
from app.modules.admin.models import EnquiryFollowUp
from app.modules.applications.constants import TERMINAL, PortalStatus
from app.modules.applications.models import PortalApplication
from app.modules.auth import service as auth_service
from app.modules.auth.constants import StaffRole, UserStatus, UserType
from app.modules.auth.dependencies import StaffContext
from app.modules.auth.models import User
from app.modules.documents.models import Document
from app.modules.engagement.models import MeetingRequest
from app.modules.enquiries.activity import log_activity
from app.modules.enquiries.constants import ActorType, EnquiryStatus, EnquiryType, Priority
from app.modules.enquiries.models import Activity, Company, Contact, Enquiry
from app.modules.notifications.constants import DeliveryStatus
from app.modules.notifications.models import Notification
from app.modules.organizations.models import PartnerOrganization
from app.modules.partners.models import PartnerApplication
from app.modules.projects.models import ProjectEnquiry
from app.modules.strategic.models import StrategicEnquiry

BDM_TYPES = {EnquiryType.GENERAL, EnquiryType.PROJECT, EnquiryType.PARTNER, EnquiryType.MEETING}
MAX_EXPORT_ROWS = 10_000


def _is_super(staff: StaffContext) -> bool:
    return staff.user.staff_role is StaffRole.SUPER_ADMINISTRATOR


def visible_types(staff: StaffContext) -> set[EnquiryType]:
    return set(EnquiryType) if _is_super(staff) else BDM_TYPES


def _audit(
    db: Session,
    staff: StaffContext,
    record_type: str,
    record_id: uuid.UUID,
    action: str,
    meta: dict[str, Any] | None = None,
    organization_id: uuid.UUID | None = None,
) -> None:
    log_activity(
        db,
        record_type,
        record_id,
        action,
        meta,
        ActorType.STAFF,
        actor_user_id=staff.user.id,
        organization_id=organization_id,
    )


# ------------------------------------------------------------------ enquiries
def _like(q: str) -> str:
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def enquiry_query(staff: StaffContext) -> Select[Enquiry, Contact, Company]:
    return (
        select(Enquiry, Contact, Company)
        .join(Contact, Contact.id == Enquiry.contact_id)
        .outerjoin(Company, Company.id == Enquiry.company_id)
        .where(Enquiry.enquiry_type.in_(visible_types(staff)))
    )


def apply_filters(
    stmt: Select[Enquiry, Contact, Company],
    *,
    enquiry_type: EnquiryType | None = None,
    status: EnquiryStatus | None = None,
    priority: Priority | None = None,
    assigned_user_id: uuid.UUID | None = None,
    unassigned: bool = False,
    overdue: bool = False,
    sla_breached: bool = False,
    q: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> Select[Enquiry, Contact, Company]:
    if enquiry_type:
        stmt = stmt.where(Enquiry.enquiry_type == enquiry_type)
    if status:
        stmt = stmt.where(Enquiry.status == status)
    if priority:
        stmt = stmt.where(Enquiry.priority == priority)
    if assigned_user_id:
        stmt = stmt.where(Enquiry.assigned_user_id == assigned_user_id)
    if unassigned:
        stmt = stmt.where(Enquiry.assigned_user_id.is_(None))
    if overdue:
        stmt = stmt.where(
            Enquiry.next_follow_up_at < utcnow(), Enquiry.status != EnquiryStatus.CLOSED
        )
    if sla_breached:
        stmt = stmt.where(
            Enquiry.response_due_at < utcnow(),
            Enquiry.first_response_at.is_(None),
            Enquiry.status != EnquiryStatus.CLOSED,
        )
    if created_from:
        stmt = stmt.where(Enquiry.created_at >= created_from)
    if created_to:
        stmt = stmt.where(Enquiry.created_at < created_to)
    if q:
        pattern = _like(q.strip())
        stmt = stmt.where(
            or_(
                Enquiry.reference_number.ilike(pattern, escape="\\"),
                Contact.full_name.ilike(pattern, escape="\\"),
                Contact.business_email.ilike(pattern, escape="\\"),
                Company.legal_name.ilike(pattern, escape="\\"),
            )
        )
    return stmt


def row_dict(e: Enquiry, c: Contact, co: Company | None) -> dict[str, Any]:
    return {
        "id": e.id,
        "reference_number": e.reference_number,
        "enquiry_type": e.enquiry_type,
        "subject": e.subject,
        "status": e.status,
        "priority": e.priority,
        "source": e.source,
        "contact_name": c.full_name,
        "contact_email": c.business_email,
        "company_name": co.legal_name if co else None,
        "assigned_user_id": e.assigned_user_id,
        "next_follow_up_at": e.next_follow_up_at,
        "created_at": e.created_at,
    }


def list_enquiries(
    db: Session, staff: StaffContext, limit: int, offset: int, **filters: Any
) -> tuple[list[dict[str, Any]], int]:
    stmt = apply_filters(enquiry_query(staff), **filters)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(stmt.order_by(Enquiry.created_at.desc()).limit(limit).offset(offset)).all()
    return [row_dict(*r) for r in rows], total


def get_visible(
    db: Session, staff: StaffContext, enquiry_id: uuid.UUID, *, lock: bool = False
) -> Enquiry:
    stmt = select(Enquiry).where(
        Enquiry.id == enquiry_id, Enquiry.enquiry_type.in_(visible_types(staff))
    )
    if lock:
        stmt = stmt.with_for_update()
    enquiry = db.execute(stmt).scalar_one_or_none()
    if enquiry is None:
        raise NotFoundError("Enquiry not found")  # also hides restricted types from BDMs
    return enquiry


def _doc_allowed(staff: StaffContext, category: str | None) -> bool:
    return _is_super(staff) or category != "financial_statements"


def enquiry_detail(db: Session, staff: StaffContext, enquiry_id: uuid.UUID) -> dict[str, Any]:
    e = get_visible(db, staff, enquiry_id)
    c = db.get(Contact, e.contact_id)
    co = db.get(Company, e.company_id) if e.company_id else None
    if c is None:
        raise NotFoundError("Enquiry not found")
    details: dict[str, Any] | None = None
    if e.enquiry_type is EnquiryType.PROJECT:
        p = db.execute(
            select(ProjectEnquiry).where(ProjectEnquiry.enquiry_id == e.id)
        ).scalar_one_or_none()
        if p:
            details = {
                "project_category": p.project_category.value,
                "requirement_summary": p.requirement_summary,
                "scope": p.scope,
                "expected_timeline": p.expected_timeline,
                "estimated_volume": p.estimated_volume,
                "geography": p.geography,
                "security_constraints": p.security_constraints,
            }
    elif e.enquiry_type is EnquiryType.PARTNER:
        a = db.execute(
            select(PartnerApplication).where(PartnerApplication.enquiry_id == e.id)
        ).scalar_one_or_none()
        if a:
            details = {
                "preferred_engagement_pathway": a.preferred_engagement_pathway.value,
                "workforce_range": a.workforce_range.value,
                "service_categories": a.service_categories,
                "infrastructure_summary": a.infrastructure_summary,
                "client_experience": a.client_experience,
                "application_status": a.application_status.value,
            }
            if _is_super(staff):  # financial / third-party data stays with super administrators
                details["turnover_range"] = a.turnover_range.value
                details["client_references"] = a.client_references
    elif e.enquiry_type is EnquiryType.MEETING:
        m = db.execute(
            select(MeetingRequest).where(MeetingRequest.enquiry_id == e.id)
        ).scalar_one_or_none()
        if m:
            details = {
                "purpose": m.purpose,
                "preferred_slots": m.preferred_slots,
                "timezone": m.timezone,
                "status": m.status.value,
                "calendar_checked": m.calendar_checked,
                "confirmed_start": m.confirmed_start,
                "confirmed_end": m.confirmed_end,
                "decision_note": m.decision_note,
            }
    elif e.enquiry_type is EnquiryType.STRATEGIC:
        s = db.execute(
            select(StrategicEnquiry).where(StrategicEnquiry.enquiry_id == e.id)
        ).scalar_one_or_none()
        if s:
            details = {
                "discussion_type": s.discussion_type.value,
                "business_overview": s.business_overview,
                "confidential_summary": s.confidential_summary,
                "access_classification": s.access_classification.value,
            }
    docs = db.execute(select(Document).where(Document.owner_id == e.id)).scalars()
    _audit(db, staff, "enquiry", e.id, "admin.enquiry_viewed", {"type": e.enquiry_type.value})
    db.commit()
    return {
        "enquiry": row_dict(e, c, co),
        "message": e.message,
        "contact": {
            "full_name": c.full_name,
            "designation": c.designation,
            "business_email": c.business_email,
            "phone": c.phone,
            "country": c.country,
            "consent_status": c.consent_status.value,
            "consent_timestamp": c.consent_timestamp,
            "consent_notice_version": c.consent_notice_version,
        },
        "company": (
            {
                "legal_name": co.legal_name,
                "website": co.website,
                "country": co.country,
                "year_established": co.year_established,
                "registered_address": co.registered_address,
            }
            if co
            else None
        ),
        "details": details,
        "documents": [
            {
                "id": d.id,
                "original_filename": d.original_filename,
                "content_type": d.content_type,
                "file_size": d.file_size,
                "category": d.category.value if d.category else None,
                "classification": d.classification.value,
                "upload_status": d.upload_status.value,
            }
            for d in docs
            if _doc_allowed(staff, d.category.value if d.category else None)
        ],
        "follow_ups": list_followups(db, e.id),
    }


def mark_response(e: Enquiry) -> None:
    """First staff response stops the SLA clock (a status change or a follow-up note counts)."""
    if e.first_response_at is None:
        e.first_response_at = utcnow()


def update_enquiry(
    db: Session,
    staff: StaffContext,
    enquiry_id: uuid.UUID,
    status: EnquiryStatus | None,
    priority: Priority | None,
) -> Enquiry:
    e = get_visible(db, staff, enquiry_id, lock=True)
    changes: dict[str, Any] = {}
    if status and status is not e.status:
        changes["status"] = {"from": e.status.value, "to": status.value}
        e.status = status
        mark_response(e)
    if priority and priority is not e.priority:
        changes["priority"] = {"from": e.priority.value, "to": priority.value}
        e.priority = priority
    if changes:
        _audit(db, staff, "enquiry", e.id, "admin.enquiry_updated", changes)
    db.commit()
    return e


def assign_enquiry(
    db: Session, staff: StaffContext, enquiry_id: uuid.UUID, user_id: uuid.UUID | None
) -> Enquiry:
    e = get_visible(db, staff, enquiry_id, lock=True)
    if user_id is not None:
        owner = db.get(User, user_id)
        allowed = {StaffRole.BUSINESS_DEVELOPMENT_MANAGER, StaffRole.SUPER_ADMINISTRATOR}
        if e.enquiry_type is EnquiryType.STRATEGIC:
            allowed = {
                StaffRole.SUPER_ADMINISTRATOR
            }  # confidential records: super administrators only
        if (
            owner is None
            or owner.status is not UserStatus.ACTIVE
            or owner.staff_role not in allowed
        ):
            raise AppError(
                "Not a valid owner for this enquiry", status_code=422, code="INVALID_OWNER"
            )
    previous = e.assigned_user_id
    e.assigned_user_id = user_id
    _audit(
        db,
        staff,
        "enquiry",
        e.id,
        "admin.enquiry_assigned",
        {
            "owner": str(user_id) if user_id else None,
            "previous": str(previous) if previous else None,
        },
    )
    db.commit()
    return e


# ------------------------------------------------------------------ follow-ups
def list_followups(db: Session, enquiry_id: uuid.UUID) -> list[EnquiryFollowUp]:
    return list(
        db.execute(
            select(EnquiryFollowUp)
            .where(EnquiryFollowUp.enquiry_id == enquiry_id)
            .order_by(EnquiryFollowUp.created_at)
        ).scalars()
    )


def _recompute_next(db: Session, e: Enquiry) -> None:
    e.next_follow_up_at = db.execute(
        select(func.min(EnquiryFollowUp.due_at)).where(
            EnquiryFollowUp.enquiry_id == e.id, EnquiryFollowUp.completed_at.is_(None)
        )
    ).scalar_one()


def add_followup(
    db: Session, staff: StaffContext, enquiry_id: uuid.UUID, note: str, due_at: datetime | None
) -> EnquiryFollowUp:
    e = get_visible(db, staff, enquiry_id, lock=True)
    f = EnquiryFollowUp(
        enquiry_id=e.id, author_id=staff.user.id, note=note, due_at=due_at, created_at=utcnow()
    )
    db.add(f)
    db.flush()
    mark_response(e)
    _recompute_next(db, e)
    _audit(
        db,
        staff,
        "enquiry",
        e.id,
        "admin.followup_added",
        {"followup_id": str(f.id), "due": due_at is not None},
    )
    db.commit()
    return f


def complete_followup(
    db: Session, staff: StaffContext, enquiry_id: uuid.UUID, followup_id: uuid.UUID
) -> EnquiryFollowUp:
    e = get_visible(db, staff, enquiry_id, lock=True)
    f = db.execute(
        select(EnquiryFollowUp)
        .where(EnquiryFollowUp.id == followup_id, EnquiryFollowUp.enquiry_id == e.id)
        .with_for_update()
    ).scalar_one_or_none()
    if f is None:
        raise NotFoundError("Follow-up not found")
    if f.completed_at is None:
        f.completed_at = utcnow()
        db.flush()  # sessions run with autoflush off; the recompute query must see completed_at
        _recompute_next(db, e)
        _audit(db, staff, "enquiry", e.id, "admin.followup_completed", {"followup_id": str(f.id)})
    db.commit()
    return f


def download_document(
    db: Session,
    storage: Storage,
    staff: StaffContext,
    enquiry_id: uuid.UUID,
    document_id: uuid.UUID,
) -> tuple[bytes, Document]:
    e = get_visible(db, staff, enquiry_id)
    d = db.execute(
        select(Document).where(Document.id == document_id, Document.owner_id == e.id)
    ).scalar_one_or_none()
    if d is None or not _doc_allowed(staff, d.category.value if d.category else None):
        raise NotFoundError("Document not found")
    try:
        data = storage.get(d.storage_key)
    except StorageError:
        raise AppError(
            "File storage is unavailable", status_code=503, code="STORAGE_UNAVAILABLE"
        ) from None
    _audit(db, staff, "document", d.id, "admin.document_downloaded", {"enquiry": str(e.id)})
    db.commit()
    return data, d


# --------------------------------------------------------------- organizations
def list_orgs(
    db: Session, limit: int, offset: int, q: str | None, status: str | None
) -> tuple[list[dict[str, Any]], int]:
    stmt = select(PartnerOrganization)
    if q:
        stmt = stmt.where(PartnerOrganization.legal_name.ilike(_like(q.strip()), escape="\\"))
    if status:
        stmt = stmt.where(PartnerOrganization.status == status)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    orgs = list(
        db.execute(
            stmt.order_by(PartnerOrganization.created_at.desc()).limit(limit).offset(offset)
        ).scalars()
    )
    open_status = dict(
        db.execute(
            select(PortalApplication.organization_id, PortalApplication.status).where(
                PortalApplication.organization_id.in_([o.id for o in orgs]),
                PortalApplication.status.notin_(list(TERMINAL)),
            )
        ).all()
    )
    return [
        {
            "id": o.id,
            "legal_name": o.legal_name,
            "status": o.status.value,
            "country": o.country,
            "created_at": o.created_at,
            "open_application_status": open_status[o.id].value if o.id in open_status else None,
        }
        for o in orgs
    ], total


def org_detail(db: Session, staff: StaffContext, org_id: uuid.UUID) -> dict[str, Any]:
    o = db.get(PartnerOrganization, org_id)
    if o is None:
        raise NotFoundError("Organization not found")
    profile: dict[str, Any] = {
        "legal_name": o.legal_name,
        "status": o.status.value,
        "year_established": o.year_established,
        "employee_count": o.employee_count,
        "registered_address": o.registered_address,
        "country": o.country,
        "website": o.website,
        "service_categories": o.service_categories,
        "technical_capabilities": o.technical_capabilities,
        "business_description": o.business_description,
    }
    if _is_super(staff):  # financial / identifying data
        profile.update(
            registration_number=o.registration_number,
            annual_turnover_inr_crore=o.annual_turnover_inr_crore,
            client_references=o.client_references,
            authorized_contacts=o.authorized_contacts,
        )
    apps = db.execute(
        select(PortalApplication)
        .where(PortalApplication.organization_id == o.id)
        .order_by(PortalApplication.created_at.desc())
    ).scalars()
    _audit(db, staff, "organization", o.id, "admin.organization_viewed", None, o.id)
    db.commit()
    return {
        "profile": profile,
        "applications": [
            {
                "id": a.id,
                "reference": a.reference,
                "status": a.status.value,
                "assigned_reviewer_id": a.assigned_reviewer_id,
            }
            for a in apps
        ],
    }


def set_org_status(
    db: Session, staff: StaffContext, org_id: uuid.UUID, status: str, reason: str
) -> PartnerOrganization:
    o = db.execute(
        select(PartnerOrganization).where(PartnerOrganization.id == org_id).with_for_update()
    ).scalar_one_or_none()
    if o is None:
        raise NotFoundError("Organization not found")
    previous = o.status.value
    o.status = type(o.status)(status)
    _audit(
        db,
        staff,
        "organization",
        o.id,
        "admin.organization_status_changed",
        {"from": previous, "to": status},
        o.id,
    )
    db.commit()
    return o


# ------------------------------------------------------------------ staff users
def list_staff(db: Session, role: StaffRole | None) -> list[User]:
    stmt = select(User).where(User.user_type == UserType.STAFF)
    if role:
        stmt = stmt.where(User.staff_role == role)
    return list(db.execute(stmt.order_by(User.created_at)).scalars())


def _active_super_admins(db: Session) -> int:
    return db.execute(
        select(func.count())
        .select_from(User)
        .where(User.staff_role == StaffRole.SUPER_ADMINISTRATOR, User.status == UserStatus.ACTIVE)
    ).scalar_one()


def _staff(db: Session, user_id: uuid.UUID) -> User:
    u = db.execute(
        select(User).where(User.id == user_id, User.user_type == UserType.STAFF).with_for_update()
    ).scalar_one_or_none()
    if u is None:
        raise NotFoundError("Staff user not found")
    return u


def change_role(db: Session, staff: StaffContext, user_id: uuid.UUID, role: StaffRole) -> User:
    u = _staff(db, user_id)
    if u.id == staff.user.id:
        raise AppError("You cannot change your own role", status_code=409, code="SELF_CHANGE")
    if (
        u.staff_role is StaffRole.SUPER_ADMINISTRATOR
        and role is not StaffRole.SUPER_ADMINISTRATOR
        and u.status is UserStatus.ACTIVE
        and _active_super_admins(db) <= 1
    ):
        raise AppError(
            "At least one super administrator must remain", status_code=409, code="LAST_SUPER_ADMIN"
        )
    previous = u.staff_role
    u.staff_role = role
    auth_service.revoke_all_sessions(db, u.id, "role_changed")
    _audit(
        db,
        staff,
        "user",
        u.id,
        "admin.staff_role_changed",
        {"from": previous.value if previous else None, "to": role.value},
    )
    db.commit()
    return u


def set_staff_active(db: Session, staff: StaffContext, user_id: uuid.UUID, active: bool) -> User:
    u = _staff(db, user_id)
    if u.id == staff.user.id:
        raise AppError("You cannot change your own status", status_code=409, code="SELF_CHANGE")
    if not active:
        if (
            u.staff_role is StaffRole.SUPER_ADMINISTRATOR
            and u.status is UserStatus.ACTIVE
            and _active_super_admins(db) <= 1
        ):
            raise AppError(
                "At least one super administrator must remain",
                status_code=409,
                code="LAST_SUPER_ADMIN",
            )
        u.status = UserStatus.DEACTIVATED
        auth_service.revoke_all_sessions(db, u.id, "deactivated")
    elif u.password_hash is not None:
        u.status = UserStatus.ACTIVE
    else:
        raise AppError(
            "The invitation has not been accepted yet", status_code=409, code="NOT_ACTIVATED"
        )
    _audit(
        db, staff, "user", u.id, "admin.staff_activated" if active else "admin.staff_deactivated"
    )
    db.commit()
    return u


# ------------------------------------------------------------- audit / overview
def list_audit(
    db: Session,
    limit: int,
    offset: int,
    *,
    record_type: str | None,
    action: str | None,
    actor_user_id: uuid.UUID | None,
    organization_id: uuid.UUID | None,
    created_from: datetime | None,
    created_to: datetime | None,
) -> tuple[list[Activity], int]:
    stmt = select(Activity)
    if record_type:
        stmt = stmt.where(Activity.record_type == record_type)
    if action:
        stmt = stmt.where(Activity.action.ilike(_like(action), escape="\\"))
    if actor_user_id:
        stmt = stmt.where(Activity.actor_user_id == actor_user_id)
    if organization_id:
        stmt = stmt.where(Activity.organization_id == organization_id)
    if created_from:
        stmt = stmt.where(Activity.created_at >= created_from)
    if created_to:
        stmt = stmt.where(Activity.created_at < created_to)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    return list(
        db.execute(stmt.order_by(Activity.created_at.desc()).limit(limit).offset(offset)).scalars()
    ), total


def overview(db: Session, staff: StaffContext) -> dict[str, Any]:
    types = visible_types(staff)
    now = utcnow()
    by = db.execute(
        select(Enquiry.enquiry_type, Enquiry.status, func.count())
        .where(Enquiry.enquiry_type.in_(types))
        .group_by(Enquiry.enquiry_type, Enquiry.status)
    ).all()
    out: dict[str, Any] = {"enquiries": {f"{t.value}:{s.value}": n for t, s, n in by}}
    out["unassigned_enquiries"] = db.execute(
        select(func.count())
        .select_from(Enquiry)
        .where(
            Enquiry.enquiry_type.in_(types),
            Enquiry.assigned_user_id.is_(None),
            Enquiry.status != EnquiryStatus.CLOSED,
        )
    ).scalar_one()
    out["overdue_follow_ups"] = db.execute(
        select(func.count())
        .select_from(Enquiry)
        .where(
            Enquiry.enquiry_type.in_(types),
            Enquiry.next_follow_up_at < now,
            Enquiry.status != EnquiryStatus.CLOSED,
        )
    ).scalar_one()
    out["sla_breached"] = db.execute(
        select(func.count())
        .select_from(Enquiry)
        .where(
            Enquiry.enquiry_type.in_(types),
            Enquiry.response_due_at < now,
            Enquiry.first_response_at.is_(None),
            Enquiry.status != EnquiryStatus.CLOSED,
        )
    ).scalar_one()
    if _is_super(staff):
        out["failed_notifications"] = db.execute(
            select(func.count())
            .select_from(Notification)
            .where(Notification.delivery_status == DeliveryStatus.FAILED)
        ).scalar_one()
        apps = db.execute(
            select(PortalApplication.status, func.count())
            .where(PortalApplication.status != PortalStatus.DRAFT)
            .group_by(PortalApplication.status)
        ).all()
        out["applications"] = {s.value: n for s, n in apps}
        out["unassigned_applications"] = db.execute(
            select(func.count())
            .select_from(PortalApplication)
            .where(
                PortalApplication.status == PortalStatus.SUBMITTED,
                PortalApplication.assigned_reviewer_id.is_(None),
            )
        ).scalar_one()
        recent = db.execute(
            select(Activity).order_by(Activity.created_at.desc()).limit(10)
        ).scalars()
        out["recent_activity"] = [
            {
                "action": a.action,
                "record_type": a.record_type,
                "actor_type": a.actor_type.value,
                "created_at": a.created_at,
            }
            for a in recent
        ]
    return out


# ---------------------------------------------------------------------- reports
def _safe(value: Any) -> Any:
    """Neutralise spreadsheet formula injection in exported text."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def enquiries_csv(db: Session, staff: StaffContext, **filters: Any) -> str:
    stmt = (
        apply_filters(enquiry_query(staff), **filters)
        .order_by(Enquiry.created_at)
        .limit(MAX_EXPORT_ROWS)
    )
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "reference",
            "type",
            "status",
            "priority",
            "source",
            "subject",
            "company",
            "contact_name",
            "contact_email",
            "assigned_user_id",
            "next_follow_up_at",
            "created_at",
        ]
    )
    for e, c, co in db.execute(stmt).all():
        w.writerow(
            [
                _safe(v)
                for v in [
                    e.reference_number,
                    e.enquiry_type.value,
                    e.status.value,
                    e.priority.value,
                    e.source,
                    e.subject,
                    co.legal_name if co else "",
                    c.full_name,
                    c.business_email,
                    e.assigned_user_id or "",
                    e.next_follow_up_at or "",
                    e.created_at,
                ]
            ]
        )
    _audit(
        db,
        staff,
        "report",
        uuid.uuid4(),
        "admin.report_exported",
        {"report": "enquiries", "filters": sorted(k for k, v in filters.items() if v)},
    )
    db.commit()
    return buf.getvalue()


def applications_csv(
    db: Session,
    staff: StaffContext,
    status: PortalStatus | None,
    created_from: datetime | None,
    created_to: datetime | None,
) -> str:
    stmt = (
        select(PortalApplication, PartnerOrganization)
        .join(PartnerOrganization, PartnerOrganization.id == PortalApplication.organization_id)
        .where(PortalApplication.status != PortalStatus.DRAFT)
    )
    if status:
        stmt = stmt.where(PortalApplication.status == status)
    if created_from:
        stmt = stmt.where(PortalApplication.created_at >= created_from)
    if created_to:
        stmt = stmt.where(PortalApplication.created_at < created_to)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "reference",
            "organization",
            "pathway",
            "status",
            "assigned_reviewer_id",
            "submissions",
            "submitted_at",
            "decided_at",
        ]
    )
    for a, o in db.execute(
        stmt.order_by(PortalApplication.created_at).limit(MAX_EXPORT_ROWS)
    ).all():
        w.writerow(
            [
                _safe(v)
                for v in [
                    a.reference,
                    o.legal_name,
                    a.pathway.value,
                    a.status.value,
                    a.assigned_reviewer_id or "",
                    a.submission_count,
                    a.submitted_at or "",
                    a.decided_at or "",
                ]
            ]
        )
    _audit(db, staff, "report", uuid.uuid4(), "admin.report_exported", {"report": "applications"})
    db.commit()
    return buf.getvalue()
