"""Authentication: login, sessions, invitations, password reset. Caller owns no transactions:
each public function commits its own unit of work (security events must persist even on failure)."""

import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.utilities import utcnow
from app.core.config import Settings
from app.core.exceptions import AppError
from app.modules.admin import settings_service as cfg
from app.modules.auth.constants import StaffRole, TokenPurpose, UserStatus, UserType
from app.modules.auth.models import AuthSession, AuthToken, User
from app.modules.auth.policy import effective_settings
from app.modules.auth.security import (
    burn_verify,
    hash_password,
    hash_token,
    new_token,
    validate_password_policy,
    verify_password,
)
from app.modules.enquiries.activity import log_activity
from app.modules.enquiries.constants import ActorType
from app.modules.notifications.constants import NotificationType, TemplateKey
from app.modules.notifications.service import queue_notification
from app.modules.organizations.constants import MembershipRole, MembershipStatus
from app.modules.organizations.models import PartnerMembership, PartnerOrganization

logger = logging.getLogger("app.auth")


def _invalid_credentials() -> AppError:
    return AppError("Invalid email or password", status_code=401, code="INVALID_CREDENTIALS")


def _invalid_refresh() -> AppError:
    return AppError(
        "Invalid or expired refresh token", status_code=401, code="INVALID_REFRESH_TOKEN"
    )


def _invalid_token() -> AppError:
    return AppError("Invalid or expired token", status_code=400, code="INVALID_OR_EXPIRED_TOKEN")


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int
    session_id: uuid.UUID


def active_membership(db: Session, user_id: uuid.UUID) -> PartnerMembership | None:
    return db.execute(
        select(PartnerMembership).where(
            PartnerMembership.user_id == user_id,
            PartnerMembership.status == MembershipStatus.ACTIVE,
        )
    ).scalar_one_or_none()


def _actor(user: User) -> ActorType:
    return ActorType.PARTNER if user.user_type is UserType.PARTNER else ActorType.REVIEWER


def _audit(db: Session, user: User, action: str, meta: dict[str, object] | None = None) -> None:
    membership = active_membership(db, user.id) if user.user_type is UserType.PARTNER else None
    log_activity(
        db,
        "user",
        user.id,
        action,
        meta,
        _actor(user),
        actor_user_id=user.id,
        organization_id=membership.organization_id if membership else None,
    )


def update_profile(db: Session, user_id: uuid.UUID, changes: dict[str, str | None]) -> User:
    """Own display name / phone for staff and partners. Audited by field name only."""
    user = db.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one()
    changed = sorted(k for k, v in changes.items() if getattr(user, k) != v)
    for k in changed:
        setattr(user, k, changes[k])
    if changed:
        _audit(db, user, "auth.profile_updated", {"fields": changed})
        db.commit()
    return user


def revoke_other_sessions(db: Session, user: User, current: AuthSession) -> int:
    result = db.execute(
        update(AuthSession)
        .where(
            AuthSession.user_id == user.id,
            AuthSession.id != current.id,
            AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=utcnow(), revoked_reason="signed_out_others")
    )
    _audit(db, user, "auth.other_sessions_revoked")
    db.commit()
    return int(getattr(result, "rowcount", 0))


# ---------------------------------------------------------------- sessions
def issue_session(
    db: Session, settings: Settings, user: User, ip: str | None, user_agent: str | None
) -> TokenPair:
    now = utcnow()
    access, refresh = new_token(), new_token()
    session = AuthSession(
        user_id=user.id,
        access_hash=hash_token(access),
        access_expires_at=now + timedelta(minutes=settings.access_token_expire_minutes),
        refresh_hash=hash_token(refresh),
        refresh_expires_at=now + timedelta(minutes=settings.refresh_token_expire_minutes),
        ip_hash=hashlib.sha256(ip.encode()).hexdigest() if ip else None,
        user_agent=(user_agent or "")[:200] or None,
        created_at=now,
    )
    db.add(session)
    db.flush()
    return TokenPair(access, refresh, settings.access_token_expire_minutes * 60, session.id)


