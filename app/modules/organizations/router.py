from typing import Any

from fastapi import APIRouter

from app.common.responses import ApiResponse, ErrorResponse, ok
from app.database.dependencies import DbSession
from app.modules.auth.dependencies import PartnerDep
from app.modules.organizations import service
from app.modules.organizations.schemas import (
    CompletionOut,
    EditableFieldOut,
    OrganizationOut,
    ProfileUpdate,
    RevisionOut,
)

router = APIRouter(prefix="/partner/organization", tags=["partner-organization"])
_ERR: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
}


@router.get(
    "", response_model=ApiResponse[OrganizationOut], responses=_ERR, summary="Own organization"
)
def get_own(ctx: PartnerDep, db: DbSession) -> ApiResponse[OrganizationOut]:
    """The organization is taken from the authenticated membership, never from the request."""
    org = service.get_organization(db, ctx.organization_id)
    return ok(OrganizationOut.model_validate(org))


@router.put(
    "",
    response_model=ApiResponse[OrganizationOut],
    responses={**_ERR, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    summary="Update own profile (partial update, recorded in history)",
)
def update_own(
    ctx: PartnerDep, db: DbSession, payload: ProfileUpdate
) -> ApiResponse[OrganizationOut]:
    org = service.update_profile(db, ctx, payload)
    return ok(OrganizationOut.model_validate(org), "Profile saved")


@router.get("/completion", response_model=ApiResponse[CompletionOut], responses=_ERR)
def get_completion(ctx: PartnerDep, db: DbSession) -> ApiResponse[CompletionOut]:
    return ok(service.completion(service.get_organization(db, ctx.organization_id)))


@router.get(
    "/editable-fields",
    response_model=ApiResponse[list[EditableFieldOut]],
    responses=_ERR,
    summary="Profile fields and direct-update/null-clearing behavior",
)
def editable_fields(ctx: PartnerDep) -> ApiResponse[list[EditableFieldOut]]:
    del ctx  # authentication is required; metadata is shared by every partner
    return ok(
        [
            EditableFieldOut(
                name=name,
                direct_update=True,
                approval_required=False,
                nullable=name != "legal_name",
                null_clears=name != "legal_name",
            )
            for name in ProfileUpdate.model_fields
            if name != "expected_version"
        ]
    )


@router.get("/history", response_model=ApiResponse[list[RevisionOut]], responses=_ERR)
def get_history(ctx: PartnerDep, db: DbSession) -> ApiResponse[list[RevisionOut]]:
    return ok(
        [
            RevisionOut(
                version=r.version,
                changed_by=r.changed_by,
                changes=r.changes,
                created_at=r.created_at,
            )
            for r in service.list_revisions(db, ctx.organization_id)
        ]
    )
