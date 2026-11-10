import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile

from app.common.responses import ApiResponse, ErrorResponse, ok
from app.core.config import Settings, get_settings
from app.core.protection import rate_limit
from app.database.dependencies import DbSession
from app.modules.auth.dependencies import PartnerDep
from app.modules.enquiries.constants import ActorType
from app.modules.partner_documents import requests, service
from app.modules.partner_documents.constants import PartnerDocCategory
from app.modules.partner_documents.schemas import (
    DocumentOut,
    VersionOut,
    document_out,
    version_out,
)

router = APIRouter(prefix="/partner/documents", tags=["partner-documents"])
SettingsDep = Annotated[Settings, Depends(get_settings)]
_ERR: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    413: {"model": ErrorResponse},
    415: {"model": ErrorResponse},
}
UPLOAD_LIMIT = [Depends(rate_limit("partner-upload", 2))]
FileField = Annotated[UploadFile, File(description="pdf, png, jpg, docx or xlsx")]
ExpiresField = Annotated[date | None, Form(description="Optional document expiry date")]


@router.post(
    "",
    status_code=201,
    response_model=ApiResponse[DocumentOut],
    dependencies=UPLOAD_LIMIT,
    responses=_ERR,
    summary="Upload a new document (private, quarantined; no malware scanner configured)",
)
def upload(
    request: Request,
    ctx: PartnerDep,
    db: DbSession,
    settings: SettingsDep,
    file: FileField,
    category: Annotated[PartnerDocCategory, Form()],
    expires_on: ExpiresField = None,
    request_id: Annotated[
        uuid.UUID | None, Form(description="Fulfils this document request")
    ] = None,
) -> ApiResponse[DocumentOut]:
    pending = (
        requests.open_request_for_upload(db, ctx, request_id, category) if request_id else None
    )
    doc, version = service.upload_new(
        db,
        request.app.state.storage,
        settings,
        ctx,
        upload=file,
        category=category,
        expires_on=expires_on,
    )
    if pending is not None:
        requests.mark_fulfilled(db, pending, doc.id, ctx.user.id)
    return ok(document_out(doc, version), "Document uploaded")


@router.get(
    "", response_model=ApiResponse[list[DocumentOut]], responses=_ERR, summary="Own documents"
)
def list_own(ctx: PartnerDep, db: DbSession) -> ApiResponse[list[DocumentOut]]:
    return ok([document_out(d, v) for d, v in service.list_documents(db, ctx.organization_id)])


@router.get("/{document_id}", response_model=ApiResponse[DocumentOut], responses=_ERR)
def get_one(document_id: uuid.UUID, ctx: PartnerDep, db: DbSession) -> ApiResponse[DocumentOut]:
    doc = service.get_owned(db, ctx.organization_id, document_id)
    return ok(document_out(doc, service.current_version(db, doc)))


@router.post(
    "/{document_id}/versions",
    status_code=201,
    response_model=ApiResponse[DocumentOut],
    dependencies=UPLOAD_LIMIT,
    responses=_ERR,
    summary="Replace a document with a new version (old versions are kept)",
)
def replace(
    document_id: uuid.UUID,
    request: Request,
    ctx: PartnerDep,
    db: DbSession,
    settings: SettingsDep,
    file: FileField,
    expires_on: ExpiresField = None,
) -> ApiResponse[DocumentOut]:
    doc, version = service.replace(
        db,
        request.app.state.storage,
        settings,
        ctx,
        document_id,
        upload=file,
        expires_on=expires_on,
    )
    return ok(document_out(doc, version), "Document replaced")


@router.get("/{document_id}/history", response_model=ApiResponse[list[VersionOut]], responses=_ERR)
def history(
    document_id: uuid.UUID, ctx: PartnerDep, db: DbSession
) -> ApiResponse[list[VersionOut]]:
    doc = service.get_owned(db, ctx.organization_id, document_id)
    return ok([version_out(v) for v in service.versions_of(db, doc.id)])


@router.get(
    "/{document_id}/download",
    responses={**_ERR, 200: {"content": {"application/octet-stream": {}}}},
    summary="Download a document you own (authorised, audited; no public URLs exist)",
)
def download(
    document_id: uuid.UUID,
    request: Request,
    ctx: PartnerDep,
    db: DbSession,
    version: Annotated[int | None, Query(ge=1)] = None,
) -> Response:
    doc = service.get_owned(db, ctx.organization_id, document_id)
    data, ver = service.read_version(
        db,
        request.app.state.storage,
        doc,
        version,
        actor_type=ActorType.PARTNER,
        actor_user_id=ctx.user.id,
    )
    return Response(
        content=data,
        media_type=ver.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="document-{ver.version_no}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.delete("/{document_id}", response_model=ApiResponse[None], responses=_ERR)
def remove(document_id: uuid.UUID, ctx: PartnerDep, db: DbSession) -> ApiResponse[None]:
    """Soft delete: data is retained until a retention policy is approved."""
    service.remove(db, ctx, document_id)
    return ok(None, "Document removed")
