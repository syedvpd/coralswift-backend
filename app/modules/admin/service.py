"""Phase 3 admin operations. Permission model (PRD s.14):

* super_administrator: everything below, including strategic (M&A) enquiries, financial data, users.
* business_development_manager: general / project / partner enquiries (assignment, follow-ups),
  limited partner view. Strategic enquiries and financial data are NOT visible (restricted by
  default; whether BDMs handle "partnership discussions" is a business decision).
Partner Reviewer keeps the Phase 2 reviewer API only.
"""

import csv
import io
import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Select, case, exists, func, or_, select
from sqlalchemy.orm import Session

from app.common.utilities import utcnow
from app.core.exceptions import AppError, NotFoundError
from app.integrations.storage import Storage, StorageError
from app.modules.admin import lookups
from app.modules.admin.feed import notify_staff
from app.modules.admin.models import EnquiryFollowUp
from app.modules.applications.constants import TERMINAL, PortalStatus
from app.modules.applications.models import PortalApplication
from app.modules.auth import service as auth_service
from app.modules.auth.constants import StaffRole, UserStatus, UserType
from app.modules.auth.dependencies import StaffContext
from app.modules.auth.models import User
from app.modules.documents.constants import EvidenceCategory, OwnerType
from app.modules.documents.models import Document
from app.modules.engagement.models import MeetingRequest
from app.modules.enquiries.activity import log_activity
from app.modules.enquiries.constants import ActorType, EnquiryStatus, EnquiryType, Priority
from app.modules.enquiries.models import Activity, Company, Contact, Enquiry
from app.modules.notifications.constants import DeliveryStatus
from app.modules.notifications.models import Notification
from app.modules.organizations.models import PartnerOrganization
from app.modules.partners.models import PartnerApplication
from app.modules.projects.constants import ProjectCategory, category_group
from app.modules.projects.models import ProjectEnquiry
from app.modules.strategic.constants import DiscussionType
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
    assigned_any: bool = False,
    category: ProjectCategory | None = None,
    discussion_type: DiscussionType | None = None,
    project_group: str | None = None,
    updated_from: datetime | None = None,
    updated_to: datetime | None = None,
) -> Select[Enquiry, Contact, Company]:
    if assigned_any:
        stmt = stmt.where(Enquiry.assigned_user_id.is_not(None))
    if category:
        stmt = stmt.where(
            exists().where(
                ProjectEnquiry.enquiry_id == Enquiry.id,
                ProjectEnquiry.project_category == category,
            )
        )
    if discussion_type:
        stmt = stmt.where(
            exists().where(
                StrategicEnquiry.enquiry_id == Enquiry.id,
                StrategicEnquiry.discussion_type == discussion_type,
            )
        )
    if project_group:
        group = {c for c in ProjectCategory if category_group(c) == project_group}
        stmt = stmt.where(
            exists().where(
                ProjectEnquiry.enquiry_id == Enquiry.id,
                ProjectEnquiry.project_category.in_(group),
            )
        )
    if updated_from:
        stmt = stmt.where(Enquiry.updated_at >= updated_from)
    if updated_to:
        stmt = stmt.where(Enquiry.updated_at < updated_to)
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
        "updated_at": e.updated_at,
        "contact_phone": c.phone,
        "first_response_at": e.first_response_at,
        "response_due_at": e.response_due_at,
    }


