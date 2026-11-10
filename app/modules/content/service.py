"""Website content workflow (PRD s.14 content approval, s.15C FAQ, s.15E resource centre, s.15H).

draft -> in_review -> approved (super administrator) -> published (content administrator or SA).
Editing is only possible in draft; changing approved/published content means reopening it (back to
draft, unpublished), so nothing unapproved can be live. Every edit stores a version.
"""

import uuid
from datetime import datetime
from typing import Any

from fastapi import UploadFile
from sqlalchemy import Select, any_, func, literal, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.utilities import utcnow
from app.core.config import Settings
from app.core.exceptions import AppError, NotFoundError
from app.integrations.storage import Storage, StorageError
from app.modules.auth.constants import StaffRole
from app.modules.auth.dependencies import StaffContext
from app.modules.content.constants import (
    PERMISSION_REQUIRED,
    ClaimCategory,
    ClaimStatus,
    ContentType,
)
from app.modules.content.constants import ContentStatus as S
from app.modules.content.models import ContentClaim, ContentItem, ContentVersion
from app.modules.documents.files import validate_upload
from app.modules.enquiries.activity import log_activity
from app.modules.enquiries.constants import ActorType


def _audit(
    db: Session,
    staff: StaffContext,
    item: ContentItem,
    action: str,
    meta: dict[str, Any] | None = None,
) -> None:
    log_activity(
        db,
        "content",
        item.id,
        action,
        {"slug": item.slug, **(meta or {})},
        ActorType.STAFF,
        actor_user_id=staff.user.id,
    )


def _bad(msg: str, code: str = "INVALID_CONTENT_STATE") -> AppError:
    return AppError(msg, status_code=409, code=code)


def get_item(db: Session, item_id: uuid.UUID, *, lock: bool = False) -> ContentItem:
    stmt = select(ContentItem).where(ContentItem.id == item_id)
    item = db.execute(stmt.with_for_update() if lock else stmt).scalar_one_or_none()
    if item is None:
        raise NotFoundError("Content not found")
    return item


def _snapshot(db: Session, item: ContentItem, user_id: uuid.UUID) -> None:
    db.add(
        ContentVersion(
            content_id=item.id,
            version_no=item.current_version,
            title=item.title,
            summary=item.summary,
            body=item.body,
            edited_by=user_id,
            created_at=utcnow(),
        )
    )


def create(db: Session, staff: StaffContext, data: dict[str, Any]) -> ContentItem:
    if "claim_ids" in data:
        data["claim_ids"] = _check_claim_ids(db, data["claim_ids"])
    item = ContentItem(owner_id=staff.user.id, status=S.DRAFT, current_version=1, **data)
    db.add(item)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise AppError("Slug already in use", status_code=409, code="SLUG_IN_USE") from None
    _snapshot(db, item, staff.user.id)
    _audit(db, staff, item, "content.created")
    db.commit()
    return item


def update(
    db: Session, staff: StaffContext, item_id: uuid.UUID, changes: dict[str, Any]
) -> ContentItem:
    item = get_item(db, item_id, lock=True)
    if item.status is not S.DRAFT:
        raise _bad("Only drafts can be edited; reopen the content first")
    if "claim_ids" in changes:
        changes["claim_ids"] = _check_claim_ids(db, changes["claim_ids"])
    text_changed = any(k in changes for k in ("title", "summary", "body"))
    for k, v in changes.items():
        setattr(item, k, v)
    if text_changed:
        item.current_version += 1
        _snapshot(db, item, staff.user.id)
    _audit(
        db,
        staff,
        item,
        "content.updated",
        {"fields": sorted(changes), "version": item.current_version},
    )
    db.commit()
    return item


def _move(
    db: Session,
    staff: StaffContext,
    item_id: uuid.UUID,
    allowed: set[S],
    target: S,
    action: str,
    *,
    super_only: bool = False,
) -> ContentItem:
    if super_only and staff.user.staff_role is not StaffRole.SUPER_ADMINISTRATOR:
        raise AppError(
            "Only a super administrator can approve content", status_code=403, code="FORBIDDEN"
        )
    item = get_item(db, item_id, lock=True)
    if item.status not in allowed:
        raise _bad(f"Cannot move content from {item.status.value} to {target.value}")
    item.status = target
    item.scheduled_publish_at = None
    _audit(db, staff, item, action, {"to": target.value})
    return item


