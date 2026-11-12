"""Authentication / authorization dependencies. Deny by default: every protected route names who
may call it, and tokens are re-checked against the database on every request."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.utilities import utcnow
from app.core.exceptions import AppError
from app.database.dependencies import DbSession
from app.modules.auth.constants import StaffRole, UserStatus, UserType
from app.modules.auth.models import AuthSession, User
from app.modules.auth.security import hash_token
from app.modules.organizations.constants import MembershipRole, MembershipStatus, OrgStatus
from app.modules.organizations.models import PartnerMembership, PartnerOrganization

bearer = HTTPBearer(auto_error=False, description="Opaque access token from POST /auth/login")


def unauthenticated() -> AppError:
    return AppError(
        "Authentication required",
        status_code=401,
        code="UNAUTHENTICATED",
        headers={"WWW-Authenticate": "Bearer"},
    )


def forbidden() -> AppError:
    return AppError(
        "You do not have permission to perform this action", status_code=403, code="FORBIDDEN"
    )


@dataclass(frozen=True)
class AuthContext:
    user: User
    session: AuthSession


@dataclass(frozen=True)
class PartnerContext:
    user: User
    session: AuthSession
    organization_id: uuid.UUID
    role: MembershipRole


@dataclass(frozen=True)
class StaffContext:
    user: User
    session: AuthSession

    @property
    def is_super_admin(self) -> bool:
        return self.user.staff_role is StaffRole.SUPER_ADMINISTRATOR


def get_auth(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> AuthContext:
    """Valid, unexpired session of an active account."""
    if credentials is None or not credentials.credentials:
        raise unauthenticated()
    row = db.execute(
        select(AuthSession, User)
        .join(User, User.id == AuthSession.user_id)
        .where(AuthSession.access_hash == hash_token(credentials.credentials))
    ).first()
    if row is None:
        raise unauthenticated()
    session, user = row
    if (
        session.revoked_at is not None
        or session.access_expires_at <= utcnow()
        or user.status is not UserStatus.ACTIVE
    ):
        raise unauthenticated()
    return AuthContext(user=user, session=session)


AuthDep = Annotated[AuthContext, Depends(get_auth)]


def resolve_membership(db: Session, user: User) -> tuple[PartnerMembership, PartnerOrganization]:
    row = db.execute(
        select(PartnerMembership, PartnerOrganization)
        .join(PartnerOrganization, PartnerOrganization.id == PartnerMembership.organization_id)
        .where(
            PartnerMembership.user_id == user.id,
            PartnerMembership.status == MembershipStatus.ACTIVE,
        )
    ).first()
    if row is None or row[1].status is not OrgStatus.ACTIVE:
        raise forbidden()
    return row[0], row[1]


def require_partner(db: DbSession, auth: AuthDep) -> PartnerContext:
    if auth.user.user_type is not UserType.PARTNER:
        raise forbidden()
    membership, org = resolve_membership(db, auth.user)
    return PartnerContext(auth.user, auth.session, org.id, membership.role)


PartnerDep = Annotated[PartnerContext, Depends(require_partner)]


def require_staff(*roles: StaffRole) -> Callable[[AuthContext], StaffContext]:
    allowed = set(roles)

    def dependency(auth: AuthDep) -> StaffContext:
        user = auth.user
        if user.user_type is not UserType.STAFF or user.staff_role is None:
            raise forbidden()
        if allowed and user.staff_role not in allowed:
            raise forbidden()
        return StaffContext(user, auth.session)

    dependency.allowed_roles = frozenset(allowed)  # type: ignore[attr-defined]
    return dependency


ReviewerDep = Annotated[
    StaffContext,
    Depends(require_staff(StaffRole.PARTNER_REVIEWER, StaffRole.SUPER_ADMINISTRATOR)),
]
SuperAdminDep = Annotated[StaffContext, Depends(require_staff(StaffRole.SUPER_ADMINISTRATOR))]
# Read-only partner collaboration data: BDMs only for organisations assigned to them (D45).
CollabReadDep = Annotated[
    StaffContext,
    Depends(
        require_staff(
            StaffRole.PARTNER_REVIEWER,
            StaffRole.SUPER_ADMINISTRATOR,
            StaffRole.BUSINESS_DEVELOPMENT_MANAGER,
        )
    ),
]
