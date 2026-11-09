import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, UUIDPrimaryKeyMixin, enum_column
from app.modules.documents.constants import (
    Classification,
    EvidenceCategory,
    OwnerType,
    UploadPurpose,
    UploadStatus,
)


class Document(UUIDPrimaryKeyMixin, Base):
    """Metadata only. The bytes live in private storage under `storage_key`, which is never
    returned to clients."""

    __tablename__ = "documents"

    owner_type: Mapped[OwnerType] = mapped_column(
        enum_column(OwnerType, "document_owner_type"), default=OwnerType.UNATTACHED
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("enquiries.id", ondelete="RESTRICT")
    )
    purpose: Mapped[UploadPurpose] = mapped_column(enum_column(UploadPurpose, "upload_purpose"))
    category: Mapped[EvidenceCategory | None] = mapped_column(
        enum_column(EvidenceCategory, "evidence_category")
    )
    original_filename: Mapped[str] = mapped_column(String(150))  # display only, sanitised
    storage_key: Mapped[str] = mapped_column(String(200), unique=True)
    content_type: Mapped[str] = mapped_column(String(120))  # detected, not client-declared
    file_size: Mapped[int] = mapped_column(BigInteger)
    checksum: Mapped[str] = mapped_column(String(64))  # SHA-256 hex
    classification: Mapped[Classification] = mapped_column(
        enum_column(Classification, "document_classification")
    )
    upload_status: Mapped[UploadStatus] = mapped_column(
        enum_column(UploadStatus, "upload_status"), default=UploadStatus.UPLOADING
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Null until a retention policy is approved (PRD s.19 / open decision).
    retention_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("file_size > 0", name="positive_size"),
        CheckConstraint("length(checksum) = 64", name="sha256_length"),
        CheckConstraint(
            "(owner_type = 'unattached' AND owner_id IS NULL)"
            " OR (owner_type = 'enquiry' AND owner_id IS NOT NULL)",
            name="owner_consistent",
        ),
        Index("ix_documents_owner", "owner_type", "owner_id"),
        Index("ix_documents_status_uploaded", "upload_status", "uploaded_at"),
    )