def submit_for_review(db: Session, staff: StaffContext, item_id: uuid.UUID) -> ContentItem:
    item = _move(db, staff, item_id, {S.DRAFT}, S.IN_REVIEW, "content.submitted")
    item.review_note = None
    db.commit()
    return item


def approve(db: Session, staff: StaffContext, item_id: uuid.UUID, note: str | None) -> ContentItem:
    item = _move(db, staff, item_id, {S.IN_REVIEW}, S.APPROVED, "content.approved", super_only=True)
    item.reviewer_id, item.last_reviewed_at, item.review_note = staff.user.id, utcnow(), note
    db.commit()
    return item


def reject(db: Session, staff: StaffContext, item_id: uuid.UUID, note: str) -> ContentItem:
    item = _move(db, staff, item_id, {S.IN_REVIEW}, S.DRAFT, "content.rejected", super_only=True)
    item.reviewer_id, item.review_note = staff.user.id, note
    db.commit()
    return item


def publish(db: Session, staff: StaffContext, item_id: uuid.UUID) -> ContentItem:
    problems = claim_problems(db, get_item(db, item_id))
    if problems:  # PRD s.10/s.28 publication gate
        raise AppError(
            "Linked claims are not cleared for publication",
            status_code=409,
            code="CLAIMS_NOT_VERIFIED",
            details=[{"claim": p} for p in problems],
        )
    item = _move(db, staff, item_id, {S.APPROVED}, S.PUBLISHED, "content.published")
    item.published_at = item.published_at or utcnow()
    db.commit()
    return item


def schedule_publish(
    db: Session, staff: StaffContext, item_id: uuid.UUID, publish_at: datetime
) -> ContentItem:
    item = get_item(db, item_id, lock=True)
    if item.status is not S.APPROVED:
        raise _bad("Only approved content can be scheduled")
    if publish_at <= utcnow():
        raise AppError(
            "Publication time must be in the future", status_code=422, code="INVALID_TIME"
        )
    problems = claim_problems(db, item)
    if problems:
        raise AppError(
            "Linked claims are not cleared for publication",
            status_code=409,
            code="CLAIMS_NOT_VERIFIED",
            details=[{"claim": problem} for problem in problems],
        )
    item.scheduled_publish_at = publish_at
    _audit(db, staff, item, "content.publication_scheduled", {"publish_at": publish_at.isoformat()})
    db.commit()
    return item


def cancel_scheduled_publish(db: Session, staff: StaffContext, item_id: uuid.UUID) -> ContentItem:
    item = get_item(db, item_id, lock=True)
    if item.scheduled_publish_at is None:
        raise _bad("Content has no scheduled publication")
    item.scheduled_publish_at = None
    _audit(db, staff, item, "content.publication_schedule_cancelled")
    db.commit()
    return item


def unpublish(db: Session, staff: StaffContext, item_id: uuid.UUID) -> ContentItem:
    item = _move(db, staff, item_id, {S.PUBLISHED}, S.APPROVED, "content.unpublished")
    db.commit()
    return item


def reopen(db: Session, staff: StaffContext, item_id: uuid.UUID) -> ContentItem:
    item = _move(
        db, staff, item_id, {S.APPROVED, S.PUBLISHED, S.ARCHIVED}, S.DRAFT, "content.reopened"
    )
    db.commit()
    return item


def archive(db: Session, staff: StaffContext, item_id: uuid.UUID) -> ContentItem:
    item = _move(
        db, staff, item_id, {S.DRAFT, S.APPROVED, S.PUBLISHED}, S.ARCHIVED, "content.archived"
    )
    db.commit()
    return item


def set_attachment(
    db: Session,
    storage: Storage,
    settings: Settings,
    staff: StaffContext,
    item_id: uuid.UUID,
    upload: UploadFile,
    version_label: str | None,
) -> ContentItem:
    """Downloadable document with a version label (PRD s.15A/E). Draft only."""
    item = get_item(db, item_id, lock=True)
    if item.status is not S.DRAFT:
        raise _bad("Only drafts can change the attachment; reopen the content first")
    data = upload.file.read(settings.max_upload_bytes + 1)
    checked = validate_upload(
        data=data,
        filename=upload.filename,
        declared_type=upload.content_type,
        max_bytes=settings.max_upload_bytes,
    )
    key = f"content/{utcnow():%Y/%m}/{uuid.uuid4().hex}.{checked.kind.extension}"
    try:
        storage.put(key, data, checked.kind.content_type)
    except StorageError:
        raise AppError(
            "File storage is unavailable", status_code=503, code="STORAGE_UNAVAILABLE"
        ) from None
    item.attachment_key, item.attachment_filename = key, checked.display_name
    item.attachment_content_type, item.attachment_size = checked.kind.content_type, checked.size
    item.attachment_checksum, item.version_label = checked.sha256, version_label
    _audit(db, staff, item, "content.attachment_set", {"size": checked.size})
    db.commit()
    return item