def login(
    db: Session,
    settings: Settings,
    *,
    email: str,
    password: str,
    ip: str | None,
    user_agent: str | None,
) -> tuple[TokenPair, User]:
    settings = effective_settings(db, settings)
    email = email.strip().lower()
    now = utcnow()
    user = db.execute(
        select(User).where(User.email == email).with_for_update()
    ).scalar_one_or_none()
    if user is not None and user.status is UserStatus.INVITED and user.password_hash is None:
        # Frontend requirement P1.8: tell an invited person to activate. This confirms that a
        # pending invitation exists for the address (accepted trade-off, rate limited).
        burn_verify(settings, password)
        raise AppError(
            "This account has not been activated yet. Use the invitation link.",
            status_code=403,
            code="ACCOUNT_NOT_ACTIVATED",
        )
    if user is None or user.password_hash is None or user.status is not UserStatus.ACTIVE:
        if (
            user is not None
            and user.password_hash is not None
            and user.status in (UserStatus.DEACTIVATED, UserStatus.SUSPENDED)
            and verify_password(settings, user.password_hash, password)
        ):
            if user.status is UserStatus.SUSPENDED:
                raise AppError(
                    "This account has been suspended", status_code=403, code="ACCOUNT_SUSPENDED"
                )
            raise AppError(
                "This account has been deactivated", status_code=403, code="ACCOUNT_DEACTIVATED"
            )
        burn_verify(settings, password)
        raise _invalid_credentials()
    if user.locked_until and user.locked_until > now:
        proved = verify_password(settings, user.password_hash, password)
        _audit(db, user, "auth.login_blocked_locked")
        db.commit()
        if proved:  # only someone holding the password learns the account is locked
            raise AppError(
                "This account is temporarily locked after repeated failed sign-ins",
                status_code=423,
                code="ACCOUNT_LOCKED",
            )
        raise _invalid_credentials()  # same response as a wrong password
    if not verify_password(settings, user.password_hash, password):
        user.failed_login_count += 1
        meta: dict[str, object] = {"failed_count": user.failed_login_count}
        max_failures = cfg.get_int(db, "security.login_max_failures") or settings.login_max_failures
        lock_minutes = (
            cfg.get_int(db, "security.login_lockout_minutes") or settings.login_lockout_minutes
        )
        if user.failed_login_count >= max_failures:
            user.locked_until = now + timedelta(minutes=lock_minutes)
            user.failed_login_count = 0
            meta["locked"] = True
        _audit(db, user, "auth.login_failed", meta)
        db.commit()
        raise _invalid_credentials()
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    pair = issue_session(db, settings, user, ip, user_agent)
    _audit(db, user, "auth.login", {"session_id": str(pair.session_id)})
    db.commit()
    return pair, user


def refresh_session(db: Session, settings: Settings, refresh_token: str) -> TokenPair:
    settings = effective_settings(db, settings)
    h = hash_token(refresh_token)
    now = utcnow()
    session = db.execute(
        select(AuthSession)
        .where(or_(AuthSession.refresh_hash == h, AuthSession.prev_refresh_hash == h))
        .with_for_update()
    ).scalar_one_or_none()
    if session is None:
        raise _invalid_refresh()
    user = db.get(User, session.user_id)
    if session.prev_refresh_hash == h and session.refresh_hash != h:
        # An already-rotated refresh token was presented again: treat as theft, kill the session.
        session.revoked_at = session.revoked_at or now
        session.revoked_reason = "refresh_reuse"
        if user:
            _audit(db, user, "auth.refresh_reuse_detected", {"session_id": str(session.id)})
        db.commit()
        raise _invalid_refresh()
    if (
        session.revoked_at is not None
        or session.refresh_expires_at <= now
        or user is None
        or user.status is not UserStatus.ACTIVE
    ):
        raise _invalid_refresh()
    access, refresh = new_token(), new_token()
    session.prev_refresh_hash = session.refresh_hash
    session.refresh_hash = hash_token(refresh)
    session.access_hash = hash_token(access)
    session.access_expires_at = now + timedelta(minutes=settings.access_token_expire_minutes)
    session.last_used_at = now
    db.commit()
    return TokenPair(access, refresh, settings.access_token_expire_minutes * 60, session.id)


def revoke_session(db: Session, session: AuthSession, reason: str) -> None:
    if session.revoked_at is None:
        session.revoked_at = utcnow()
        session.revoked_reason = reason


def revoke_all_sessions(db: Session, user_id: uuid.UUID, reason: str) -> None:
    db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=utcnow(), revoked_reason=reason)
    )


