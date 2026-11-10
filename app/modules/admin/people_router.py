"""Account administration and assignee lookup (gap closure: M1, Phase 14, Phase 17, Phase 24).

Accounts are managed by super administrators only. The assignee picker is open to every staff role
but exposes names and roles only (no email, no status detail)."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import ColumnElement, and_, exists, func, or_, select
from sqlalchemy.orm import Session

from app.common.pagination import PageDep, page_meta
from app.common.responses import ApiResponse, ErrorResponse, ok
from app.common.utilities import utcnow
from app.core.config import Settings, get_settings
from app.core.exceptions import AppError, NotFoundError
from app.core.protection import rate_limit
from app.database.dependencies import DbSession
from app.modules.admin import lookups
from app.modules.auth import service as auth_service
from app.modules.auth.constants import StaffRole, TokenPurpose, UserStatus, UserType
from app.modules.auth.dependencies import SuperAdminDep, require_staff
from app.modules.auth.models import AuthToken, User
from app.modules.enquiries.activity import log_activity
from app.modules.enquiries.constants import ActorType
from app.modules.enquiries.models import Activity
from app.modules.notifications.constants import DeliveryStatus, TemplateKey
from app.modules.notifications.models import Notification
from app.modules.notifications.service import dispatch_notifications
from app.modules.organizations.constants import MembershipStatus
from app.modules.organizations.models import PartnerMembership, PartnerOrganization

router = APIRouter(prefix="/admin", tags=["admin-accounts"])
_ERR: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
}
SettingsDep = Annotated[Settings, Depends(get_settings)]
AnyStaffDep = Annotated[object, Depends(require_staff())]
INVITE_LIMIT = [Depends(rate_limit("invite"))]


# ------------------------------------------------------------------ assignees (M1)
class AssigneeOut(BaseModel):
    id: uuid.UUID
    full_name: str
    staff_role: StaffRole


@router.get(
    "/assignees",
    response_model=ApiResponse[list[AssigneeOut]],
    responses=_ERR,
    summary="Active staff who can own enquiries or applications (names and roles only)",
)
def assignees(
    staff: AnyStaffDep,
    db: DbSession,
    purpose: Annotated[Literal["enquiries", "applications"], Query()] = "enquiries",
) -> ApiResponse[list[AssigneeOut]]:
    roles = (
        (StaffRole.SUPER_ADMINISTRATOR, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
        if purpose == "enquiries"
        else (StaffRole.SUPER_ADMINISTRATOR, StaffRole.PARTNER_REVIEWER)
    )
    rows = db.execute(
        select(User)
        .where(
            User.user_type == UserType.STAFF,
            User.status == UserStatus.ACTIVE,
            User.staff_role.in_(roles),
        )
        .order_by(User.full_name, User.id)
    ).scalars()
    return ok(
        [
            AssigneeOut(id=u.id, full_name=u.full_name, staff_role=u.staff_role)
            for u in rows
            if u.staff_role
        ]
    )


# ------------------------------------------------------------------------ accounts
class OrgRefOut(BaseModel):
    id: uuid.UUID
    legal_name: str


class AccountOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    user_type: UserType
    staff_role: StaffRole | None
    status: UserStatus
    invitation_state: Literal["none", "pending", "expired", "revoked", "accepted"]
    mfa_enabled: bool
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime
    invitation_delivery_status: DeliveryStatus | None = None
    invitation_delivery_at: datetime | None = None
    organization: OrgRefOut | None = None


class AccountEvent(BaseModel):
    action: str
    actor_name: str | None
    created_at: datetime


class AccountDetail(AccountOut):
    recent_activity: list[AccountEvent]


class AccountMetricsOut(BaseModel):
    total_accounts: int
    accounts_by_type: dict[str, int]
    accounts_by_status: dict[str, int]
    staff_by_role: dict[str, int]
    active_partner_accounts: int
    accounts_never_logged_in: int


def _valid_invite(now: datetime) -> ColumnElement[bool]:
    return exists().where(
        AuthToken.user_id == User.id,
        AuthToken.purpose == TokenPurpose.INVITATION,
        AuthToken.used_at.is_(None),
        AuthToken.revoked_at.is_(None),
        AuthToken.expires_at > now,
    )


def _any_invite(*conditions: ColumnElement[bool]) -> ColumnElement[bool]:
    return exists().where(
        AuthToken.user_id == User.id, AuthToken.purpose == TokenPurpose.INVITATION, *conditions
    )


def _account_rows(db: Session, users: list[User]) -> list[AccountOut]:
    orgs: dict[uuid.UUID, OrgRefOut] = {}
    invite_delivery: dict[str, tuple[DeliveryStatus, datetime]] = {}
    emails = [u.email for u in users]
    if emails:
        for recipient, status, created_at in db.execute(
            select(Notification.recipient, Notification.delivery_status, Notification.created_at)
            .where(
                Notification.recipient.in_(emails),
                Notification.template_key == TemplateKey.PARTNER_INVITATION,
            )
            .order_by(Notification.created_at.desc(), Notification.id.desc())
        ):
            invite_delivery.setdefault(recipient, (status, created_at))
    partner_ids = [u.id for u in users if u.user_type is UserType.PARTNER]
    if partner_ids:
        for uid, oid, name in db.execute(
            select(
                PartnerMembership.user_id, PartnerOrganization.id, PartnerOrganization.legal_name
            )
            .join(PartnerOrganization, PartnerOrganization.id == PartnerMembership.organization_id)
            .where(
                PartnerMembership.user_id.in_(partner_ids),
                PartnerMembership.status == MembershipStatus.ACTIVE,
            )
        ):
            orgs[uid] = OrgRefOut(id=oid, legal_name=name)
    return [
        AccountOut(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            user_type=u.user_type,
            staff_role=u.staff_role,
            status=u.status,
            invitation_state=auth_service.invitation_state(db, u),  # type: ignore[arg-type,unused-ignore]
            mfa_enabled=u.mfa_enabled_at is not None,
            last_login_at=u.last_login_at,
            created_at=u.created_at,
            updated_at=u.updated_at,
            invitation_delivery_status=(
                invite_delivery[u.email][0] if u.email in invite_delivery else None
            ),
            invitation_delivery_at=(
                invite_delivery[u.email][1] if u.email in invite_delivery else None
            ),
            organization=orgs.get(u.id),
        )
        for u in users
    ]


_SORTS: dict[str, tuple[Any, ...]] = {
    "created_at": (User.created_at.asc(), User.id.asc()),
    "-created_at": (User.created_at.desc(), User.id.desc()),
    "last_login_at": (User.last_login_at.asc().nulls_last(), User.id.asc()),
    "-last_login_at": (User.last_login_at.desc().nulls_last(), User.id.desc()),
    "email": (User.email.asc(), User.id.asc()),
}


@router.get(
    "/accounts",
    response_model=ApiResponse[list[AccountOut]],
    responses=_ERR,
    summary="All staff and partner accounts with invitation state (super administrator)",
)
def list_accounts(
    staff: SuperAdminDep,
    db: DbSession,
    page: PageDep,
    q: Annotated[
        str | None, Query(max_length=120, description="Partial match on email or name")
    ] = None,
    user_type: Annotated[UserType | None, Query()] = None,
    role: Annotated[StaffRole | None, Query()] = None,
    status: Annotated[UserStatus | None, Query()] = None,
    invitation: Annotated[Literal["pending", "expired", "revoked"] | None, Query()] = None,
    created_from: Annotated[datetime | None, Query()] = None,
    created_to: Annotated[datetime | None, Query()] = None,
    sort: Annotated[
        Literal["created_at", "-created_at", "last_login_at", "-last_login_at", "email"], Query()
    ] = "-created_at",
) -> ApiResponse[list[AccountOut]]:
    stmt = select(User)
    if q:
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        stmt = stmt.where(
            or_(User.email.ilike(like, escape="\\"), User.full_name.ilike(like, escape="\\"))
        )
    if user_type:
        stmt = stmt.where(User.user_type == user_type)
    if role:
        stmt = stmt.where(User.staff_role == role)
    if status:
        stmt = stmt.where(User.status == status)
    if created_from:
        stmt = stmt.where(User.created_at >= created_from)
    if created_to:
        stmt = stmt.where(User.created_at < created_to)
    if invitation:
        now = utcnow()
        invited = User.status == UserStatus.INVITED
        valid = _valid_invite(now)
        if invitation == "pending":
            stmt = stmt.where(invited, valid)
        elif invitation == "revoked":
            stmt = stmt.where(invited, ~valid, _any_invite(AuthToken.revoked_at.is_not(None)))
        else:
            stmt = stmt.where(
                invited,
                ~valid,
                _any_invite(
                    and_(
                        AuthToken.used_at.is_(None),
                        AuthToken.revoked_at.is_(None),
                        AuthToken.expires_at <= now,
                    )
                ),
            )
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    users = list(
        db.execute(stmt.order_by(*_SORTS[sort]).limit(page.page_size).offset(page.offset)).scalars()
    )
    return ok(_account_rows(db, users), meta=page_meta(page, total))


@router.get(
    "/accounts/metrics",
    response_model=ApiResponse[AccountMetricsOut],
    responses=_ERR,
    summary="Account counts by type, status and staff role (super administrator)",
)
def account_metrics(staff: SuperAdminDep, db: DbSession) -> ApiResponse[AccountMetricsOut]:
    by_type = {
        str(kind.value): count
        for kind, count in db.execute(select(User.user_type, func.count()).group_by(User.user_type))
    }
    by_status = {
        str(status.value): count
        for status, count in db.execute(select(User.status, func.count()).group_by(User.status))
    }
    by_role = {
        str(role.value): count
        for role, count in db.execute(
            select(User.staff_role, func.count())
            .where(User.user_type == UserType.STAFF, User.staff_role.is_not(None))
            .group_by(User.staff_role)
        )
        if role is not None
    }
    return ok(
        AccountMetricsOut(
            total_accounts=sum(by_type.values()),
            accounts_by_type=by_type,
            accounts_by_status=by_status,
            staff_by_role=by_role,
            active_partner_accounts=db.execute(
                select(func.count())
                .select_from(User)
                .where(User.user_type == UserType.PARTNER, User.status == UserStatus.ACTIVE)
            ).scalar_one(),
            accounts_never_logged_in=db.execute(
                select(func.count()).select_from(User).where(User.last_login_at.is_(None))
            ).scalar_one(),
        )
    )


def _account(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("Account not found")
    return user


@router.get(
    "/accounts/{user_id}",
    response_model=ApiResponse[AccountDetail],
    responses=_ERR,
    summary="One account with its recent activity (super administrator)",
)
def account_detail(
    user_id: uuid.UUID, staff: SuperAdminDep, db: DbSession
) -> ApiResponse[AccountDetail]:
    user = _account(db, user_id)
    base = _account_rows(db, [user])[0]
    acts = list(
        db.execute(
            select(Activity)
            .where(
                or_(
                    and_(Activity.record_type == "user", Activity.record_id == user.id),
                    Activity.actor_user_id == user.id,
                )
            )
            .order_by(Activity.created_at.desc(), Activity.id.desc())
            .limit(50)
        ).scalars()
    )
    names = lookups.user_names(db, (a.actor_user_id for a in acts))
    events = [
        AccountEvent(
            action=a.action,
            actor_name=names.get(a.actor_user_id) if a.actor_user_id else None,
            created_at=a.created_at,
        )
        for a in acts
    ]
    return ok(AccountDetail(**base.model_dump(), recent_activity=events))


def _dispatch(request: Request, background: BackgroundTasks, settings: Settings) -> None:
    background.add_task(
        dispatch_notifications,
        request.app.state.sessionmaker,
        request.app.state.email_sender,
        settings,
    )


@router.post(
    "/accounts/{user_id}/invitation/resend",
    dependencies=INVITE_LIMIT,
    response_model=ApiResponse[AccountOut],
    responses=_ERR,
    summary="Issue a fresh invitation link (replaces older ones); rate limited",
)
def resend(
    user_id: uuid.UUID,
    request: Request,
    staff: SuperAdminDep,
    db: DbSession,
    settings: SettingsDep,
    background: BackgroundTasks,
) -> ApiResponse[AccountOut]:
    user = db.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one_or_none()
    if user is None:
        raise NotFoundError("Account not found")
    auth_service.resend_invitation(db, settings, staff.user, user)
    db.commit()
    _dispatch(request, background, settings)
    return ok(_account_rows(db, [user])[0], "Invitation re-sent")


@router.post(
    "/accounts/{user_id}/invitation/revoke",
    response_model=ApiResponse[AccountOut],
    responses=_ERR,
    summary="Cancel the open invitation; the account stays un-activated",
)
def revoke(user_id: uuid.UUID, staff: SuperAdminDep, db: DbSession) -> ApiResponse[AccountOut]:
    user = db.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one_or_none()
    if user is None:
        raise NotFoundError("Account not found")
    auth_service.revoke_invitation(db, staff.user, user)
    db.commit()
    return ok(_account_rows(db, [user])[0], "Invitation revoked")


@router.post(
    "/accounts/{user_id}/password-reset",
    dependencies=INVITE_LIMIT,
    response_model=ApiResponse[None],
    responses=_ERR,
    summary="Email the account holder a password-reset link (admins never see or set passwords)",
)
def admin_password_reset(
    user_id: uuid.UUID,
    request: Request,
    staff: SuperAdminDep,
    db: DbSession,
    settings: SettingsDep,
    background: BackgroundTasks,
) -> ApiResponse[None]:
    user = _account(db, user_id)
    if user.status is not UserStatus.ACTIVE:
        raise AppError("Only active accounts can be reset", status_code=409, code="NOT_ACTIVE")
    auth_service.request_password_reset(db, settings, user.email)
    log_activity(
        db,
        "user",
        user.id,
        "admin.password_reset_sent",
        {},
        ActorType.STAFF,
        actor_user_id=staff.user.id,
    )
    db.commit()
    _dispatch(request, background, settings)
    return ok(None, "Reset link sent")


@router.post(
    "/accounts/{user_id}/suspend",
    response_model=ApiResponse[AccountOut],
    responses=_ERR,
    summary="Suspend an account and sign it out everywhere (never yourself)",
)
def suspend(user_id: uuid.UUID, staff: SuperAdminDep, db: DbSession) -> ApiResponse[AccountOut]:
    user = _account(db, user_id)
    if user.id == staff.user.id:
        raise AppError("You cannot suspend your own account", status_code=409, code="SELF_CHANGE")
    if user.user_type is UserType.STAFF:
        from app.modules.admin import service  # staff rules: last super administrator

        user = service.set_staff_active(db, staff, user_id, False)
    else:
        if user.status is UserStatus.DEACTIVATED:
            raise AppError(
                "Account is already suspended", status_code=409, code="ALREADY_SUSPENDED"
            )
        user.status = UserStatus.DEACTIVATED
        auth_service.revoke_all_sessions(db, user.id, "suspended")
        log_activity(
            db,
            "user",
            user.id,
            "admin.account_suspended",
            {},
            ActorType.STAFF,
            actor_user_id=staff.user.id,
        )
        db.commit()
    return ok(_account_rows(db, [user])[0], "Account suspended")


@router.post(
    "/accounts/{user_id}/reactivate",
    response_model=ApiResponse[AccountOut],
    responses=_ERR,
    summary="Reactivate a suspended account (needs a password; otherwise re-invite instead)",
)
def reactivate(user_id: uuid.UUID, staff: SuperAdminDep, db: DbSession) -> ApiResponse[AccountOut]:
    user = _account(db, user_id)
    if user.status is not UserStatus.DEACTIVATED:
        raise AppError(
            "Only suspended accounts can be reactivated", status_code=409, code="NOT_SUSPENDED"
        )
    if user.password_hash is None:
        raise AppError(
            "Account was never activated; re-invite it", status_code=409, code="NOT_ACTIVATED"
        )
    if user.user_type is UserType.STAFF:
        from app.modules.admin import service

        user = service.set_staff_active(db, staff, user_id, True)
    else:
        user.status = UserStatus.ACTIVE
        log_activity(
            db,
            "user",
            user.id,
            "admin.account_reactivated",
            {},
            ActorType.STAFF,
            actor_user_id=staff.user.id,
        )
        db.commit()
    return ok(_account_rows(db, [user])[0], "Account reactivated")