CONTENT_SORTS: dict[str, tuple[Any, ...]] = {
    "-updated_at": (ContentItem.updated_at.desc(), ContentItem.id.desc()),
    "updated_at": (ContentItem.updated_at.asc(), ContentItem.id.asc()),
    "-created_at": (ContentItem.created_at.desc(), ContentItem.id.desc()),
    "title": (ContentItem.title.asc(), ContentItem.id.asc()),
}


def list_admin(
    db: Session,
    limit: int,
    offset: int,
    status: S | None,
    content_type: ContentType | None,
    q: str | None,
    updated_from: datetime | None = None,
    updated_to: datetime | None = None,
    sort: str = "-updated_at",
) -> tuple[list[ContentItem], int]:
    stmt = select(ContentItem)
    if updated_from:
        stmt = stmt.where(ContentItem.updated_at >= updated_from)
    if updated_to:
        stmt = stmt.where(ContentItem.updated_at < updated_to)
    if status:
        stmt = stmt.where(ContentItem.status == status)
    if content_type:
        stmt = stmt.where(ContentItem.content_type == content_type)
    if q:
        stmt = stmt.where(ContentItem.title.ilike(_like(q), escape="\\"))
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    return list(
        db.execute(stmt.order_by(*CONTENT_SORTS[sort]).limit(limit).offset(offset)).scalars()
    ), total


def versions(db: Session, item_id: uuid.UUID) -> list[ContentVersion]:
    return list(
        db.execute(
            select(ContentVersion)
            .where(ContentVersion.content_id == item_id)
            .order_by(ContentVersion.version_no.desc())
        ).scalars()
    )


# ------------------------------------------------------------------ public
def _like(q: str) -> str:
    return "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def published_query() -> Select[ContentItem]:
    return select(ContentItem).where(ContentItem.status == S.PUBLISHED)


def search_published(
    db: Session,
    limit: int,
    offset: int,
    *,
    q: str | None,
    content_type: ContentType | None,
    category: str | None,
    tag: str | None,
) -> tuple[list[ContentItem], int]:
    stmt = published_query()
    if content_type:
        stmt = stmt.where(ContentItem.content_type == content_type)
    if category:
        stmt = stmt.where(ContentItem.category == category)
    if tag:
        stmt = stmt.where(literal(tag) == any_(ContentItem.tags))
    if q:
        pattern = _like(q)
        stmt = stmt.where(
            or_(
                ContentItem.title.ilike(pattern, escape="\\"),
                ContentItem.summary.ilike(pattern, escape="\\"),
                ContentItem.body.ilike(pattern, escape="\\"),
            )
        )
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    return list(
        db.execute(
            stmt.order_by(ContentItem.published_at.desc()).limit(limit).offset(offset)
        ).scalars()
    ), total


def get_published(db: Session, slug: str) -> ContentItem:
    item = db.execute(published_query().where(ContentItem.slug == slug)).scalar_one_or_none()
    if item is None:
        raise NotFoundError("Content not found")
    return item


def related(db: Session, item: ContentItem, limit: int = 5) -> list[ContentItem]:
    conds = [ContentItem.tags.overlap(item.tags or [])] if item.tags else []
    if item.category:
        conds.append(ContentItem.category == item.category)
    if not conds:
        return []
    stmt = (
        published_query()
        .where(ContentItem.id != item.id, or_(*conds))
        .order_by(ContentItem.published_at.desc())
        .limit(limit)
    )
    return list(db.execute(stmt).scalars())


def sitemap(db: Session) -> list[tuple[str, datetime]]:
    rows = db.execute(
        select(ContentItem.slug, ContentItem.updated_at)
        .where(ContentItem.status == S.PUBLISHED)
        .order_by(ContentItem.slug)
    ).all()
    return [(s, u) for s, u in rows]


