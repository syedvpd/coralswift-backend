import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from app.modules.documents.constants import UploadStatus
from app.modules.partner_documents.constants import DocStatus, PartnerDocCategory, ReviewStatus


class PartnerDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Logical document owned by one organization; files live in immutable versions."""

    __tablename__ = "partner_documents"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_organizations.id", ondelete="RESTRICT")
    )
    category: Mapped[PartnerDocCategory] = mapped_column(
        enum_column(PartnerDocCategory, "partner_doc_category")
    )
    status: Mapped[DocStatus] = mapped_column(
        enum_column(DocStatus, "partner_doc_status"), default=DocStatus.ACTIVE
    )
    current_version_no: Mapped[int] = mapped_column(Integer, default=0)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_partner_documents_org_category", "organization_id", "category"),)


class PartnerDocumentVersion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "partner_document_versions"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_documents.id", ondelete="RESTRICT"), index=True
    )
    version_no: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(200), unique=True)  # server-generated, private
    original_filename: Mapped[str] = mapped_column(String(150))  # display only, sanitised
    content_type: Mapped[str] = mapped_column(String(120))  # detected from content
    file_size: Mapped[int] = mapped_column(BigInteger)
    checksum: Mapped[str] = mapped_column(String(64))
    upload_status: Mapped[UploadStatus] = mapped_column(
        enum_column(UploadStatus, "partner_doc_upload_status"), default=UploadStatus.UPLOADING
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_on: Mapped[date | None] = mapped_column(Date)
    review_status: Mapped[ReviewStatus] = mapped_column(
        enum_column(ReviewStatus, "partner_doc_review_status"), default=ReviewStatus.PENDING
    )
    review_comment: Mapped[str | None] = mapped_column(Text)  # reviewer feedback, partner-visible
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retention_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # blob deleted

    __table_args__ = (
        UniqueConstraint("document_id", "version_no", name="uq_document_version_no"),
        CheckConstraint("file_size > 0", name="positive_size"),
        CheckConstraint("length(checksum) = 64", name="sha256_length"),
    )
