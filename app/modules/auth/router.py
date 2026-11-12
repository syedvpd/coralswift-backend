import uuid
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select

from app.common.responses import ApiResponse, ErrorResponse, ok
from app.core.config import Settings, get_settings
from app.core.exceptions import NotFoundError
from app.core.protection import client_ip, rate_limit
from app.database.dependencies import DbSession
from app.modules.auth import service
from app.modules.auth.constants import StaffRole, UserType
from app.modules.auth.dependencies import AuthDep
from app.modules.auth.models import AuthSession, User
from app.modules.auth.permissions import permissions_for, role_matrix
from app.modules.auth.schemas import (
    AcceptInvitationIn,
    ChangePasswordIn,
    LoginIn,
    MeOut,
    OrganizationRef,
    PasswordResetConfirmIn,
    PasswordResetRequestIn,
    ProfileUpdateIn,
    RefreshIn,
    SessionOut,
    TokenOut,
)
from app.modules.notifications.service import dispatch_notifications
from app.modules.organizations.constants import PARTNER_PERMISSIONS
from app.modules.organizations.models import PartnerOrganization

router = APIRouter(prefix="/auth", tags=["auth"])
SettingsDep = Annotated[Settings, Depends(get_settings)]
_ERR: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    429: {"model": ErrorResponse},
}
AUTH_LIMIT = [Depends(rate_limit("auth"))]
GENERIC_RESET_MESSAGE = "If an account exists for this address, a reset email has been sent"


def _tokens(pair: service.TokenPair) -> TokenOut:
    return TokenOut(
        access_token=pair.access_token, refresh_token=pair.refresh_token, expires_in=pair.expires_in
    )


def _dispatch(request: Request, settings: Settings, background: BackgroundTasks) -> None:
    background.add_task(
        dispatch_notifications,
        request.app.state.sessionmaker,
        request.app.state.email_sender,
        settings,
    )