def read_attachment(db: Session, storage: Storage, slug: str) -> tuple[bytes, ContentItem]:
    item = get_published(db, slug)
    if not item.attachment_key:
        raise NotFoundError("No attachment")
    try:
        return storage.get(item.attachment_key), item
    except StorageError:
        raise AppError(
            "File storage is unavailable", status_code=503, code="STORAGE_UNAVAILABLE"
        ) from None


# --------------------------------------------------------- claims register
def _check_claim_ids(db: Session, ids: list[Any]) -> list[str]:
    unique = list(dict.fromkeys(str(i) for i in ids))
    if unique:
        found = {
            str(c)
            for c in db.execute(
                select(ContentClaim.id).where(ContentClaim.id.in_([uuid.UUID(i) for i in unique]))
            ).scalars()
        }
        if found != set(unique):
            raise AppError("Unknown claim id", status_code=422, code="UNKNOWN_CLAIM")
    return unique


def _cleared(claim: ContentClaim) -> bool:
    if claim.evidence_status not in (ClaimStatus.VERIFIED, ClaimStatus.ILLUSTRATIVE):
        return False
    if claim.category in PERMISSION_REQUIRED:
        return claim.evidence_status is ClaimStatus.VERIFIED and claim.publication_permission
    return True


def claim_problems(db: Session, item: ContentItem) -> list[str]:
    """Why linked claims block publication (empty list = cleared)."""
    problems: list[str] = []
    for cid in item.claim_ids or []:
        claim = db.get(ContentClaim, uuid.UUID(cid))
        if claim is None:
            problems.append(f"{cid}: missing")
        elif not _cleared(claim):
            problems.append(
                f"{cid}: {claim.evidence_status.value} / permission={claim.publication_permission}"
            )
    return problems


def create_claim(db: Session, staff: StaffContext, data: dict[str, Any]) -> ContentClaim:
    claim = ContentClaim(
        owner_id=staff.user.id, evidence_status=ClaimStatus.PENDING_VERIFICATION, **data
    )
    db.add(claim)
    db.flush()
    log_activity(
        db,
        "claim",
        claim.id,
        "claim.created",
        {"category": claim.category.value},
        ActorType.STAFF,
        actor_user_id=staff.user.id,
    )
    db.commit()
    return claim


def update_claim(
    db: Session, staff: StaffContext, claim_id: uuid.UUID, changes: dict[str, Any]
) -> ContentClaim:
    """Content administrators edit text/evidence reference; only a super administrator can change
    the evidence status or publication permission."""
    claim = db.execute(
        select(ContentClaim).where(ContentClaim.id == claim_id).with_for_update()
    ).scalar_one_or_none()
    if claim is None:
        raise NotFoundError("Claim not found")
    privileged = {"evidence_status", "publication_permission"} & set(changes)
    if privileged and staff.user.staff_role is not StaffRole.SUPER_ADMINISTRATOR:
        raise AppError(
            "Only a super administrator can verify claims", status_code=403, code="FORBIDDEN"
        )
    was_cleared = _cleared(claim)
    for k, v in changes.items():
        setattr(claim, k, v)
    if privileged:
        claim.last_reviewed_at = utcnow()
    pulled = 0
    if was_cleared and not _cleared(
        claim
    ):  # withdrawn/outdated claim: nothing relying on it stays live
        stmt = (
            select(ContentItem)
            .where(
                ContentItem.status.in_([S.APPROVED, S.PUBLISHED]),
                ContentItem.claim_ids.contains([str(claim.id)]),
            )
            .with_for_update()
        )
        for item in db.execute(stmt).scalars():
            item.status = S.DRAFT
            pulled += 1
            _audit(db, staff, item, "content.pulled_claim_not_cleared", {"claim": str(claim.id)})
    log_activity(
        db,
        "claim",
        claim.id,
        "claim.updated",
        {"fields": sorted(changes), "content_pulled": pulled},
        ActorType.STAFF,
        actor_user_id=staff.user.id,
    )
    db.commit()
    return claim


def list_claims(
    db: Session, limit: int, offset: int, status: ClaimStatus | None, category: ClaimCategory | None
) -> tuple[list[ContentClaim], int]:
    stmt = select(ContentClaim)
    if status:
        stmt = stmt.where(ContentClaim.evidence_status == status)
    if category:
        stmt = stmt.where(ContentClaim.category == category)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(ContentClaim.created_at.desc()).limit(limit).offset(offset)
    ).scalars()
    return list(rows), total
