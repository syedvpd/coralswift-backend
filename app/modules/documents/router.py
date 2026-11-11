from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import BaseModel

from app.common.responses import ApiResponse, ErrorResponse, ok
from app.core.config import Settings, get_settings
from app.core.protection import rate_limit, require_human
from app.database.dependencies import DbSession
from app.modules.documents.constants import EvidenceCategory, UploadPurpose
from app.modules.documents.service import upload_document

router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentOut(BaseModel):
    document_id: str
    original_filename: str
    content_type: str
    file_size: int
    checksum_sha256: str
    upload_status: str


@router.post(
    "/upload",
    status_code=201,
    response_model=ApiResponse[DocumentOut],
    dependencies=[Depends(rate_limit("upload", 2)), Depends(require_human)],
    responses={
        403: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        415: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
    summary="Upload a supporting document (private storage, quarantined)",
)
def upload(
    request: Request,
    db: DbSession,
    settings: Annotated[Settings, Depends(get_settings)],
    file: Annotated[UploadFile, File(description="pdf, png, jpg, docx or xlsx")],
    purpose: Annotated[UploadPurpose, Form()],
    category: Annotated[EvidenceCategory | None, Form()] = None,
) -> ApiResponse[DocumentOut]:
    """Returns a `document_id` to pass in `document_ids` when submitting an enquiry.
    Files are stored privately and are never downloadable via the public API."""
    doc = upload_document(
        db, request.app.state.storage, settings, upload=file, purpose=purpose, category=category
    )
    return ok(
        DocumentOut(
            document_id=str(doc.id),
            original_filename=doc.original_filename,
            content_type=doc.content_type,
            file_size=doc.file_size,
            checksum_sha256=doc.checksum,
            upload_status=doc.upload_status.value,
        ),
        "Document uploaded",
    )
