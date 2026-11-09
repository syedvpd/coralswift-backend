"""Phase 3 admin APIs (/api/v1/admin). Roles: super_administrator, business_development_manager
(restricted: no strategic enquiries, no financial data). Every route declares its role."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response

from app.common.pagination import PageDep, page_meta
from app.common.responses import ApiResponse, ErrorResponse, ok
from app.core.config import Settings, get_settings
from app.database.dependencies import DbSession
from app.modules.admin import service
from app.modules.admin.schemas import (
    AssignIn,
    AuditRow,
    EnquiryDetail,
    EnquiryRow,
    EnquiryUpdate,
    FollowUpIn,
    FollowUpOut,
    OrgRow,
    OrgStatusIn,
    StaffInviteIn,
    StaffOut,
    StaffRoleIn,
)
from app.modules.applications.constants import PortalStatus
from app.modules.auth import service as auth_service
from app.modules.auth.constants import StaffRole
from app.modules.auth.dependencies import StaffContext, SuperAdminDep, require_staff
from app.modules.auth.models import User
from app.modules.enquiries.constants import EnquiryStatus, EnquiryType, Priority
from app.modules.enquiries.models import Enquiry
from app.modules.notifications.service import dispatch_notifications

router = APIRouter(prefix="/admin", tags=["admin"])
SettingsDep = Annotated[Settings, Depends(get_settings)]
AdminDep = Annotated[
    StaffContext,
    Depends(require_staff(StaffRole.SUPER_ADMINISTRATOR, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)),
]
_ERR: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


class EnquiryFilters:
    """Shared query parameters for the list and the CSV export."""

    def __init__(
        self,
        type: Annotated[EnquiryType | None, Query()] = None,  # noqa: A002
        status: Annotated[EnquiryStatus | None, Query()] = None,
        priority: Annotated[Priority | None, Query()] = None,
        assigned_user_id: Annotated[uuid.UUID | None, Query()] = None,
        unassigned: Annotated[bool, Query()] = False,
        overdue: Annotated[
            bool, Query(description="Follow-up date passed, enquiry not closed")
        ] = False,
        sla_breached: Annotated[bool, Query(description="First-response target missed")] = False,
        q: Annotated[
            str | None, Query(max_length=100, description="reference, name, email, company")
        ] = None,
        created_from: Annotated[datetime | None, Query()] = None,
        created_to: Annotated[datetime | None, Query()] = None,
    ) -> None:
        self.values: dict[str, Any] = {
            "enquiry_type": type,
            "status": status,
            "priority": priority,
            "assigned_user_id": assigned_user_id,
            "unassigned": unassigned,
            "overdue": overdue,
            "sla_breached": sla_breached,
            "q": q,
            "created_from": created_from,
            "created_to": created_to,
        }


FiltersDep = Annotated[EnquiryFilters, Depends()]


# --------------------------------------------------------------------- overview
@router.get(
    "/overview",
    response_model=ApiResponse[dict[str, Any]],
    responses=_ERR,
    summary="Dashboard counters (scoped to your role)",
)
def overview(staff: AdminDep, db: DbSession) -> ApiResponse[dict[str, Any]]:
    return ok(service.overview(db, staff))


# -------------------------------------------------------------------- enquiries
@router.get(
    "/enquiries",
    response_model=ApiResponse[list[EnquiryRow]],
    responses=_ERR,
    summary="Enquiries / leads (filters, search, pagination)",
)
def list_enquiries(
    staff: AdminDep, db: DbSession, page: PageDep, f: FiltersDep
) -> ApiResponse[list[EnquiryRow]]:
    rows, total = service.list_enquiries(db, staff, page.page_size, page.offset, **f.values)
    return ok([EnquiryRow(**r) for r in rows], meta=page_meta(page, total))


@router.get("/enquiries/{enquiry_id}", response_model=ApiResponse[EnquiryDetail], responses=_ERR)
def enquiry_detail(
    enquiry_id: uuid.UUID, staff: AdminDep, db: DbSession
) -> ApiResponse[EnquiryDetail]:
    return ok(EnquiryDetail.model_validate(service.enquiry_detail(db, staff, enquiry_id)))


def _row(db: DbSession, staff: StaffContext, enquiry_id: uuid.UUID) -> EnquiryRow:
    e = service.get_visible(db, staff, enquiry_id)
    stmt = service.enquiry_query(staff).where(Enquiry.id == e.id)
    return EnquiryRow(**service.row_dict(*db.execute(stmt).one()))


@router.patch(
    "/enquiries/{enquiry_id}",
    response_model=ApiResponse[EnquiryRow],
    responses=_ERR,
    summary="Change status or priority",
)
def update_enquiry(
    enquiry_id: uuid.UUID, payload: EnquiryUpdate, staff: AdminDep, db: DbSession
) -> ApiResponse[EnquiryRow]:
    service.update_enquiry(db, staff, enquiry_id, payload.status, payload.priority)
    return ok(_row(db, staff, enquiry_id), "Enquiry updated")


@router.post(
    "/enquiries/{enquiry_id}/assign",
    response_model=ApiResponse[EnquiryRow],
    responses=_ERR,
    summary="Assign or clear the lead owner",
)
def assign(
    enquiry_id: uuid.UUID, payload: AssignIn, staff: AdminDep, db: DbSession
) -> ApiResponse[EnquiryRow]:
    service.assign_enquiry(db, staff, enquiry_id, payload.user_id)
    return ok(_row(db, staff, enquiry_id), "Owner updated")


@router.post(
    "/enquiries/{enquiry_id}/follow-ups",
    status_code=201,
    response_model=ApiResponse[FollowUpOut],
    responses=_ERR,
    summary="Add a follow-up / communication note",
)
def add_followup(
    enquiry_id: uuid.UUID, payload: FollowUpIn, staff: AdminDep, db: DbSession
) -> ApiResponse[FollowUpOut]:
    f = service.add_followup(db, staff, enquiry_id, payload.note, payload.due_at)
    return ok(FollowUpOut.model_validate(f, from_attributes=True))


@router.post(
    "/enquiries/{enquiry_id}/follow-ups/{followup_id}/complete",
    response_model=ApiResponse[FollowUpOut],
    responses=_ERR,
)
def complete_followup(
    enquiry_id: uuid.UUID, followup_id: uuid.UUID, staff: AdminDep, db: DbSession
) -> ApiResponse[FollowUpOut]:
    return ok(
        FollowUpOut.model_validate(
            service.complete_followup(db, staff, enquiry_id, followup_id), from_attributes=True
        )
    )


@router.get(
    "/enquiries/{enquiry_id}/documents/{document_id}/download",
    responses={**_ERR, 200: {"content": {"application/octet-stream": {}}}},
    summary="Download an enquiry attachment (audited)",
)
def download(
    enquiry_id: uuid.UUID, document_id: uuid.UUID, request: Request, staff: AdminDep, db: DbSession
) -> Response:
    data, doc = service.download_document(
        db, request.app.state.storage, staff, enquiry_id, document_id
    )
    return Response(
        content=data,
        media_type=doc.content_type,
        headers={
            "Content-Disposition": 'attachment; filename="document"',
            "Cache-Control": "private, no-store",
        },
    )


# ---------------------------------------------------------------- partner database
@router.get(
    "/organizations",
    response_model=ApiResponse[list[OrgRow]],
    responses=_ERR,
    summary="Partner organizations",
)
def list_orgs(
    staff: AdminDep,
    db: DbSession,
    page: PageDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status: Annotated[str | None, Query(pattern="^(active|suspended)$")] = None,
) -> ApiResponse[list[OrgRow]]:
    rows, total = service.list_orgs(db, page.page_size, page.offset, q, status)
    return ok([OrgRow(**r) for r in rows], meta=page_meta(page, total))


@router.get(
    "/organizations/{org_id}",
    response_model=ApiResponse[dict[str, Any]],
    responses=_ERR,
    summary="Organization profile + applications (financial data: super administrators only)",
)
def org_detail(org_id: uuid.UUID, staff: AdminDep, db: DbSession) -> ApiResponse[dict[str, Any]]:
    return ok(service.org_detail(db, staff, org_id))


@router.post(
    "/organizations/{org_id}/status",
    response_model=ApiResponse[None],
    responses=_ERR,
    summary="Suspend or reactivate an organization (super administrator)",
)
def org_status(
    org_id: uuid.UUID, payload: OrgStatusIn, staff: SuperAdminDep, db: DbSession
) -> ApiResponse[None]:
    service.set_org_status(db, staff, org_id, payload.status, payload.reason)
    return ok(None, "Organization updated")


# ------------------------------------------------------------------- staff users
def _staff_out(u: User) -> StaffOut:
    return StaffOut(
        id=u.id,
        email=u.email,
        full_name=u.full_name,
        staff_role=u.staff_role,
        status=u.status.value,
        mfa_enabled=u.mfa_enabled_at is not None,
        last_login_at=u.last_login_at,
    )


@router.get(
    "/users",
    response_model=ApiResponse[list[StaffOut]],
    responses=_ERR,
    summary="Staff accounts (super administrator)",
)
def list_staff(
    staff: SuperAdminDep, db: DbSession, role: Annotated[StaffRole | None, Query()] = None
) -> ApiResponse[list[StaffOut]]:
    return ok([_staff_out(u) for u in service.list_staff(db, role)])


@router.post(
    "/users",
    status_code=201,
    response_model=ApiResponse[StaffOut],
    responses=_ERR,
    summary="Invite a staff user (they set a password, then enroll MFA)",
)
def invite_staff(
    payload: StaffInviteIn,
    request: Request,
    staff: SuperAdminDep,
    db: DbSession,
    settings: SettingsDep,
    background: BackgroundTasks,
) -> ApiResponse[StaffOut]:
    user = auth_service.invite_staff_user(
        db,
        settings,
        inviter=staff.user,
        email=payload.email,
        full_name=payload.full_name,
        role=payload.role,
    )
    db.commit()
    background.add_task(
        dispatch_notifications,
        request.app.state.sessionmaker,
        request.app.state.email_sender,
        settings,
    )
    return ok(_staff_out(user), "Invitation issued")


@router.post("/users/{user_id}/role", response_model=ApiResponse[StaffOut], responses=_ERR)
def change_role(
    user_id: uuid.UUID, payload: StaffRoleIn, staff: SuperAdminDep, db: DbSession
) -> ApiResponse[StaffOut]:
    return ok(_staff_out(service.change_role(db, staff, user_id, payload.role)), "Role updated")


@router.post("/users/{user_id}/deactivate", response_model=ApiResponse[StaffOut], responses=_ERR)
def deactivate(user_id: uuid.UUID, staff: SuperAdminDep, db: DbSession) -> ApiResponse[StaffOut]:
    return ok(
        _staff_out(service.set_staff_active(db, staff, user_id, False)), "Account deactivated"
    )


@router.post("/users/{user_id}/activate", response_model=ApiResponse[StaffOut], responses=_ERR)
def activate(user_id: uuid.UUID, staff: SuperAdminDep, db: DbSession) -> ApiResponse[StaffOut]:
    return ok(_staff_out(service.set_staff_active(db, staff, user_id, True)), "Account activated")


# ------------------------------------------------------------- audit and reports
@router.get(
    "/audit",
    response_model=ApiResponse[list[AuditRow]],
    responses=_ERR,
    summary="Audit log (super administrator)",
)
def audit(
    staff: SuperAdminDep,
    db: DbSession,
    page: PageDep,
    record_type: Annotated[str | None, Query(max_length=50)] = None,
    action: Annotated[str | None, Query(max_length=80)] = None,
    actor_user_id: Annotated[uuid.UUID | None, Query()] = None,
    organization_id: Annotated[uuid.UUID | None, Query()] = None,
    created_from: Annotated[datetime | None, Query()] = None,
    created_to: Annotated[datetime | None, Query()] = None,
) -> ApiResponse[list[AuditRow]]:
    rows, total = service.list_audit(
        db,
        page.page_size,
        page.offset,
        record_type=record_type,
        action=action,
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        created_from=created_from,
        created_to=created_to,
    )
    return ok(
        [
            AuditRow(
                id=a.id,
                record_type=a.record_type,
                record_id=a.record_id,
                action=a.action,
                actor_type=a.actor_type.value,
                actor_user_id=a.actor_user_id,
                organization_id=a.organization_id,
                request_id=a.request_id,
                meta=a.meta,
                created_at=a.created_at,
            )
            for a in rows
        ],
        meta=page_meta(page, total),
    )


@router.get(
    "/reports/enquiries.csv",
    responses={**_ERR, 200: {"content": {"text/csv": {}}}},
    summary="CSV export of the enquiry list (same filters; capped at 10,000 rows; audited)",
)
def export_enquiries(staff: AdminDep, db: DbSession, f: FiltersDep) -> Response:
    body = service.enquiries_csv(db, staff, **f.values)
    return Response(
        content=body,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="enquiries.csv"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get(
    "/reports/applications.csv",
    responses={**_ERR, 200: {"content": {"text/csv": {}}}},
    summary="CSV export of partner applications (super administrator)",
)
def export_applications(
    staff: SuperAdminDep,
    db: DbSession,
    status: Annotated[PortalStatus | None, Query()] = None,
    created_from: Annotated[datetime | None, Query()] = None,
    created_to: Annotated[datetime | None, Query()] = None,
) -> Response:
    body = service.applications_csv(db, staff, status, created_from, created_to)
    return Response(
        content=body,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="applications.csv"',
            "Cache-Control": "private, no-store",
        },
    )
