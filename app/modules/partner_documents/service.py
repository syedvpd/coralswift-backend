"""Versioned private partner documents. Every function is organization-scoped by its arguments;
callers pass the organization id from the authenticated membership, never from request input."""

import logging
import uuid
from datetime import date, timedelta

from fastapi import UploadFile
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.common.utilities import utcnow
from app.core.config import Settings
from app.core.exceptions import AppError, NotFoundError
from app.integrations.storage import Storage, StorageError
from app.modules.admin import settings_service as cfg
from app.modules.auth.dependencies import PartnerContext
from app.modules.documents.constants import ATTACHABLE_STATUSES, UploadStatus
from app.modules.documents.files import validate_upload
from app.modules.enquiries.activity import log_activity
from app.modules.enquiries.constants import ActorType
from app.modules.partner_documents.constants import (
    REQUIRED_CATEGORIES,
    DocStatus,
    PartnerDocCategory,
    ReviewStatus,
)
from app.modules.partner_documents.models import PartnerDocument, PartnerDocumentVersion

logger = logging.getLogger("app.partner_documents")


def get_owned(
    db: Session, organization_id: uuid.UUID, document_id: uuid.UUID, *, lock: bool = False
) -> PartnerDocument:
    """404 (not 403) for other organizations' documents: existence is not revealed."""
    stmt = select(PartnerDocument).where(
        PartnerDocument.id == document_id,
        PartnerDocument.organization_id == organization_id,
        PartnerDocument.status == DocStatus.ACTIVE,
    )
    if lock:
        stmt = stmt.with_for_update()
    doc = db.execute(stmt).scalar_one_or_none()
    if doc is None:
        raise NotFoundError("Document not found")
    return doc


def versions_of(db: Session, document_id: uuid.UUID) -> list[PartnerDocumentVersion]:
    return list(
        db.execute(
            select(PartnerDocumentVersion)
            .where(PartnerDocumentVersion.document_id == document_id)
            .order_by(PartnerDocumentVersion.version_no.desc())
        ).scalars()
    )


def current_version(db: Session, doc: PartnerDocument) -> PartnerDocumentVersion | None:
    return db.execute(
        select(PartnerDocumentVersion).where(
            PartnerDocumentVersion.document_id == doc.id,
            PartnerDocumentVersion.version_no == doc.current_version_no,
        )
    ).scalar_one_or_none()


