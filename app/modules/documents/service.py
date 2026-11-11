import logging
import uuid
from collections.abc import Sequence

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.utilities import utcnow
from app.core.config import Settings
from app.core.exceptions import AppError
from app.integrations.storage import Storage, StorageError
from app.modules.documents.constants import (
    Classification,
    EvidenceCategory,
    OwnerType,
    UploadPurpose,
    UploadStatus,
    attachable_statuses,
)
from app.modules.documents.files import validate_upload
from app.modules.documents.models import Document
from app.modules.documents.scanning import scan_upload
from app.modules.enquiries.activity import log_activity

logger = logging.getLogger("app.documents")

CLASSIFICATION = {
    UploadPurpose.PROJECT_ATTACHMENT: Classification.RESTRICTED,
    UploadPurpose.PARTNER_EVIDENCE: Classification.RESTRICTED,
    UploadPurpose.STRATEGIC_ATTACHMENT: Classification.CONFIDENTIAL,
}


def upload_document(
    db: Session,
    storage: Storage,
    settings: Settings,
    *,
    upload: UploadFile,
    purpose: UploadPurpose,
    category: EvidenceCategory | None,
) -> Document:
    if purpose is UploadPurpose.PARTNER_EVIDENCE and category is None:
        raise AppError(
            "category is required for partner evidence", status_code=422, code="CATEGORY_REQUIRED"
        )
    if purpose is not UploadPurpose.PARTNER_EVIDENCE and category is not None:
        raise AppError(
            "category only applies to partner evidence",
            status_code=422,
            code="CATEGORY_NOT_ALLOWED",
        )

    data = upload.file.read(settings.max_upload_bytes + 1)  # bounded read
    checked = validate_upload(
        data=data,
        filename=upload.filename,
        declared_type=upload.content_type,
        max_bytes=settings.max_upload_bytes,
    )
    now = utcnow()
    # The random key is never derived from the client filename.
    area = "partners" if purpose is UploadPurpose.PARTNER_EVIDENCE else "enquiries"
    key = f"{area}/{now:%Y/%m}/{uuid.uuid4().hex}.{checked.kind.extension}"
    doc = Document(
        purpose=purpose,
        category=category,
        original_filename=checked.display_name,
        storage_key=key,
        content_type=checked.kind.content_type,
        file_size=checked.size,
        checksum=checked.sha256,
        classification=CLASSIFICATION[purpose],
        upload_status=UploadStatus.UPLOADING,
    )
    db.add(doc)
    # Commit the row first, so interrupted writes remain visible as "uploading".
    db.commit()
    try:
        storage.put(key, data, checked.kind.content_type)
    except StorageError:
        logger.error("storage write failed", extra={"document_id": str(doc.id)})
        doc.upload_status = UploadStatus.FAILED
        db.commit()
        raise AppError(
            "File storage is unavailable", status_code=503, code="STORAGE_UNAVAILABLE"
        ) from None
    doc.upload_status = scan_upload(data)
    log_activity(db, "document", doc.id, "document.uploaded", {"purpose": purpose.value})
    db.commit()
    return doc


def attach_documents(
    db: Session,
    *,
    enquiry_id: uuid.UUID,
    document_ids: Sequence[uuid.UUID],
    purpose: UploadPurpose,
    settings: Settings,
) -> int:
    """Claim unattached uploads for an enquiry (same transaction as the enquiry insert)."""
    ids = list(dict.fromkeys(document_ids))
    if not ids:
        return 0
    if len(ids) > settings.max_documents_per_enquiry:
        raise AppError("Too many documents", status_code=422, code="TOO_MANY_DOCUMENTS")
    docs = (
        db.execute(select(Document).where(Document.id.in_(ids)).with_for_update()).scalars().all()
    )
    valid = len(docs) == len(ids) and all(
        d.owner_type is OwnerType.UNATTACHED
        and d.purpose is purpose
        and d.upload_status in attachable_statuses()
        for d in docs
    )
    if not valid:  # one generic error: do not reveal which id exists or who owns it
        raise AppError(
            "One or more documents are invalid", status_code=422, code="INVALID_DOCUMENT_REFERENCE"
        )
    for d in docs:
        d.owner_type = OwnerType.ENQUIRY
        d.owner_id = enquiry_id
    return len(docs)
