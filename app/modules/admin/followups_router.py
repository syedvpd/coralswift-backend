"""Follow-ups across enquiries, follow-up changes, and the enquiry activity feed (gap closure)."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query

from app.common.pagination import PageDep, page_meta
from app.common.responses import ApiResponse, ErrorResponse, ok
from app.database.dependencies import DbSession
from app.modules.admin import service
from app.modules.admin.schemas import ActivityOut, FollowUpOut, FollowUpUpdate
from app.modules.auth.constants import StaffRole
from app.modules.auth.dependencies import StaffContext, require_staff

router = APIRouter(prefix="/admin", tags=["admin-followups"])
_ERR: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}
AdminDep = Annotated[
    StaffContext,
    Depends(require_staff(StaffRole.SUPER_ADMINISTRATOR, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)),
]


@router.get(
    "/follow-ups",
    response_model=ApiResponse[list[FollowUpOut]],
    responses=_ERR,
    summary="Follow-ups and communications across visible enquiries (counts in meta)",
)
def list_follow_ups(
    staff: AdminDep,
    db: DbSession,
    page: PageDep,
    status: Annotated[Literal["open", "completed", "cancelled"] | None, Query()] = None,
    kind: Annotated[Literal["note", "follow_up", "communication"] | None, Query()] = None,
    assignee_id: Annotated[uuid.UUID | None, Query()] = None,
    mine: Annotated[bool, Query(description="Assigned to or written by me")] = False,
    due_from: Annotated[datetime | None, Query()] = None,
    due_to: Annotated[datetime | None, Query()] = None,
    sort: Annotated[Literal["due_at", "-due_at"], Query()] = "due_at",
) -> ApiResponse[list[FollowUpOut]]:
    rows, total, counts = service.list_all_followups(
        db,
        staff,
        page.page_size,
        page.offset,
        status=status,
        kind=kind,
        assignee_id=assignee_id,
        mine=mine,
        due_from=due_from,
        due_to=due_to,
        sort_desc=sort == "-due_at",
    )
    return ok([FollowUpOut(**r) for r in rows], meta={**page_meta(page, total), "counts": counts})


@router.patch(
    "/enquiries/{enquiry_id}/follow-ups/{followup_id}",
    response_model=ApiResponse[FollowUpOut],
    responses=_ERR,
    summary="Edit, reschedule or reassign an open follow-up (null clears due date or assignee)",
)
def update_follow_up(
    enquiry_id: uuid.UUID,
    followup_id: uuid.UUID,
    payload: FollowUpUpdate,
    staff: AdminDep,
    db: DbSession,
) -> ApiResponse[FollowUpOut]:
    changes = {k: getattr(payload, k) for k in payload.model_fields_set}
    f = service.update_followup(db, staff, enquiry_id, followup_id, changes)
    return ok(FollowUpOut(**service.followup_dicts(db, [f])[0]), "Follow-up updated")


@router.post(
    "/enquiries/{enquiry_id}/follow-ups/{followup_id}/cancel",
    response_model=ApiResponse[FollowUpOut],
    responses=_ERR,
    summary="Cancel an open follow-up",
)
def cancel_follow_up(
    enquiry_id: uuid.UUID, followup_id: uuid.UUID, staff: AdminDep, db: DbSession
) -> ApiResponse[FollowUpOut]:
    f = service.cancel_followup(db, staff, enquiry_id, followup_id)
    return ok(FollowUpOut(**service.followup_dicts(db, [f])[0]), "Follow-up cancelled")


@router.get(
    "/enquiries/{enquiry_id}/activity",
    response_model=ApiResponse[list[ActivityOut]],
    responses=_ERR,
    summary="Status, assignment and follow-up history of one enquiry, with actor names",
)
def enquiry_activity(
    enquiry_id: uuid.UUID,
    staff: AdminDep,
    db: DbSession,
    page: PageDep,
    action: Annotated[str | None, Query(max_length=80, description="Partial match")] = None,
) -> ApiResponse[list[ActivityOut]]:
    rows, total = service.enquiry_activity(
        db, staff, enquiry_id, page.page_size, page.offset, action
    )
    return ok([ActivityOut(**r) for r in rows], meta=page_meta(page, total))
