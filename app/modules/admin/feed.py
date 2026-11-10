"""Staff in-app notification feed: creation helper and the signed-in staff member's own feed."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.common.pagination import PageDep, page_meta
from app.common.responses import ApiResponse, ErrorResponse, ok
from app.common.utilities import utcnow
from app.core.exceptions import NotFoundError
from app.database.dependencies import DbSession
from app.modules.admin.models import StaffNotification
from app.modules.auth.dependencies import StaffContext, require_staff

router = APIRouter(prefix="/admin/feed", tags=["admin-feed"])
_ERR: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
}
AnyStaff = Annotated[StaffContext, Depends(require_staff())]


def notify_staff(
    db: Session,
    user_id: uuid.UUID,
    kind: str,
    title: str,
    *,
    record_type: str | None = None,
    record_id: uuid.UUID | None = None,
    is_strategic: bool = False,
) -> None:
    """Add a feed item. Flushes only: the caller's transaction decides whether it persists."""
    db.add(
        StaffNotification(
            user_id=user_id,
            kind=kind,
            title=title,
            record_type=record_type,
            record_id=record_id,
            is_strategic=is_strategic,
        )
    )
    db.flush()


class FeedItemOut(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    record_type: str | None
    record_id: uuid.UUID | None
    is_strategic: bool
    created_at: datetime
    read_at: datetime | None
    is_read: bool
    archived_at: datetime | None


def _out(n: StaffNotification) -> FeedItemOut:
    return FeedItemOut(
        id=n.id,
        kind=n.kind,
        title=n.title,
        record_type=n.record_type,
        record_id=n.record_id,
        is_strategic=n.is_strategic,
        created_at=n.created_at,
        read_at=n.read_at,
        is_read=n.read_at is not None,
        archived_at=n.archived_at,
    )


def _mine(staff: StaffContext) -> list[Any]:
    return [StaffNotification.user_id == staff.user.id]


@router.get(
    "",
    response_model=ApiResponse[list[FeedItemOut]],
    responses=_ERR,
    summary="Your own notification feed (meta.unread counts unread, non-archived items)",
)
def list_feed(
    staff: AnyStaff,
    db: DbSession,
    page: PageDep,
    unread: Annotated[bool, Query()] = False,
    archived: Annotated[bool, Query(description="Show archived items instead")] = False,
) -> ApiResponse[list[FeedItemOut]]:
    live = [*_mine(staff), StaffNotification.archived_at.is_(None)]
    unread_count = db.execute(
        select(func.count())
        .select_from(StaffNotification)
        .where(*live, StaffNotification.read_at.is_(None))
    ).scalar_one()
    conds = _mine(staff) + (
        [StaffNotification.archived_at.is_not(None)]
        if archived
        else [StaffNotification.archived_at.is_(None)]
    )
    if unread:
        conds.append(StaffNotification.read_at.is_(None))
    stmt = select(StaffNotification).where(*conds)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(StaffNotification.created_at.desc(), StaffNotification.id.desc())
        .limit(page.page_size)
        .offset(page.offset)
    ).scalars()
    return ok([_out(n) for n in rows], meta={**page_meta(page, total), "unread": unread_count})


def _own(db: Session, staff: StaffContext, item_id: uuid.UUID) -> StaffNotification:
    n = db.execute(
        select(StaffNotification).where(StaffNotification.id == item_id, *_mine(staff))
    ).scalar_one_or_none()
    if n is None:
        raise NotFoundError("Notification not found")  # other people's items look the same
    return n


@router.post(
    "/read-all",
    response_model=ApiResponse[dict[str, int]],
    responses=_ERR,
    summary="Mark all as read",
)
def read_all(staff: AnyStaff, db: DbSession) -> ApiResponse[dict[str, int]]:
    result = db.execute(
        update(StaffNotification)
        .where(*_mine(staff), StaffNotification.read_at.is_(None))
        .values(read_at=utcnow())
    )
    db.commit()
    return ok({"marked": int(getattr(result, "rowcount", 0))})


@router.post(
    "/{item_id}/read",
    response_model=ApiResponse[FeedItemOut],
    responses=_ERR,
    summary="Mark one as read",
)
def mark_read(item_id: uuid.UUID, staff: AnyStaff, db: DbSession) -> ApiResponse[FeedItemOut]:
    n = _own(db, staff, item_id)
    if n.read_at is None:
        n.read_at = utcnow()
        db.commit()
    return ok(_out(n))


@router.post(
    "/{item_id}/archive",
    response_model=ApiResponse[FeedItemOut],
    responses=_ERR,
    summary="Archive one item",
)
def archive(item_id: uuid.UUID, staff: AnyStaff, db: DbSession) -> ApiResponse[FeedItemOut]:
    n = _own(db, staff, item_id)
    if n.archived_at is None:
        n.archived_at = utcnow()
        if n.read_at is None:
            n.read_at = n.archived_at
        db.commit()
    return ok(_out(n))