# ------------------------------------------------------------ one-time tokens
def _create_token(
    db: Session, user: User, purpose: TokenPurpose, ttl: timedelta
) -> tuple[str, AuthToken]:
    now = utcnow()
    # Newer token supersedes older unused tokens of the same purpose.
    db.execute(
        update(AuthToken)
        .where(
            AuthToken.user_id == user.id,
            AuthToken.purpose == purpose,
            AuthToken.used_at.is_(None),
            AuthToken.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    raw = new_token()
    row = AuthToken(
        purpose=purpose,
        token_hash=hash_token(raw),
        user_id=user.id,
        created_at=now,
        expires_at=now + ttl,
    )
    db.add(row)
    db.flush()
    return raw, row


def _consume_token(db: Session, raw: str, purpose: TokenPurpose) -> uuid.UUID:
    """Atomically mark a token used; only one caller can ever win."""
    row = db.execute(
        update(AuthToken)
        .where(
            AuthToken.token_hash == hash_token(raw),
            AuthToken.purpose == purpose,
            AuthToken.used_at.is_(None),
            AuthToken.revoked_at.is_(None),
            AuthToken.expires_at > utcnow(),
        )
        .values(used_at=utcnow())
        .returning(AuthToken.user_id)
    ).first()
    if row is None:
        raise _token_failure(db, raw, purpose)
    return uuid.UUID(str(row[0]))


def _token_failure(db: Session, raw: str, purpose: TokenPurpose) -> AppError:
    """Why a one-time token cannot be used. The token is a 256-bit secret, so naming the reason
    reveals nothing to someone who does not already hold it."""
    row = db.execute(
        select(AuthToken).where(
            AuthToken.token_hash == hash_token(raw), AuthToken.purpose == purpose
        )
    ).scalar_one_or_none()
    if row is None:
        return _invalid_token()
    if row.used_at is not None:
        return AppError("This link was already used", status_code=400, code="TOKEN_ALREADY_USED")
    if row.revoked_at is not None:
        return AppError(
            "This link was cancelled or replaced", status_code=400, code="TOKEN_REVOKED"
        )
    return AppError("This link has expired", status_code=400, code="TOKEN_EXPIRED")


def _link(settings: Settings, path: str, raw: str) -> str:
    return f"{settings.portal_base_url.rstrip('/')}{path}?token={raw}"


# ----------------------------------------------------------------- invitation
def invite_partner_user(
    db: Session,
    settings: Settings,
    *,
    inviter: User,
    email: str,
    full_name: str,
    organization: PartnerOrganization,
    role: MembershipRole = MembershipRole.OWNER,
) -> None:
    """Create or re-issue a pending partner account for an organization. Caller commits."""
    settings = effective_settings(db, settings)
    email = email.strip().lower()
    user = db.execute(
        select(User).where(User.email == email).with_for_update()
    ).scalar_one_or_none()
    if user is None:
        user = User(
            email=email, full_name=full_name, user_type=UserType.PARTNER, status=UserStatus.INVITED
        )
        db.add(user)
        db.flush()
    elif user.user_type is not UserType.PARTNER or user.status is not UserStatus.INVITED:
        raise AppError(
            "An account already exists for this email", status_code=409, code="EMAIL_IN_USE"
        )
    membership = db.execute(
        select(PartnerMembership).where(
            PartnerMembership.user_id == user.id,
            PartnerMembership.organization_id == organization.id,
        )
    ).scalar_one_or_none()
    if membership is not None and membership.status is MembershipStatus.REMOVED:
        membership.status, membership.role = MembershipStatus.ACTIVE, role  # cancelled invite
    if membership is None:
        db.add(PartnerMembership(organization_id=organization.id, user_id=user.id, role=role))
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise AppError(
                "User already belongs to another organization", status_code=409, code="EMAIL_IN_USE"
            ) from None
    raw, token = _create_token(
        db, user, TokenPurpose.INVITATION, timedelta(hours=settings.invitation_ttl_hours)
    )
    queue_notification(
        db,
        recipient=user.email,
        kind=NotificationType.ACCOUNT,
        template=TemplateKey.PARTNER_INVITATION,
        context={"name": user.full_name, "link": _link(settings, "/activate", raw)},
        dedupe_key=f"invite:{token.id}",
    )
    log_activity(
        db,
        "user",
        user.id,
        "auth.invitation_issued",
        {"organization_id": str(organization.id)},
        ActorType.REVIEWER,
        actor_user_id=inviter.id,
        organization_id=organization.id,
    )


def accept_invitation(db: Session, settings: Settings, token: str, password: str) -> User:
    # Check the policy first so a weak password does not burn the one-time token.
    settings = effective_settings(db, settings)
    row = db.execute(
        select(AuthToken).where(
            AuthToken.token_hash == hash_token(token), AuthToken.purpose == TokenPurpose.INVITATION
        )
    ).scalar_one_or_none()
    if row is None:
        raise _invalid_token()
    user = db.get(User, row.user_id)
    if user is None:
        raise _invalid_token()
    validate_password_policy(settings, password, user.email)
    user_id = _consume_token(db, token, TokenPurpose.INVITATION)
    user = db.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one()
    if user.status in (UserStatus.DEACTIVATED, UserStatus.SUSPENDED):
        raise _invalid_token()
    user.password_hash = hash_password(settings, password)
    user.status = UserStatus.ACTIVE
    user.email_verified_at = utcnow()
    _audit(db, user, "auth.account_activated")
    db.commit()
    return user


# ------------------------------------------------------------- password reset
def request_password_reset(db: Session, settings: Settings, email: str) -> None:
    """Never reveals whether the address has an account (caller always answers 202)."""
    settings = effective_settings(db, settings)
    user = db.execute(
        select(User).where(User.email == email.strip().lower()).with_for_update()
    ).scalar_one_or_none()
    if user is None or user.status is not UserStatus.ACTIVE:
        return
    raw, token = _create_token(
        db,
        user,
        TokenPurpose.PASSWORD_RESET,
        timedelta(minutes=settings.password_reset_ttl_minutes),
    )
    queue_notification(
        db,
        recipient=user.email,
        kind=NotificationType.ACCOUNT,
        template=TemplateKey.PASSWORD_RESET,
        context={"name": user.full_name, "link": _link(settings, "/reset-password", raw)},
        dedupe_key=f"reset:{token.id}",
    )
    _audit(db, user, "auth.password_reset_requested")
    db.commit()


def confirm_password_reset(db: Session, settings: Settings, token: str, new_password: str) -> None:
    settings = effective_settings(db, settings)
    row = db.execute(
        select(AuthToken).where(
            AuthToken.token_hash == hash_token(token),
            AuthToken.purpose == TokenPurpose.PASSWORD_RESET,
        )
    ).scalar_one_or_none()
    if row is None:
        raise _invalid_token()
    user_row = db.get(User, row.user_id)
    if user_row is None:
        raise _invalid_token()
    validate_password_policy(settings, new_password, user_row.email)
    user_id = _consume_token(db, token, TokenPurpose.PASSWORD_RESET)
    user = db.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one()
    if user.status is not UserStatus.ACTIVE:
        raise _invalid_token()
    user.password_hash = hash_password(settings, new_password)
    user.failed_login_count = 0
    user.locked_until = None
    revoke_all_sessions(db, user.id, "password_reset")  # every old token dies
    _audit(db, user, "auth.password_reset_completed")
    db.commit()


# --------------------------------------------------------------- staff helper
def create_staff_user(
    db: Session, settings: Settings, *, email: str, full_name: str, role: StaffRole, password: str
) -> User:
    """Used by scripts/create_staff_user.py only; there is no public path to create staff."""
    settings = effective_settings(db, settings)
    validate_password_policy(settings, password, email)
    user = User(
        email=email.strip().lower(),
        full_name=full_name,
        user_type=UserType.STAFF,
        staff_role=role,
        status=UserStatus.ACTIVE,
        password_hash=hash_password(settings, password),
        email_verified_at=utcnow(),
    )
    db.add(user)
    db.flush()
    log_activity(
        db, "user", user.id, "auth.staff_account_created", {"role": role.value}, ActorType.SYSTEM
    )
    return user


def invite_staff_user(
    db: Session,
    settings: Settings,
    *,
    inviter: User,
    email: str,
    full_name: str,
    role: StaffRole,
) -> User:
    """Super administrator creates a pending staff account; the invitee sets a password."""
    settings = effective_settings(db, settings)
    email = email.strip().lower()
    if db.execute(select(User).where(User.email == email)).scalar_one_or_none() is not None:
        raise AppError(
            "An account already exists for this email", status_code=409, code="EMAIL_IN_USE"
        )
    user = User(
        email=email,
        full_name=full_name,
        user_type=UserType.STAFF,
        staff_role=role,
        status=UserStatus.INVITED,
    )
    db.add(user)
    db.flush()
    raw, token = _create_token(
        db, user, TokenPurpose.INVITATION, timedelta(hours=settings.invitation_ttl_hours)
    )
    queue_notification(
        db,
        recipient=user.email,
        kind=NotificationType.ACCOUNT,
        template=TemplateKey.PARTNER_INVITATION,
        context={"name": user.full_name, "link": _link(settings, "/activate", raw)},
        dedupe_key=f"invite:{token.id}",
    )
    log_activity(
        db,
        "user",
        user.id,
        "admin.staff_invited",
        {"role": role.value},
        ActorType.STAFF,
        actor_user_id=inviter.id,
    )
    return user


# ------------------------------------------------------------ password change
def change_password(
    db: Session,
    settings: Settings,
    user: User,
    session: AuthSession,
    current_password: str,
    new_password: str,
) -> None:
    """Authenticated password change. Other sessions of the account are revoked; this one stays."""
    settings = effective_settings(db, settings)
    if user.password_hash is None or not verify_password(
        settings, user.password_hash, current_password
    ):
        _audit(db, user, "auth.password_change_failed")
        db.commit()
        raise AppError(
            "Current password is incorrect", status_code=400, code="INVALID_CURRENT_PASSWORD"
        )
    validate_password_policy(settings, new_password, user.email)
    if verify_password(settings, user.password_hash, new_password):
        raise AppError(
            "The new password must differ from the current one",
            status_code=422,
            code="PASSWORD_UNCHANGED",
        )
    user.password_hash = hash_password(settings, new_password)
    db.execute(
        update(AuthSession)
        .where(
            AuthSession.user_id == user.id,
            AuthSession.id != session.id,
            AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=utcnow(), revoked_reason="password_changed")
    )
    _audit(db, user, "auth.password_changed")
    db.commit()


# ------------------------------------------------------- invitation lifecycle
def invitation_state(db: Session, user: User) -> str:
    """none | pending | expired | revoked | accepted for the user's latest invitation."""
    if user.status is not UserStatus.INVITED:
        return "accepted" if user.status is UserStatus.ACTIVE else "none"
    row = db.execute(
        select(AuthToken)
        .where(AuthToken.user_id == user.id, AuthToken.purpose == TokenPurpose.INVITATION)
        .order_by(AuthToken.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        return "none"
    if row.used_at is not None:
        return "accepted"
    if row.revoked_at is not None:
        return "revoked"
    return "expired" if row.expires_at <= utcnow() else "pending"


def resend_invitation(db: Session, settings: Settings, actor: User, user: User) -> None:
    """Issue a fresh invitation link for an account that has not been activated. Caller commits."""
    settings = effective_settings(db, settings)
    if user.status is not UserStatus.INVITED:
        raise AppError(
            "Only accounts that have not been activated can be re-invited",
            status_code=409,
            code="NOT_INVITED",
        )
    raw, token = _create_token(
        db, user, TokenPurpose.INVITATION, timedelta(hours=settings.invitation_ttl_hours)
    )
    queue_notification(
        db,
        recipient=user.email,
        kind=NotificationType.ACCOUNT,
        template=TemplateKey.PARTNER_INVITATION,
        context={"name": user.full_name, "link": _link(settings, "/activate", raw)},
        dedupe_key=f"invite:{token.id}",
    )
    log_activity(
        db,
        "user",
        user.id,
        "auth.invitation_resent",
        {},
        ActorType.STAFF,
        actor_user_id=actor.id,
    )


def revoke_invitation(db: Session, actor: User, user: User) -> None:
    """Cancel every unused invitation link. The account stays un-activated and can be re-invited."""
    if user.status is not UserStatus.INVITED:
        raise AppError(
            "Only accounts that have not been activated have an open invitation",
            status_code=409,
            code="NOT_INVITED",
        )
    db.execute(
        update(AuthToken)
        .where(
            AuthToken.user_id == user.id,
            AuthToken.purpose == TokenPurpose.INVITATION,
            AuthToken.used_at.is_(None),
            AuthToken.revoked_at.is_(None),
        )
        .values(revoked_at=utcnow())
    )
    log_activity(
        db,
        "user",
        user.id,
        "auth.invitation_revoked",
        {},
        ActorType.STAFF,
        actor_user_id=actor.id,
    )
