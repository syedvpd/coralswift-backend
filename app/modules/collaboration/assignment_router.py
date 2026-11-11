"""Explicit organisation -> BDM assignment (D45). Super administrator only; BDMs cannot assign
themselves. Assignment and removal are audited and the history is kept."""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.common.responses import ApiResponse, ErrorResponse, ok
from app.common.utilities import utcnow
from app.core.exceptions import AppError, NotFoundError
from app.database.dependencies import DbSession
from app.modules.admin import lookups
from app.modules.auth.constants import StaffRole, UserStatus, UserType
from app.modules.auth.dependencies import SuperAdminDep
from app.modules.auth.models import User
from app.modules.collaboration.models import OrganizationBdmAssignment
from app.modules.enquiries.activity import log_activity
from app.modules.enquiries.constants import ActorType
from app.modules.organizations.models import PartnerOrganization

router = APIRouter(prefix="/admin/organizations", tags=["admin-organizations"])
_ERR: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
}


class AssignIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID


class AssignmentOut(BaseModel):
    user_id: uuid.UUID
    user_name: str | None
    assigned_by_name: str | None
    assigned_at: datetime
    removed_at: datetime | None
    removed_by_name: str | None
    is_active: bool


def _rows(db: DbSession, org_id: uuid.UUID) -> list[AssignmentOut]:
    rows = list(
        db.execute(
            select(OrganizationBdmAssignment)
            .where(OrganizationBdmAssignment.organization_id == org_id)
            .order_by(OrganizationBdmAssignment.assigned_at.desc())
        ).scalars()
    )
    ids = [r.user_id for r in rows] + [r.assigned_by for r in rows]
    ids += [r.removed_by for r in rows if r.removed_by]
    names = lookups.user_names(db, ids)
    return [
        AssignmentOut(
            user_id=r.user_id,
            user_name=names.get(r.user_id),
            assigned_by_name=names.get(r.assigned_by),
            assigned_at=r.assigned_at,
            removed_at=r.removed_at,
            removed_by_name=names.get(r.removed_by) if r.removed_by else None,
            is_active=r.removed_at is None,
        )
        for r in rows
    ]


def _org(db: DbSession, org_id: uuid.UUID) -> PartnerOrganization:
    org = db.get(PartnerOrganization, org_id)
    if org is None:
        raise NotFoundError("Organisation not found")
    return org


@router.get(
    "/{org_id}/bdm-assignments",
    response_model=ApiResponse[list[AssignmentOut]],
    responses=_ERR,
    summary="BDMs assigned to an organisation, with history (super administrator)",
)
def list_assignments(
    org_id: uuid.UUID, staff: SuperAdminDep, db: DbSession
) -> ApiResponse[list[AssignmentOut]]:
    return ok(_rows(db, _org(db, org_id).id))


@router.post(
    "/{org_id}/bdm-assignments",
    status_code=201,
    response_model=ApiResponse[list[AssignmentOut]],
    responses=_ERR,
    summary="Give a BDM read-only access to this organisation",
)
def assign_bdm(
    org_id: uuid.UUID, payload: AssignIn, staff: SuperAdminDep, db: DbSession
) -> ApiResponse[list[AssignmentOut]]:
    org = _org(db, org_id)
    bdm = db.get(User, payload.user_id)
    if (
        bdm is None
        or bdm.user_type is not UserType.STAFF
        or bdm.staff_role is not StaffRole.BUSINESS_DEVELOPMENT_MANAGER
        or bdm.status is not UserStatus.ACTIVE
    ):
        raise NotFoundError("Business development manager not found")
    active = db.execute(
        select(OrganizationBdmAssignment.id).where(
            OrganizationBdmAssignment.organization_id == org.id,
            OrganizationBdmAssignment.user_id == bdm.id,
            OrganizationBdmAssignment.removed_at.is_(None),
        )
    ).first()
    if active:
        raise AppError("Already assigned", status_code=409, code="ALREADY_ASSIGNED")
    row = OrganizationBdmAssignment(
        organization_id=org.id,
        user_id=bdm.id,
        assigned_by=staff.user.id,
        assigned_at=utcnow(),
    )
    db.add(row)
    db.flush()
    log_activity(
        db,
        "organization",
        org.id,
        "organization.bdm_assigned",
        {"user_id": str(bdm.id)},
        ActorType.STAFF,
        actor_user_id=staff.user.id,
        organization_id=org.id,
    )
    db.commit()
    return ok(_rows(db, org.id), "Assigned")


@router.delete(
    "/{org_id}/bdm-assignments/{user_id}",
    response_model=ApiResponse[list[AssignmentOut]],
    responses=_ERR,
    summary="Remove a BDM's access (history is kept)",
)
def remove_bdm(
    org_id: uuid.UUID, user_id: uuid.UUID, staff: SuperAdminDep, db: DbSession
) -> ApiResponse[list[AssignmentOut]]:
    org = _org(db, org_id)
    row = db.execute(
        select(OrganizationBdmAssignment)
        .where(
            OrganizationBdmAssignment.organization_id == org.id,
            OrganizationBdmAssignment.user_id == user_id,
            OrganizationBdmAssignment.removed_at.is_(None),
        )
        .with_for_update()
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("Assignment not found")
    row.removed_at, row.removed_by = utcnow(), staff.user.id
    log_activity(
        db,
        "organization",
        org.id,
        "organization.bdm_unassigned",
        {"user_id": str(user_id)},
        ActorType.STAFF,
        actor_user_id=staff.user.id,
        organization_id=org.id,
    )
    db.commit()
    return ok(_rows(db, org.id), "Removed")
