import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.modules.documents.constants import ATTACHABLE_STATUSES
from app.modules.documents.scan import ScanStatusMixin
from app.modules.partner_documents.constants import PartnerDocCategory
from app.modules.partner_documents.models import PartnerDocument, PartnerDocumentVersion


class VersionOut(ScanStatusMixin):
    version_no: int
    original_filename: str
    content_type: str
    file_size: int
    checksum_sha256: str
    upload_status: str
    expires_on: date | None
    review_status: str
    review_comment: str | None
    uploaded_at: datetime


class DocumentOut(BaseModel):
    id: uuid.UUID
    category: PartnerDocCategory
    status: str
    current_version: VersionOut | None
    can_replace: bool
    can_remove: bool
    can_download: bool


def version_out(v: PartnerDocumentVersion) -> VersionOut:
    """Never includes storage_key or reviewer identity."""
    return VersionOut(
        version_no=v.version_no,
        original_filename=v.original_filename,
        content_type=v.content_type,
        file_size=v.file_size,
        checksum_sha256=v.checksum,
        upload_status=v.upload_status.value,
        expires_on=v.expires_on,
        review_status=v.review_status.value,
        review_comment=v.review_comment,
        uploaded_at=v.uploaded_at,
    )


def document_out(d: PartnerDocument, v: PartnerDocumentVersion | None) -> DocumentOut:
    return DocumentOut(
        id=d.id,
        category=d.category,
        status=d.status.value,
        current_version=version_out(v) if v else None,
        can_replace=d.status.value == "active",
        can_remove=d.status.value == "active",
        can_download=v is not None and v.upload_status in ATTACHABLE_STATUSES,
    )