def enrich_rows(db: Session, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add owner names and the category (project category / strategic discussion type)."""
    names = lookups.user_names(db, (r["assigned_user_id"] for r in rows))
    ids = [r["id"] for r in rows]
    cats: dict[uuid.UUID, str] = {}
    if ids:
        for eid, value in db.execute(
            select(ProjectEnquiry.enquiry_id, ProjectEnquiry.project_category).where(
                ProjectEnquiry.enquiry_id.in_(ids)
            )
        ):
            cats[eid] = value.value
        for eid, dtype in db.execute(
            select(StrategicEnquiry.enquiry_id, StrategicEnquiry.discussion_type).where(
                StrategicEnquiry.enquiry_id.in_(ids)
            )
        ):
            cats[eid] = dtype.value
    for r in rows:
        r["assigned_user_name"] = (
            names.get(r["assigned_user_id"]) if r["assigned_user_id"] else None
        )
        r["category"] = cats.get(r["id"])
    return rows


ENQUIRY_SORTS: dict[str, tuple[Any, ...]] = {
    "-created_at": (Enquiry.created_at.desc(), Enquiry.id.desc()),
    "created_at": (Enquiry.created_at.asc(), Enquiry.id.asc()),
    "-updated_at": (Enquiry.updated_at.desc(), Enquiry.id.desc()),
    "updated_at": (Enquiry.updated_at.asc(), Enquiry.id.asc()),
    "next_follow_up_at": (Enquiry.next_follow_up_at.asc().nulls_last(), Enquiry.id.asc()),
    "response_due_at": (Enquiry.response_due_at.asc().nulls_last(), Enquiry.id.asc()),
}


def list_enquiries(
    db: Session, staff: StaffContext, limit: int, offset: int, **filters: Any
) -> tuple[list[dict[str, Any]], int]:
    sort = filters.pop("sort", "-created_at")
    stmt = apply_filters(enquiry_query(staff), **filters)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(stmt.order_by(*ENQUIRY_SORTS[sort]).limit(limit).offset(offset)).all()
    return enrich_rows(db, [row_dict(*r) for r in rows]), total


def enquiry_workload(db: Session, staff: StaffContext) -> dict[str, Any]:
    """Count open enquiry work by assignee without applying capacity or assignment rules."""
    now = utcnow()
    open_condition = Enquiry.status != EnquiryStatus.CLOSED
    overdue_condition = open_condition & (Enquiry.next_follow_up_at < now)
    sla_condition = (
        open_condition & (Enquiry.response_due_at < now) & Enquiry.first_response_at.is_(None)
    )
    rows = db.execute(
        select(
            Enquiry.assigned_user_id,
            func.count().label("open_enquiries"),
            func.count(case((overdue_condition, 1))).label("overdue_follow_ups"),
            func.count(case((sla_condition, 1))).label("sla_breached"),
        )
        .where(Enquiry.enquiry_type.in_(visible_types(staff)), open_condition)
        .group_by(Enquiry.assigned_user_id)
        .order_by(Enquiry.assigned_user_id)
    ).all()
    names = lookups.user_names(db, (row.assigned_user_id for row in rows if row.assigned_user_id))
    result = [
        {
            "assignee_id": row.assigned_user_id,
            "assignee_name": names.get(row.assigned_user_id) if row.assigned_user_id else None,
            "open_enquiries": row.open_enquiries,
            "overdue_follow_ups": row.overdue_follow_ups,
            "sla_breached": row.sla_breached,
        }
        for row in rows
    ]
    return {
        "rows": result,
        "totals": {
            "open_enquiries": sum(row["open_enquiries"] for row in result),
            "overdue_follow_ups": sum(row["overdue_follow_ups"] for row in result),
            "sla_breached": sum(row["sla_breached"] for row in result),
        },
    }


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
        "follow_ups": followup_dicts(db, list_followups(db, e.id)),
    }


def list_enquiry_documents(
    db: Session, staff: StaffContext, enquiry_id: uuid.UUID, limit: int, offset: int
) -> tuple[list[dict[str, Any]], int]:
    get_visible(db, staff, enquiry_id)
    stmt = select(Document).where(
        Document.owner_type == OwnerType.ENQUIRY, Document.owner_id == enquiry_id
    )
    if not _is_super(staff):
        stmt = stmt.where(Document.category != EvidenceCategory.FINANCIAL_STATEMENTS)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    page = db.execute(
        stmt.order_by(Document.uploaded_at, Document.id).limit(limit).offset(offset)
    ).scalars()
    return (
        [
            {
                "id": d.id,
                "original_filename": d.original_filename,
                "content_type": d.content_type,
                "file_size": d.file_size,
                "category": d.category.value if d.category else None,
                "classification": d.classification.value,
                "upload_status": d.upload_status.value,
            }
            for d in page
        ],
        total,
    )


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


def _check_owner(db: Session, e: Enquiry, user_id: uuid.UUID | None) -> None:
    if user_id is None:
        return
    owner = db.get(User, user_id)
    allowed = {StaffRole.BUSINESS_DEVELOPMENT_MANAGER, StaffRole.SUPER_ADMINISTRATOR}
    if e.enquiry_type is EnquiryType.STRATEGIC:
        allowed = {StaffRole.SUPER_ADMINISTRATOR}  # confidential records: super administrators only
    if owner is None or owner.status is not UserStatus.ACTIVE or owner.staff_role not in allowed:
        raise AppError("Not a valid owner for this enquiry", status_code=422, code="INVALID_OWNER")


def assign_enquiry(
    db: Session, staff: StaffContext, enquiry_id: uuid.UUID, user_id: uuid.UUID | None
) -> Enquiry:
    e = get_visible(db, staff, enquiry_id, lock=True)
    _check_owner(db, e, user_id)
    previous = e.assigned_user_id
    e.assigned_user_id = user_id
    if user_id is not None and user_id != previous and user_id != staff.user.id:
        notify_staff(
            db,
            user_id,
            "enquiry_assigned",
            f"Enquiry {e.reference_number} was assigned to you",
            record_type="enquiry",
            record_id=e.id,
            is_strategic=e.enquiry_type is EnquiryType.STRATEGIC,
        )
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
            EnquiryFollowUp.enquiry_id == e.id,
            EnquiryFollowUp.completed_at.is_(None),
            EnquiryFollowUp.cancelled_at.is_(None),
        )
    ).scalar_one()


def add_followup(
    db: Session,
    staff: StaffContext,
    enquiry_id: uuid.UUID,
    note: str,
    due_at: datetime | None,
    kind: str = "follow_up",
    assignee_id: uuid.UUID | None = None,
) -> EnquiryFollowUp:
    e = get_visible(db, staff, enquiry_id, lock=True)
    if due_at is not None and kind != "follow_up":
        raise AppError(
            "Only follow-ups have a due date", status_code=422, code="DUE_DATE_NOT_ALLOWED"
        )
    _check_owner(db, e, assignee_id)
    f = EnquiryFollowUp(
        enquiry_id=e.id,
        author_id=staff.user.id,
        note=note,
        due_at=due_at,
        kind=kind,
        assignee_id=assignee_id,
        created_at=utcnow(),
    )
    db.add(f)
    db.flush()
    _tell_assignee(db, staff, e, f)
    if kind != "note":  # an internal note is not a response to the requester
        mark_response(e)
    _recompute_next(db, e)
    _audit(
        db,
        staff,
        "enquiry",
        e.id,
        "admin.followup_added",
        {"followup_id": str(f.id), "kind": kind, "due": due_at is not None},
    )
    db.commit()
    return f


def _tell_assignee(db: Session, staff: StaffContext, e: Enquiry, f: EnquiryFollowUp) -> None:
    if f.assignee_id is not None and f.assignee_id != staff.user.id:
        notify_staff(
            db,
            f.assignee_id,
            "followup_assigned",
            f"A follow-up on {e.reference_number} was assigned to you",
            record_type="enquiry",
            record_id=e.id,
            is_strategic=e.enquiry_type is EnquiryType.STRATEGIC,
        )


def _open_followup(db: Session, e: Enquiry, followup_id: uuid.UUID) -> EnquiryFollowUp:
    f = db.execute(
        select(EnquiryFollowUp)
        .where(EnquiryFollowUp.id == followup_id, EnquiryFollowUp.enquiry_id == e.id)
        .with_for_update()
    ).scalar_one_or_none()
    if f is None:
        raise NotFoundError("Follow-up not found")
    if f.completed_at is not None or f.cancelled_at is not None:
        raise AppError(
            "Only open follow-ups can be changed", status_code=409, code="FOLLOWUP_CLOSED"
        )
    return f


def update_followup(
    db: Session,
    staff: StaffContext,
    enquiry_id: uuid.UUID,
    followup_id: uuid.UUID,
    changes: dict[str, Any],
) -> EnquiryFollowUp:
    e = get_visible(db, staff, enquiry_id, lock=True)
    f = _open_followup(db, e, followup_id)
    if "due_at" in changes and changes["due_at"] is not None and f.kind != "follow_up":
        raise AppError(
            "Only follow-ups have a due date", status_code=422, code="DUE_DATE_NOT_ALLOWED"
        )
    if changes.get("note") is None:
        changes.pop("note", None)  # the note cannot be cleared
    if "assignee_id" in changes:
        _check_owner(db, e, changes["assignee_id"])
    previous_assignee = f.assignee_id
    for name, value in changes.items():
        setattr(f, name, value)
    db.flush()
    if f.assignee_id != previous_assignee:
        _tell_assignee(db, staff, e, f)
    _recompute_next(db, e)
    _audit(
        db,
        staff,
        "enquiry",
        e.id,
        "admin.followup_updated",
        {"followup_id": str(f.id), "fields": sorted(changes)},
    )
    db.commit()
    return f


def cancel_followup(
    db: Session, staff: StaffContext, enquiry_id: uuid.UUID, followup_id: uuid.UUID
) -> EnquiryFollowUp:
    e = get_visible(db, staff, enquiry_id, lock=True)
    f = _open_followup(db, e, followup_id)
    f.cancelled_at = utcnow()
    db.flush()
    _recompute_next(db, e)
    _audit(db, staff, "enquiry", e.id, "admin.followup_cancelled", {"followup_id": str(f.id)})
    db.commit()
    return f


def followup_dicts(
    db: Session, rows: list[EnquiryFollowUp], refs: dict[uuid.UUID, str] | None = None
) -> list[dict[str, Any]]:
    names = lookups.user_names(db, [x for f in rows for x in (f.author_id, f.assignee_id)])
    return [
        {
            "id": f.id,
            "author_id": f.author_id,
            "note": f.note,
            "due_at": f.due_at,
            "completed_at": f.completed_at,
            "created_at": f.created_at,
            "kind": f.kind,
            "status": f.status,
            "cancelled_at": f.cancelled_at,
            "assignee_id": f.assignee_id,
            "author_name": names.get(f.author_id),
            "assignee_name": names.get(f.assignee_id) if f.assignee_id else None,
            "enquiry_id": f.enquiry_id,
            "enquiry_reference": (refs or {}).get(f.enquiry_id),
        }
        for f in rows
    ]


def list_all_followups(
    db: Session,
    staff: StaffContext,
    limit: int,
    offset: int,
    *,
    status: str | None,
    kind: str | None,
    assignee_id: uuid.UUID | None,
    mine: bool,
    due_from: datetime | None,
    due_to: datetime | None,
    sort_desc: bool,
) -> tuple[list[dict[str, Any]], int, dict[str, int]]:
    """Follow-ups across every enquiry this staff member may see, with open/overdue counts."""
    base = (
        select(EnquiryFollowUp, Enquiry.reference_number)
        .join(Enquiry, Enquiry.id == EnquiryFollowUp.enquiry_id)
        .where(Enquiry.enquiry_type.in_(visible_types(staff)))
    )
    now = utcnow()
    open_ = (EnquiryFollowUp.completed_at.is_(None), EnquiryFollowUp.cancelled_at.is_(None))
    counts_src = base.subquery()
    c = counts_src.c
    counts = {
        "open": db.execute(
            select(func.count())
            .select_from(counts_src)
            .where(c.completed_at.is_(None), c.cancelled_at.is_(None))
        ).scalar_one(),
        "overdue": db.execute(
            select(func.count())
            .select_from(counts_src)
            .where(c.completed_at.is_(None), c.cancelled_at.is_(None), c.due_at < now)
        ).scalar_one(),
        "upcoming": db.execute(
            select(func.count())
            .select_from(counts_src)
            .where(c.completed_at.is_(None), c.cancelled_at.is_(None), c.due_at >= now)
        ).scalar_one(),
        "completed": db.execute(
            select(func.count()).select_from(counts_src).where(c.completed_at.is_not(None))
        ).scalar_one(),
        "cancelled": db.execute(
            select(func.count()).select_from(counts_src).where(c.cancelled_at.is_not(None))
        ).scalar_one(),
    }
    stmt = base
    if status == "open":
        stmt = stmt.where(*open_)
    elif status == "completed":
        stmt = stmt.where(EnquiryFollowUp.completed_at.is_not(None))
    elif status == "cancelled":
        stmt = stmt.where(EnquiryFollowUp.cancelled_at.is_not(None))
    if kind:
        stmt = stmt.where(EnquiryFollowUp.kind == kind)
    if assignee_id:
        stmt = stmt.where(EnquiryFollowUp.assignee_id == assignee_id)
    if mine:
        stmt = stmt.where(
            or_(
                EnquiryFollowUp.assignee_id == staff.user.id,
                EnquiryFollowUp.author_id == staff.user.id,
            )
        )
    if due_from:
        stmt = stmt.where(EnquiryFollowUp.due_at >= due_from)
    if due_to:
        stmt = stmt.where(EnquiryFollowUp.due_at < due_to)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    order = (
        (EnquiryFollowUp.due_at.desc().nulls_last(), EnquiryFollowUp.id.desc())
        if sort_desc
        else (EnquiryFollowUp.due_at.asc().nulls_last(), EnquiryFollowUp.id.asc())
    )
    rows = db.execute(stmt.order_by(*order).limit(limit).offset(offset)).all()
    refs = {f.enquiry_id: ref for f, ref in rows}
    return followup_dicts(db, [f for f, _ in rows], refs), total, counts


def enquiry_activity(
    db: Session,
    staff: StaffContext,
    enquiry_id: uuid.UUID,
    limit: int,
    offset: int,
    action: str | None,
) -> tuple[list[dict[str, Any]], int]:
    e = get_visible(db, staff, enquiry_id)  # same visibility rule as the enquiry itself
    stmt = select(Activity).where(Activity.record_type == "enquiry", Activity.record_id == e.id)
    if action:
        stmt = stmt.where(Activity.action.ilike(_like(action), escape="\\"))
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    acts = list(
        db.execute(
            stmt.order_by(Activity.created_at.desc(), Activity.id.desc())
            .limit(limit)
            .offset(offset)
        ).scalars()
    )
    names = lookups.user_names(db, (a.actor_user_id for a in acts))
    return [
        {
            "id": a.id,
            "action": a.action,
            "actor_type": a.actor_type.value,
            "actor_user_id": a.actor_user_id,
            "actor_name": names.get(a.actor_user_id) if a.actor_user_id else None,
            "meta": a.meta,
            "created_at": a.created_at,
        }
        for a in acts
    ], total


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
ORG_SORTS: dict[str, tuple[Any, ...]] = {
    "-created_at": (PartnerOrganization.created_at.desc(), PartnerOrganization.id.desc()),
    "created_at": (PartnerOrganization.created_at.asc(), PartnerOrganization.id.asc()),
    "-updated_at": (PartnerOrganization.updated_at.desc(), PartnerOrganization.id.desc()),
    "legal_name": (PartnerOrganization.legal_name.asc(), PartnerOrganization.id.asc()),
}


def list_orgs(
    db: Session,
    limit: int,
    offset: int,
    q: str | None,
    status: str | None,
    country: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    sort: str = "-created_at",
) -> tuple[list[dict[str, Any]], int]:
    stmt = select(PartnerOrganization)
    if country:
        stmt = stmt.where(PartnerOrganization.country == country)
    if created_from:
        stmt = stmt.where(PartnerOrganization.created_at >= created_from)
    if created_to:
        stmt = stmt.where(PartnerOrganization.created_at < created_to)
    if q:
        stmt = stmt.where(PartnerOrganization.legal_name.ilike(_like(q.strip()), escape="\\"))
    if status:
        stmt = stmt.where(PartnerOrganization.status == status)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    orgs = list(db.execute(stmt.order_by(*ORG_SORTS[sort]).limit(limit).offset(offset)).scalars())
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
            "updated_at": o.updated_at,
            "primary_contact": o.authorized_contacts[0] if o.authorized_contacts else None,
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
        "trading_name": o.trading_name,
        "company_type": o.company_type,
        "state": o.state,
        "city": o.city,
        "primary_industry": o.primary_industry,
        "competencies": o.competencies,
        "operating_model": o.operating_model,
        "coverage": o.coverage,
        "years_of_experience": o.years_of_experience,
        "offices": o.offices,
        "workforce": o.workforce,
        "financial_period": o.financial_period,
    }
    if _is_super(staff):  # financial / identifying data
        profile.update(
            registration_number=o.registration_number,
            annual_turnover_inr_crore=o.annual_turnover_inr_crore,
            client_references=o.client_references,
            authorized_contacts=o.authorized_contacts,
            additional_contacts=o.additional_contacts,
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
STAFF_SORTS: dict[str, tuple[Any, ...]] = {
    "created_at": (User.created_at.asc(), User.id.asc()),
    "-created_at": (User.created_at.desc(), User.id.desc()),
    "full_name": (User.full_name.asc(), User.id.asc()),
    "-last_login_at": (User.last_login_at.desc().nulls_last(), User.id.desc()),
}


def list_staff(
    db: Session,
    role: StaffRole | None,
    *,
    q: str | None = None,
    status: UserStatus | None = None,
    sort: str = "created_at",
    limit: int | None = None,
    offset: int = 0,
) -> tuple[list[User], int]:
    stmt = select(User).where(User.user_type == UserType.STAFF)
    if role:
        stmt = stmt.where(User.staff_role == role)
    if status:
        stmt = stmt.where(User.status == status)
    if q:
        pattern = _like(q.strip())
        stmt = stmt.where(
            or_(User.email.ilike(pattern, escape="\\"), User.full_name.ilike(pattern, escape="\\"))
        )
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    stmt = stmt.order_by(*STAFF_SORTS[sort]).offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(db.execute(stmt).scalars()), total


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


def get_staff(db: Session, user_id: uuid.UUID) -> User:
    u = db.execute(
        select(User).where(User.id == user_id, User.user_type == UserType.STAFF)
    ).scalar_one_or_none()
    if u is None:
        raise NotFoundError("Staff user not found")
    return u


def update_staff_profile(
    db: Session, staff: StaffContext, user_id: uuid.UUID, full_name: str
) -> User:
    u = _staff(db, user_id)
    if u.full_name != full_name:
        u.full_name = full_name
        _audit(db, staff, "user", u.id, "admin.staff_profile_updated", {"fields": ["full_name"]})
    db.commit()
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
    q: str | None = None,
    ascending: bool = False,
) -> tuple[list[Activity], int]:
    stmt = select(Activity)
    if q:
        stmt = stmt.where(
            or_(
                Activity.action.ilike(_like(q), escape="\\"),
                Activity.record_type.ilike(_like(q), escape="\\"),
            )
        )
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
    # id is the tie-breaker so pages are stable when rows share a timestamp
    order = (
        (Activity.created_at.asc(), Activity.id.asc())
        if ascending
        else (Activity.created_at.desc(), Activity.id.desc())
    )
    return list(db.execute(stmt.order_by(*order).limit(limit).offset(offset)).scalars()), total


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
    sort = filters.pop("sort", "created_at")  # same filters as the list; the export is capped
    stmt = (
        apply_filters(enquiry_query(staff), **filters)
        .order_by(*ENQUIRY_SORTS[sort if sort in ENQUIRY_SORTS else "created_at"])
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


def audit_csv(
    db: Session,
    staff: StaffContext,
    *,
    record_type: str | None,
    action: str | None,
    actor_user_id: uuid.UUID | None,
    organization_id: uuid.UUID | None,
    created_from: datetime | None,
    created_to: datetime | None,
    q: str | None,
    ascending: bool,
) -> str:
    rows, _total = list_audit(
        db,
        MAX_EXPORT_ROWS,
        0,
        record_type=record_type,
        action=action,
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        created_from=created_from,
        created_to=created_to,
        q=q,
        ascending=ascending,
    )
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "id",
            "record_type",
            "record_id",
            "action",
            "actor_type",
            "actor_user_id",
            "organization_id",
            "request_id",
            "ip_address",
            "user_agent",
            "outcome",
            "metadata",
            "created_at",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                _safe(value)
                for value in [
                    row.id,
                    row.record_type,
                    row.record_id,
                    row.action,
                    row.actor_type.value,
                    row.actor_user_id or "",
                    row.organization_id or "",
                    row.request_id or "",
                    row.ip_address or "",
                    row.user_agent or "",
                    row.outcome,
                    json.dumps(row.meta, sort_keys=True),
                    row.created_at,
                ]
            ]
        )
    _audit(db, staff, "report", uuid.uuid4(), "admin.report_exported", {"report": "audit"})
    db.commit()
    return buf.getvalue()
