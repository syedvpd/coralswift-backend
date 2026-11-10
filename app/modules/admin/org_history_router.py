"""Organisation history for staff: profile revisions (old/new) and the activity trail."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import and_, func, not_, select

from app.common.pagination import PageDep, page_meta
from app.common.responses import ApiResponse, ErrorResponse, ok
from app.core.exceptions import NotFoundError
from app.database.dependencies import DbSession
from app.modules.admin import lookups
from app.modules.auth.constants import StaffRole
from app.modules.auth.dependencies import StaffContext, require_staff
from app.modules.enquiries.constants import EnquiryType
from app.modules.enquiries.models import Activity, Enquiry
from app.modules.organizations.models import PartnerOrganization, PartnerProfileRevision

router = APIRouter(prefix="/admin/organizations", tags=["admin-organizations"])
_ERR: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
}
AdminDep = Annotated[
    StaffContext,
    Depends(require_staff(StaffRole.SUPER_ADMINISTRATOR, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)),
]


class RevisionRow(BaseModel):
    version: int
    changed_by: uuid.UUID
    changed_by_name: str | None
    changes: dict[str, Any]  # {field: {"old": ..., "new": ...}}
    created_at: datetime


class OrgActivityRow(BaseModel):
    id: uuid.UUID
    record_type: str
    action: str
    actor_name: str | None
    meta: dict[str, Any]
    created_at: datetime


def _org(db: DbSession, org_id: uuid.UUID) -> PartnerOrganization:
    org = db.get(PartnerOrganization, org_id)
    if org is None:
        raise NotFoundError("Organization not found")
    return org


@router.get(
    "/{org_id}/revisions",
    response_model=ApiResponse[list[RevisionRow]],
    responses=_ERR,
    summary="Profile revisions of an organisation with before/after values and who changed them",
)
def revisions(
    org_id: uuid.UUID, staff: AdminDep, db: DbSession, page: PageDep
) -> ApiResponse[list[RevisionRow]]:
    _org(db, org_id)
    stmt = select(PartnerProfileRevision).where(PartnerProfileRevision.organization_id == org_id)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = list(
        db.execute(
            stmt.order_by(PartnerProfileRevision.version.desc())
            .limit(page.page_size)
            .offset(page.offset)
        ).scalars()
    )
    names = lookups.user_names(db, (r.changed_by for r in rows))
    return ok(
        [
            RevisionRow(
                version=r.version,
                changed_by=r.changed_by,
                changed_by_name=names.get(r.changed_by),
                changes=r.changes,
                created_at=r.created_at,
            )
            for r in rows
        ],
        meta=page_meta(page, total),
    )


@router.get(
    "/{org_id}/activity",
    response_model=ApiResponse[list[OrgActivityRow]],
    responses=_ERR,
    summary="Audit trail of one organisation (strategic enquiry events are never included)",
)
def activity(
    org_id: uuid.UUID, staff: AdminDep, db: DbSession, page: PageDep
) -> ApiResponse[list[OrgActivityRow]]:
    _org(db, org_id)
    stmt = select(Activity).where(Activity.organization_id == org_id)
    strategic_enquiries = select(Enquiry.id).where(Enquiry.enquiry_type == EnquiryType.STRATEGIC)
    stmt = stmt.where(
        not_(and_(Activity.record_type == "enquiry", Activity.record_id.in_(strategic_enquiries)))
    )
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = list(
        db.execute(
            stmt.order_by(Activity.created_at.desc(), Activity.id.desc())
            .limit(page.page_size)
            .offset(page.offset)
        ).scalars()
    )
    names = lookups.user_names(db, (a.actor_user_id for a in rows))
    return ok(
        [
            OrgActivityRow(
                id=a.id,
                record_type=a.record_type,
                action=a.action,
                actor_name=names.get(a.actor_user_id) if a.actor_user_id else None,
                meta=a.meta,
                created_at=a.created_at,
            )
            for a in rows
        ],
        meta=page_meta(page, total),
    )