def _store_version(
    db: Session,
    storage: Storage,
    settings: Settings,
    ctx: PartnerContext,
    doc: PartnerDocument,
    upload: UploadFile,
    expires_on: date | None,
    action: str,
) -> PartnerDocumentVersion:
    data = upload.file.read(settings.max_upload_bytes + 1)  # bounded read
    checked = validate_upload(
        data=data,
        filename=upload.filename,
        declared_type=upload.content_type,
        max_bytes=settings.max_upload_bytes,
    )
    now = utcnow()
    # Random server-side key: no organization id, filename or sequence is encoded in it.
    key = f"partners/portal/{now:%Y/%m}/{uuid.uuid4().hex}.{checked.kind.extension}"
    next_no = (
        db.execute(
            select(func.coalesce(func.max(PartnerDocumentVersion.version_no), 0)).where(
                PartnerDocumentVersion.document_id == doc.id
            )
        ).scalar_one()
        + 1
    )
    version = PartnerDocumentVersion(
        document_id=doc.id,
        version_no=next_no,
        storage_key=key,
        original_filename=checked.display_name,
        content_type=checked.kind.content_type,
        file_size=checked.size,
        checksum=checked.sha256,
        upload_status=UploadStatus.UPLOADING,
        uploaded_by=ctx.user.id,
        uploaded_at=now,
        expires_on=expires_on,
    )
    db.add(version)
    db.commit()  # visible 'uploading' row first; releases the document row lock
    try:
        storage.put(key, data, checked.kind.content_type)
    except StorageError:
        logger.error("partner document storage write failed", extra={"version_id": str(version.id)})
        version.upload_status = UploadStatus.FAILED
        db.commit()
        raise AppError(
            "File storage is unavailable", status_code=503, code="STORAGE_UNAVAILABLE"
        ) from None
    # Finalise under the document lock so concurrent replacements keep the highest version current;
    # populate_existing prevents stale identity-map reads when expire_on_commit=False.
    locked = db.execute(
        select(PartnerDocument)
        .where(PartnerDocument.id == doc.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one()
    version.upload_status = UploadStatus.QUARANTINED  # no malware scanner configured
    locked.current_version_no = max(locked.current_version_no, version.version_no)
    log_activity(
        db,
        "partner_document",
        doc.id,
        action,
        {"category": doc.category.value, "version": version.version_no, "size": version.file_size},
        ActorType.PARTNER,
        actor_user_id=ctx.user.id,
        organization_id=ctx.organization_id,
    )
    db.commit()
    return version


def upload_new(
    db: Session,
    storage: Storage,
    settings: Settings,
    ctx: PartnerContext,
    *,
    upload: UploadFile,
    category: PartnerDocCategory,
    expires_on: date | None,
) -> tuple[PartnerDocument, PartnerDocumentVersion]:
    doc = PartnerDocument(organization_id=ctx.organization_id, category=category)
    db.add(doc)
    db.flush()
    version = _store_version(
        db, storage, settings, ctx, doc, upload, expires_on, "document.uploaded"
    )
    return doc, version


def replace(
    db: Session,
    storage: Storage,
    settings: Settings,
    ctx: PartnerContext,
    document_id: uuid.UUID,
    *,
    upload: UploadFile,
    expires_on: date | None,
) -> tuple[PartnerDocument, PartnerDocumentVersion]:
    doc = get_owned(db, ctx.organization_id, document_id, lock=True)
    version = _store_version(
        db, storage, settings, ctx, doc, upload, expires_on, "document.replaced"
    )
    return doc, version


def remove(db: Session, ctx: PartnerContext, document_id: uuid.UUID) -> None:
    """Soft delete. Files and versions are kept until a retention policy is approved."""
    doc = get_owned(db, ctx.organization_id, document_id, lock=True)
    doc.status = DocStatus.REMOVED
    doc.removed_at = utcnow()
    days = cfg.get_int(db, "retention.partner_document_days")  # unset until policy is approved
    if days:
        db.execute(
            update(PartnerDocumentVersion)
            .where(
                PartnerDocumentVersion.document_id == doc.id,
                PartnerDocumentVersion.retention_date.is_(None),
            )
            .values(retention_date=utcnow() + timedelta(days=days))
        )
    log_activity(
        db,
        "partner_document",
        doc.id,
        "document.removed",
        {"category": doc.category.value},
        ActorType.PARTNER,
        actor_user_id=ctx.user.id,
        organization_id=ctx.organization_id,
    )
    db.commit()


def list_documents(
    db: Session, organization_id: uuid.UUID
) -> list[tuple[PartnerDocument, PartnerDocumentVersion | None]]:
    docs = db.execute(
        select(PartnerDocument)
        .where(
            PartnerDocument.organization_id == organization_id,
            PartnerDocument.status == DocStatus.ACTIVE,
        )
        .order_by(PartnerDocument.created_at)
    ).scalars()
    return [(d, current_version(db, d)) for d in docs]


def read_version(
    db: Session,
    storage: Storage,
    doc: PartnerDocument,
    version_no: int | None,
    *,
    actor_type: ActorType,
    actor_user_id: uuid.UUID,
) -> tuple[bytes, PartnerDocumentVersion]:
    """Fetch bytes for an already-authorised document and audit the access."""
    number = version_no or doc.current_version_no
    version = db.execute(
        select(PartnerDocumentVersion).where(
            PartnerDocumentVersion.document_id == doc.id,
            PartnerDocumentVersion.version_no == number,
        )
    ).scalar_one_or_none()
    if version is None or version.upload_status not in ATTACHABLE_STATUSES:
        raise NotFoundError("Document version not found")
    try:
        data = storage.get(version.storage_key)
    except StorageError:
        raise AppError(
            "File storage is unavailable", status_code=503, code="STORAGE_UNAVAILABLE"
        ) from None
    log_activity(
        db,
        "partner_document",
        doc.id,
        "document.downloaded",
        {"version": version.version_no},
        actor_type,
        actor_user_id=actor_user_id,
        organization_id=doc.organization_id,
    )
    db.commit()
    return data, version


def missing_required_categories(db: Session, organization_id: uuid.UUID) -> list[str]:
    """Required categories with no active, usable, non-rejected current version."""
    rows = db.execute(
        select(PartnerDocument.category)
        .join(
            PartnerDocumentVersion,
            (PartnerDocumentVersion.document_id == PartnerDocument.id)
            & (PartnerDocumentVersion.version_no == PartnerDocument.current_version_no),
        )
        .where(
            PartnerDocument.organization_id == organization_id,
            PartnerDocument.status == DocStatus.ACTIVE,
            PartnerDocumentVersion.upload_status.in_(ATTACHABLE_STATUSES),
            PartnerDocumentVersion.review_status != ReviewStatus.REJECTED,
            # expired evidence no longer counts (expires_on is optional)
            or_(
                PartnerDocumentVersion.expires_on.is_(None),
                PartnerDocumentVersion.expires_on >= date.today(),  # noqa: DTZ011 - calendar date
            ),
        )
    ).scalars()
    present = set(rows)
    return [c.value for c in REQUIRED_CATEGORIES if c not in present]