@router.post(
    "/login",
    response_model=ApiResponse[TokenOut],
    dependencies=AUTH_LIMIT,
    responses=_ERR,
    summary="Sign in (partner or staff)",
)
def login(
    payload: LoginIn, request: Request, db: DbSession, settings: SettingsDep
) -> ApiResponse[TokenOut]:
    """Generic 401 for unknown email, wrong password, locked or inactive account."""
    pair, user = service.login(
        db,
        settings,
        email=payload.email,
        password=payload.password,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    del user
    return ok(_tokens(pair), "Signed in")


@router.post(
    "/refresh",
    response_model=ApiResponse[TokenOut],
    dependencies=AUTH_LIMIT,
    responses=_ERR,
    summary="Rotate tokens (the old refresh token stops working; reuse revokes the session)",
)
def refresh(payload: RefreshIn, db: DbSession, settings: SettingsDep) -> ApiResponse[TokenOut]:
    return ok(
        _tokens(service.refresh_session(db, settings, payload.refresh_token)), "Tokens renewed"
    )


@router.post(
    "/logout", response_model=ApiResponse[None], responses=_ERR, summary="Revoke this session"
)
def logout(auth: AuthDep, db: DbSession) -> ApiResponse[None]:
    service.revoke_session(db, auth.session, "logout")
    db.commit()
    return ok(None, "Signed out")


@router.post(
    "/invitations/accept",
    response_model=ApiResponse[None],
    dependencies=AUTH_LIMIT,
    responses={400: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    summary="Activate an invited account and set the password",
)
def accept_invitation(
    payload: AcceptInvitationIn, db: DbSession, settings: SettingsDep
) -> ApiResponse[None]:
    service.accept_invitation(db, settings, payload.token, payload.password)
    return ok(None, "Account activated")


@router.post(
    "/password-reset/request",
    status_code=202,
    response_model=ApiResponse[None],
    dependencies=AUTH_LIMIT,
    summary="Request a password reset email (always answers the same way)",
)
def password_reset_request(
    payload: PasswordResetRequestIn,
    request: Request,
    db: DbSession,
    settings: SettingsDep,
    background: BackgroundTasks,
) -> ApiResponse[None]:
    service.request_password_reset(db, settings, payload.email)
    _dispatch(request, settings, background)
    return ok(None, GENERIC_RESET_MESSAGE)


@router.post(
    "/password-reset/confirm",
    response_model=ApiResponse[None],
    dependencies=AUTH_LIMIT,
    responses={400: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    summary="Set a new password with a single-use token; revokes all sessions",
)
def password_reset_confirm(
    payload: PasswordResetConfirmIn, db: DbSession, settings: SettingsDep
) -> ApiResponse[None]:
    service.confirm_password_reset(db, settings, payload.token, payload.new_password)
    return ok(None, "Password updated")


@router.post(
    "/change-password",
    response_model=ApiResponse[None],
    dependencies=AUTH_LIMIT,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
    summary="Change your own password (staff and partners); your other sessions are signed out",
)
def change_password(
    payload: ChangePasswordIn, auth: AuthDep, db: DbSession, settings: SettingsDep
) -> ApiResponse[None]:
    service.change_password(
        db, settings, auth.user, auth.session, payload.current_password, payload.new_password
    )
    return ok(None, "Password updated")


class EndpointRef(BaseModel):
    method: str
    path: str


class ModulePermission(BaseModel):
    module: str
    endpoints: list[EndpointRef]


class PermissionsOut(BaseModel):
    account_type: str
    staff_role: str | None
    modules: list[ModulePermission]
    role_matrix: dict[str, list[str]] | None = None  # super administrators only


@router.get(
    "/permissions",
    response_model=ApiResponse[PermissionsOut],
    response_model_exclude_none=True,  # role_matrix is present only for super administrators
    responses=_ERR,
    summary="Endpoints this account may call, derived from the live route guards",
)
def my_permissions(auth: AuthDep, request: Request) -> ApiResponse[PermissionsOut]:
    data = permissions_for(request.app, auth.user.user_type, auth.user.staff_role)
    if auth.user.staff_role is StaffRole.SUPER_ADMINISTRATOR:
        data["role_matrix"] = role_matrix(request.app)
    return ok(PermissionsOut.model_validate(data))


def _me_out(db: DbSession, settings: Settings, user: User) -> MeOut:
    org_ref = None
    partner_role = None
    membership = None
    if user.user_type is UserType.PARTNER:
        membership = service.active_membership(db, user.id)
        org = db.get(PartnerOrganization, membership.organization_id) if membership else None
        org_ref = OrganizationRef(id=org.id, legal_name=org.legal_name) if org else None
        partner_role = membership.role.value if membership else None
    return MeOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        phone=user.phone,
        user_type=user.user_type,
        account_status=user.status,
        staff_role=user.staff_role,
        partner_role=partner_role,
        permissions=list(PARTNER_PERMISSIONS[membership.role]) if membership else [],
        organization=org_ref,
        last_login_at=user.last_login_at,
    )


@router.get("/me", response_model=ApiResponse[MeOut], responses=_ERR, summary="Current account")
def me(auth: AuthDep, db: DbSession, settings: SettingsDep) -> ApiResponse[MeOut]:
    return ok(_me_out(db, settings, auth.user))


@router.patch(
    "/me",
    response_model=ApiResponse[MeOut],
    responses={**_ERR, 422: {"model": ErrorResponse}},
    summary="Update your own name and phone (staff and partners); audited",
)
def update_my_profile(
    payload: ProfileUpdateIn, auth: AuthDep, db: DbSession, settings: SettingsDep
) -> ApiResponse[MeOut]:
    user = service.update_profile(
        db, auth.user.id, {k: getattr(payload, k) for k in payload.model_fields_set}
    )
    return ok(_me_out(db, settings, user), "Profile updated")


@router.get("/sessions", response_model=ApiResponse[list[SessionOut]], responses=_ERR)
def list_sessions(auth: AuthDep, db: DbSession) -> ApiResponse[list[SessionOut]]:
    rows = db.execute(
        select(AuthSession)
        .where(AuthSession.user_id == auth.user.id, AuthSession.revoked_at.is_(None))
        .order_by(AuthSession.created_at.desc())
    ).scalars()
    return ok(
        [
            SessionOut(
                id=s.id,
                created_at=s.created_at,
                last_used_at=s.last_used_at,
                user_agent=s.user_agent,
                current=s.id == auth.session.id,
                expires_at=s.refresh_expires_at,
            )
            for s in rows
        ]
    )


@router.delete(
    "/sessions",
    response_model=ApiResponse[dict[str, int]],
    responses=_ERR,
    summary="Sign out every other session of your account",
)
def revoke_other_sessions(auth: AuthDep, db: DbSession) -> ApiResponse[dict[str, int]]:
    return ok({"revoked": service.revoke_other_sessions(db, auth.user, auth.session)})


@router.delete(
    "/sessions/{session_id}",
    response_model=ApiResponse[None],
    responses={**_ERR, 404: {"model": ErrorResponse}},
    summary="Revoke one of your own sessions",
)
def revoke(session_id: uuid.UUID, auth: AuthDep, db: DbSession) -> ApiResponse[None]:
    session = db.execute(
        select(AuthSession).where(AuthSession.id == session_id, AuthSession.user_id == auth.user.id)
    ).scalar_one_or_none()
    if session is None:
        raise NotFoundError("Session not found")
    service.revoke_session(db, session, "user_revoked")
    db.commit()
    return ok(None, "Session revoked")
