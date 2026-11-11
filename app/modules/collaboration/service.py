"""Shared helpers: staff organisation scope, reference numbers, document ownership checks."""

import secrets
import uuid
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.common.utilities import utcnow
from app.core.exceptions import AppError, NotFoundError
from app.modules.applications.constants import PortalStatus
from app.modules.applications.models import PortalApplication
from app.modules.auth.constants import StaffRole, UserType
from app.modules.auth.dependencies import StaffContext
from app.modules.auth.models import User
from app.modules.collaboration.models import OrganizationBdmAssignment
from app.modules.organizations.models import PartnerOrganization
from app.modules.partner_documents.constants import DocStatus
from app.modules.partner_documents.models import PartnerDocument

STAFF_LABEL = "CoralSwift Team"


def reference(prefix: str) -> str:
    return f"{prefix}-{utcnow().year}-{secrets.token_hex(4).upper()}"


def reviewer_org_ids(staff: StaffContext) -> Select[Any]:
    """Organisations a non-super-admin may reach. Reviewers: those whose application is assigned
    to them. Business development managers (read-only, D45): those with an active explicit
    assignment (`organization_bdm_assignments`)."""
    if staff.user.staff_role is StaffRole.BUSINESS_DEVELOPMENT_MANAGER:
        return select(OrganizationBdmAssignment.organization_id).where(
            OrganizationBdmAssignment.user_id == staff.user.id,
            OrganizationBdmAssignment.removed_at.is_(None),
        )
    return select(PortalApplication.organization_id).where(
        PortalApplication.assigned_reviewer_id == staff.user.id,
        PortalApplication.status != PortalStatus.DRAFT,
    )


def require_org(
    db: Session, staff: StaffContext, organization_id: uuid.UUID
) -> PartnerOrganization:
    """Super administrators reach every organisation; reviewers only their assigned ones.
    Others look nonexistent (404) so organisation ids are not probeable."""
    stmt = select(PartnerOrganization).where(PartnerOrganization.id == organization_id)
    if not staff.is_super_admin:
        stmt = stmt.where(PartnerOrganization.id.in_(reviewer_org_ids(staff)))
    org = db.execute(stmt).scalar_one_or_none()
    if org is None:
        raise NotFoundError("Organisation not found")
    return org


def org_scope(staff: StaffContext, column):  # type: ignore[no-untyped-def]
    """Boolean clause limiting a query's organisation column to what the staff member may see."""
    return column.in_(reviewer_org_ids(staff)) if not staff.is_super_admin else column.is_not(None)


def owned_documents(
    db: Session, organization_id: uuid.UUID, document_ids: list[uuid.UUID]
) -> list[uuid.UUID]:
    """Every id must be an active document of this organisation, else 422 (no existence leak)."""
    ids = list(dict.fromkeys(document_ids))
    if not ids:
        return []
    found = set(
        db.execute(
            select(PartnerDocument.id).where(
                PartnerDocument.id.in_(ids),
                PartnerDocument.organization_id == organization_id,
                PartnerDocument.status == DocStatus.ACTIVE,
            )
        ).scalars()
    )
    if found != set(ids):
        raise AppError(
            "One or more documents are not available for this organisation",
            status_code=422,
            code="INVALID_DOCUMENT",
        )
    return ids


def author_label(user: User) -> str:
    """Staff are shown to partners under the team label, never by personal name."""
    return STAFF_LABEL if user.user_type is UserType.STAFF else user.full_name
