"""Partner team management, notification preferences and account closure request.

Every route resolves the organisation from the session. Team changes need the `owner` role.
Partner roles stay owner/member until the owner approves a richer model (D22); the permission
names below are the only ones the API enforces.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.pagination import PageDep, page_meta
from app.common.responses import ApiResponse, ErrorResponse, ok
from app.common.utilities import utcnow
from app.common.validation import EmailAddress, Long, Name
from app.core.config import Settings, get_settings
from app.core.exceptions import AppError, NotFoundError
from app.core.protection import rate_limit
from app.database.dependencies import DbSession
from app.modules.applications.constants import TERMINAL, PortalStatus
from app.modules.applications.models import PortalApplication
from app.modules.auth import service as auth_service
from app.modules.auth.constants import UserStatus
from app.modules.auth.dependencies import CollabReadDep, PartnerContext, PartnerDep, forbidden
from app.modules.auth.models import User
from app.modules.auth.security import verify_password
from app.modules.collaboration import service as collab_service
from app.modules.engagement.models import PrivacyRequestKind
from app.modules.engagement.service import create_privacy_request
from app.modules.enquiries.activity import log_activity
from app.modules.enquiries.constants import ActorType
from app.modules.notifications import preferences
from app.modules.notifications.service import dispatch_notifications
from app.modules.organizations.constants import MembershipRole, MembershipStatus
from app.modules.organizations.models import PartnerMembership, PartnerOrganization
from app.modules.partner_documents.models import DocumentRequest

SettingsDep = Annotated[Settings, Depends(get_settings)]
_ERR: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}
team = APIRouter(prefix="/partner/team", tags=["partner-team"])
prefs = APIRouter(prefix="/partner/notification-preferences", tags=["partner-notifications"])
closure = APIRouter(prefix="/partner/account-closure", tags=["partner-account"])
staff_team = APIRouter(prefix="/reviewer/organizations", tags=["reviewer-team"])
INVITE_LIMIT = [Depends(rate_limit("invite"))]


# ------------------------------------------------------------------- team
class TeamMemberOut(BaseModel):
    id: uuid.UUID  # membership id
    full_name: str
    email: str
    role: MembershipRole
    account_status: UserStatus
    is_you: bool
    last_login_at: Any | None = None


class InviteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailAddress
    full_name: Name
    role: MembershipRole = MembershipRole.MEMBER


class RoleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: MembershipRole


class TransferIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    membership_id: uuid.UUID


def _owner(ctx: PartnerContext) -> None:
    if ctx.role is not MembershipRole.OWNER:
        raise forbidden()


def _member(db: Session, ctx: PartnerContext, membership_id: uuid.UUID) -> PartnerMembership:
    """Locked row; other organisations' memberships look nonexistent."""
    m = db.execute(
        select(PartnerMembership)
        .where(
            PartnerMembership.id == membership_id,
            PartnerMembership.organization_id == ctx.organization_id,
            PartnerMembership.status == MembershipStatus.ACTIVE,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if m is None:
        raise NotFoundError("Team member not found")
    return m


def _owners_left(db: Session, ctx: PartnerContext, excluding: uuid.UUID) -> int:
    return db.execute(
        select(func.count())
        .select_from(PartnerMembership)
        .join(User, User.id == PartnerMembership.user_id)
        .where(
            PartnerMembership.organization_id == ctx.organization_id,
            PartnerMembership.status == MembershipStatus.ACTIVE,
            PartnerMembership.role == MembershipRole.OWNER,
            PartnerMembership.id != excluding,
            User.status == UserStatus.ACTIVE,
        )
    ).scalar_one()


def _out(ctx: PartnerContext, m: PartnerMembership, u: User) -> TeamMemberOut:
    return TeamMemberOut(
        id=m.id,
        full_name=u.full_name,
        email=u.email,
        role=m.role,
        account_status=u.status,
        is_you=u.id == ctx.user.id,
        last_login_at=u.last_login_at,
    )


def _audit(db: Session, ctx: PartnerContext, action: str, target: uuid.UUID, **meta: str) -> None:
    log_activity(
        db,
        "team_member",
        target,
        action,
        dict(meta),
        ActorType.PARTNER,
        actor_user_id=ctx.user.id,
        organization_id=ctx.organization_id,
    )


def _load(
    db: Session, ctx: PartnerContext, membership_id: uuid.UUID
) -> tuple[PartnerMembership, User]:
    m = _member(db, ctx, membership_id)
    return m, db.get(User, m.user_id)  # type: ignore[return-value]


@team.get("", response_model=ApiResponse[list[TeamMemberOut]], responses=_ERR)
def list_team(ctx: PartnerDep, db: DbSession, page: PageDep) -> ApiResponse[list[TeamMemberOut]]:
    """Everyone in your organisation, including invited people who have not activated yet."""
    base = (
        select(PartnerMembership, User)
        .join(User, User.id == PartnerMembership.user_id)
        .where(
            PartnerMembership.organization_id == ctx.organization_id,
            PartnerMembership.status == MembershipStatus.ACTIVE,
        )
    )
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(
        base.order_by(User.full_name, PartnerMembership.id)
        .limit(page.page_size)
        .offset(page.offset)
    ).all()
    return ok([_out(ctx, m, u) for m, u in rows], meta=page_meta(page, total))


@team.get("/{membership_id}", response_model=ApiResponse[TeamMemberOut], responses=_ERR)
def get_member(
    membership_id: uuid.UUID, ctx: PartnerDep, db: DbSession
) -> ApiResponse[TeamMemberOut]:
    m, u = _load(db, ctx, membership_id)
    return ok(_out(ctx, m, u))


def _dispatch(request: Request, settings: Settings, background: BackgroundTasks) -> None:
    background.add_task(
        dispatch_notifications,
        request.app.state.sessionmaker,
        request.app.state.email_sender,
        settings,
    )


@team.post(
    "/invitations",
    status_code=201,
    dependencies=INVITE_LIMIT,
    response_model=ApiResponse[TeamMemberOut],
    responses=_ERR,
    summary="Invite a colleague (owners only)",
)
def invite(
    payload: InviteIn,
    request: Request,
    ctx: PartnerDep,
    db: DbSession,
    settings: SettingsDep,
    background: BackgroundTasks,
) -> ApiResponse[TeamMemberOut]:
    _owner(ctx)
    org = db.get(PartnerOrganization, ctx.organization_id)
    assert org is not None  # noqa: S101 - resolved from the session membership
    auth_service.invite_partner_user(
        db,
        settings,
        inviter=ctx.user,
        email=payload.email,
        full_name=payload.full_name,
        organization=org,
        role=payload.role,
    )
    user = db.execute(select(User).where(User.email == payload.email.lower())).scalar_one()
    m = db.execute(
        select(PartnerMembership).where(
            PartnerMembership.user_id == user.id,
            PartnerMembership.organization_id == org.id,
        )
    ).scalar_one()
    _audit(db, ctx, "team.invited", m.id, role=payload.role.value)
    db.commit()
    _dispatch(request, settings, background)
    return ok(_out(ctx, m, user), "Invitation sent")


@team.post(
    "/{membership_id}/resend",
    dependencies=INVITE_LIMIT,
    response_model=ApiResponse[None],
    responses=_ERR,
    summary="Send a fresh invitation link (only for people who have not activated)",
)
def resend(
    membership_id: uuid.UUID,
    request: Request,
    ctx: PartnerDep,
    db: DbSession,
    settings: SettingsDep,
    background: BackgroundTasks,
) -> ApiResponse[None]:
    _owner(ctx)
    m, u = _load(db, ctx, membership_id)
    auth_service.resend_invitation(db, settings, ctx.user, u)
    _audit(db, ctx, "team.invitation_resent", m.id)
    db.commit()
    _dispatch(request, settings, background)
    return ok(None, "Invitation re-sent")


@team.post(
    "/{membership_id}/cancel",
    response_model=ApiResponse[None],
    responses=_ERR,
    summary="Cancel an open invitation; the person is removed from the team",
)
def cancel_invitation(
    membership_id: uuid.UUID, ctx: PartnerDep, db: DbSession
) -> ApiResponse[None]:
    _owner(ctx)
    m, u = _load(db, ctx, membership_id)
    auth_service.revoke_invitation(db, ctx.user, u)
    m.status = MembershipStatus.REMOVED
    _audit(db, ctx, "team.invitation_cancelled", m.id)
    db.commit()
    return ok(None, "Invitation cancelled")


@team.patch(
    "/{membership_id}/role",
    response_model=ApiResponse[TeamMemberOut],
    responses=_ERR,
    summary="Change a colleague's role (owners only; not your own, use transfer-ownership)",
)
def change_role(
    membership_id: uuid.UUID, payload: RoleIn, ctx: PartnerDep, db: DbSession
) -> ApiResponse[TeamMemberOut]:
    _owner(ctx)
    m, u = _load(db, ctx, membership_id)
    if u.id == ctx.user.id:
        raise AppError("You cannot change your own role", status_code=409, code="SELF_CHANGE")
    demoting = m.role is MembershipRole.OWNER and payload.role is not MembershipRole.OWNER
    if demoting and _owners_left(db, ctx, m.id) < 1:
        raise AppError("An owner must remain", status_code=409, code="LAST_OWNER")
    previous, m.role = m.role, payload.role
    auth_service.revoke_all_sessions(db, u.id, "role_changed")
    _audit(db, ctx, "team.role_changed", m.id, **{"from": previous.value, "to": m.role.value})
    db.commit()
    return ok(_out(ctx, m, u), "Role updated")


@team.post(
    "/{membership_id}/deactivate",
    response_model=ApiResponse[TeamMemberOut],
    responses=_ERR,
    summary="Block a colleague's sign-in (not yourself, never the last active owner)",
)
def deactivate(
    membership_id: uuid.UUID, ctx: PartnerDep, db: DbSession
) -> ApiResponse[TeamMemberOut]:
    _owner(ctx)
    m, u = _load(db, ctx, membership_id)
    if u.id == ctx.user.id:
        raise AppError("You cannot deactivate yourself", status_code=409, code="SELF_CHANGE")
    if u.status is not UserStatus.ACTIVE:
        raise AppError(
            "Only active accounts can be deactivated", status_code=409, code="NOT_ACTIVE"
        )
    if m.role is MembershipRole.OWNER and _owners_left(db, ctx, m.id) < 1:
        raise AppError("An owner must remain", status_code=409, code="LAST_OWNER")
    u.status = UserStatus.DEACTIVATED
    auth_service.revoke_all_sessions(db, u.id, "deactivated")
    _audit(db, ctx, "team.deactivated", m.id)
    db.commit()
    return ok(_out(ctx, m, u), "Deactivated")


@team.post(
    "/{membership_id}/activate",
    response_model=ApiResponse[TeamMemberOut],
    responses=_ERR,
    summary="Restore a deactivated colleague",
)
def activate(
    membership_id: uuid.UUID, ctx: PartnerDep, db: DbSession
) -> ApiResponse[TeamMemberOut]:
    _owner(ctx)
    m, u = _load(db, ctx, membership_id)
    if u.status is not UserStatus.DEACTIVATED or u.password_hash is None:
        raise AppError(
            "Only deactivated accounts can be restored", status_code=409, code="NOT_DEACTIVATED"
        )
    u.status = UserStatus.ACTIVE
    u.failed_login_count, u.locked_until = 0, None
    _audit(db, ctx, "team.activated", m.id)
    db.commit()
    return ok(_out(ctx, m, u), "Activated")


@team.delete(
    "/{membership_id}",
    response_model=ApiResponse[None],
    responses=_ERR,
    summary="Remove a colleague from the organisation (their account is deactivated, not deleted)",
)
def remove(membership_id: uuid.UUID, ctx: PartnerDep, db: DbSession) -> ApiResponse[None]:
    _owner(ctx)
    m, u = _load(db, ctx, membership_id)
    if u.id == ctx.user.id:
        raise AppError("You cannot remove yourself", status_code=409, code="SELF_CHANGE")
    if m.role is MembershipRole.OWNER and _owners_left(db, ctx, m.id) < 1:
        raise AppError("An owner must remain", status_code=409, code="LAST_OWNER")
    m.status = MembershipStatus.REMOVED
    if u.status is UserStatus.ACTIVE:
        u.status = UserStatus.DEACTIVATED
    auth_service.revoke_all_sessions(db, u.id, "removed_from_team")
    _audit(db, ctx, "team.removed", m.id)
    db.commit()
    return ok(None, "Removed")


@team.post(
    "/transfer-ownership",
    response_model=ApiResponse[list[TeamMemberOut]],
    responses=_ERR,
    summary="Hand your owner role to an active colleague; you become a member (one transaction)",
)
def transfer_ownership(
    payload: TransferIn, ctx: PartnerDep, db: DbSession
) -> ApiResponse[list[TeamMemberOut]]:
    _owner(ctx)
    target, tu = _load(db, ctx, payload.membership_id)
    if tu.id == ctx.user.id:
        raise AppError("Choose someone else", status_code=409, code="SELF_CHANGE")
    if tu.status is not UserStatus.ACTIVE:
        raise AppError(
            "The new owner must have an active account", status_code=409, code="NOT_ACTIVE"
        )
    mine = db.execute(
        select(PartnerMembership)
        .where(
            PartnerMembership.organization_id == ctx.organization_id,
            PartnerMembership.user_id == ctx.user.id,
            PartnerMembership.status == MembershipStatus.ACTIVE,
        )
        .with_for_update()
    ).scalar_one()
    target.role, mine.role = MembershipRole.OWNER, MembershipRole.MEMBER
    auth_service.revoke_all_sessions(db, tu.id, "role_changed")
    _audit(db, ctx, "team.ownership_transferred", target.id, to=str(tu.id))
    db.commit()
    return ok([_out(ctx, target, tu), _out(ctx, mine, ctx.user)], "Ownership transferred")


# --------------------------------------------------- staff view of a team (read-only)
class StaffTeamMemberOut(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str
    role: MembershipRole
    account_status: UserStatus
    invitation_pending: bool
    last_login_at: Any | None = None


@staff_team.get(
    "/{organization_id}/team",
    response_model=ApiResponse[list[StaffTeamMemberOut]],
    responses=_ERR,
    summary="Partner team of an organisation (read-only; BDMs only for assigned organisations)",
)
def staff_team_list(
    organization_id: uuid.UUID, staff: CollabReadDep, db: DbSession, page: PageDep
) -> ApiResponse[list[StaffTeamMemberOut]]:
    org = collab_service.require_org(db, staff, organization_id)
    base = (
        select(PartnerMembership, User)
        .join(User, User.id == PartnerMembership.user_id)
        .where(
            PartnerMembership.organization_id == org.id,
            PartnerMembership.status == MembershipStatus.ACTIVE,
        )
    )
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(
        base.order_by(User.full_name, PartnerMembership.id)
        .limit(page.page_size)
        .offset(page.offset)
    ).all()
    return ok(
        [
            StaffTeamMemberOut(
                id=m.id,
                full_name=u.full_name,
                email=u.email,
                role=m.role,
                account_status=u.status,
                invitation_pending=u.status is UserStatus.INVITED,
                last_login_at=u.last_login_at,
            )
            for m, u in rows
        ],
        meta=page_meta(page, total),
    )


# ---------------------------------------------------- notification preferences
class PreferencesOut(BaseModel):
    categories: dict[str, bool]
    mandatory: list[str]


class PreferencesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    categories: dict[str, bool]


@prefs.get("", response_model=ApiResponse[PreferencesOut], responses=_ERR)
def get_prefs(ctx: PartnerDep, db: DbSession) -> ApiResponse[PreferencesOut]:
    return ok(
        PreferencesOut(
            categories=preferences.load(db, ctx.user.id), mandatory=sorted(preferences.MANDATORY)
        )
    )


@prefs.put(
    "",
    response_model=ApiResponse[PreferencesOut],
    responses=_ERR,
    summary="Switch optional email categories on or off; mandatory notices cannot be disabled",
)
def put_prefs(
    payload: PreferencesIn, ctx: PartnerDep, db: DbSession
) -> ApiResponse[PreferencesOut]:
    known = preferences.MANDATORY | preferences.OPTIONAL
    unknown = sorted(set(payload.categories) - known)
    if unknown:
        raise AppError(
            f"Unknown categories: {', '.join(unknown)}", status_code=422, code="UNKNOWN_CATEGORY"
        )
    locked = sorted(
        c for c in payload.categories if c in preferences.MANDATORY and not payload.categories[c]
    )
    if locked:
        raise AppError(
            f"Mandatory notices cannot be disabled: {', '.join(locked)}",
            status_code=422,
            code="MANDATORY_NOTICE",
        )
    preferences.save(db, ctx.user.id, payload.categories, utcnow())
    db.commit()
    return ok(
        PreferencesOut(
            categories=preferences.load(db, ctx.user.id), mandatory=sorted(preferences.MANDATORY)
        ),
        "Preferences saved",
    )


# --------------------------------------------------------------- account closure
class ClosureBlocker(BaseModel):
    code: str
    detail: str


class ClosurePreview(BaseModel):
    can_close: bool
    blockers: list[ClosureBlocker]
    retention_note: str


class ClosureIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str
    reason: Long | None = None


RETENTION_NOTE = (
    "Closing a request records a deletion request. Staff decide what is deleted and what must be "
    "kept under legal retention rules; nothing is deleted automatically."
)


def _blockers(db: Session, ctx: PartnerContext) -> list[ClosureBlocker]:
    out: list[ClosureBlocker] = []
    open_apps = db.execute(
        select(func.count())
        .select_from(PortalApplication)
        .where(
            PortalApplication.organization_id == ctx.organization_id,
            PortalApplication.status.notin_([PortalStatus.DRAFT, *TERMINAL]),
        )
    ).scalar_one()
    if open_apps:
        out.append(
            ClosureBlocker(code="OPEN_APPLICATIONS", detail=f"{open_apps} open application(s)")
        )
    members = db.execute(
        select(func.count())
        .select_from(PartnerMembership)
        .where(
            PartnerMembership.organization_id == ctx.organization_id,
            PartnerMembership.status == MembershipStatus.ACTIVE,
            PartnerMembership.user_id != ctx.user.id,
        )
    ).scalar_one()
    if members:
        out.append(ClosureBlocker(code="OTHER_MEMBERS", detail=f"{members} other team member(s)"))
    open_requests = db.execute(
        select(func.count())
        .select_from(DocumentRequest)
        .where(
            DocumentRequest.organization_id == ctx.organization_id,
            DocumentRequest.status == "open",
        )
    ).scalar_one()
    if open_requests:
        out.append(ClosureBlocker(code="OPEN_DOCUMENT_REQUESTS", detail=f"{open_requests} open"))
    return out


@closure.get("/preview", response_model=ApiResponse[ClosurePreview], responses=_ERR)
def closure_preview(ctx: PartnerDep, db: DbSession) -> ApiResponse[ClosurePreview]:
    _owner(ctx)
    blockers = _blockers(db, ctx)
    return ok(
        ClosurePreview(can_close=not blockers, blockers=blockers, retention_note=RETENTION_NOTE)
    )


@closure.post(
    "",
    status_code=201,
    dependencies=[Depends(rate_limit("auth"))],
    response_model=ApiResponse[dict[str, str]],
    responses=_ERR,
    summary="Request account closure (owner, password re-entered; blockers return 409)",
)
def request_closure(
    payload: ClosureIn,
    request: Request,
    ctx: PartnerDep,
    db: DbSession,
    settings: SettingsDep,
    background: BackgroundTasks,
) -> ApiResponse[dict[str, str]]:
    _owner(ctx)
    if ctx.user.password_hash is None or not verify_password(
        settings, ctx.user.password_hash, payload.password
    ):
        raise AppError("Password is incorrect", status_code=400, code="INVALID_CURRENT_PASSWORD")
    blockers = _blockers(db, ctx)
    if blockers:
        raise AppError(
            "Account closure is blocked: " + "; ".join(b.code for b in blockers),
            status_code=409,
            code="CLOSURE_BLOCKED",
        )
    row = create_privacy_request(
        db,
        settings,
        ctx.user.email,
        PrivacyRequestKind.DELETION,
        ("Account closure request. " + (payload.reason or "")).strip(),
        submitted_by=ctx.user.id,
    )
    log_activity(
        db,
        "partner_organization",
        ctx.organization_id,
        "account.closure_requested",
        {"reference": row.reference},
        ActorType.PARTNER,
        actor_user_id=ctx.user.id,
        organization_id=ctx.organization_id,
    )
    db.commit()
    _dispatch(request, settings, background)
    return ok({"reference": row.reference}, "Closure request received")
