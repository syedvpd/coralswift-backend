import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from app.modules.content.constants import ClaimCategory, ClaimStatus, ContentStatus, ContentType


class ContentItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Website content with an approval workflow (PRD s.14, s.15C/E/H) and edit history."""

    __tablename__ = "content_items"

    slug: Mapped[str] = mapped_column(String(120), unique=True)
    content_type: Mapped[ContentType] = mapped_column(enum_column(ContentType, "content_type"))
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(80), index=True)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(40)), default=list)
    status: Mapped[ContentStatus] = mapped_column(
        enum_column(ContentStatus, "content_status"), default=ContentStatus.DRAFT
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    review_note: Mapped[str | None] = mapped_column(Text)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_publish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    claim_ids: Mapped[list[Any]] = mapped_column(JSONB, default=list)  # claims register links
    version_label: Mapped[str | None] = mapped_column(String(40))  # e.g. "2026-11" for documents
    attachment_key: Mapped[str | None] = mapped_column(String(200), unique=True)
    attachment_filename: Mapped[str | None] = mapped_column(String(150))
    attachment_content_type: Mapped[str | None] = mapped_column(String(120))
    attachment_size: Mapped[int | None] = mapped_column(BigInteger)
    attachment_checksum: Mapped[str | None] = mapped_column(String(64))
    # SEO / social metadata and a cover image reference (https URLs only, validated at the API)
    seo_title: Mapped[str | None] = mapped_column(String(200))
    seo_description: Mapped[str | None] = mapped_column(String(300))
    canonical_url: Mapped[str | None] = mapped_column(String(500))
    og_title: Mapped[str | None] = mapped_column(String(200))
    og_description: Mapped[str | None] = mapped_column(String(300))
    og_image_url: Mapped[str | None] = mapped_column(String(500))
    image_url: Mapped[str | None] = mapped_column(String(500))
    image_alt: Mapped[str | None] = mapped_column(String(200))
    # Added in 0020: markdown/plain body flag, structured block data, last editor
    body_format: Mapped[str] = mapped_column(String(10), default="plain", server_default="plain")
    data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )

    __table_args__ = (
        CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="slug_format"),
        Index("ix_content_status_published", "status", "published_at"),
        Index("ix_content_status_scheduled", "status", "scheduled_publish_at"),
    )


class ContentVersion(UUIDPrimaryKeyMixin, Base):
    """Immutable snapshot taken on every edit (version control, PRD s.28)."""

    __tablename__ = "content_versions"

    content_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_items.id", ondelete="RESTRICT"), index=True
    )
    version_no: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    edited_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("content_id", "version_no", name="uq_content_version_no"),)


class ContentClaim(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Content/claims register (PRD s.28): each public claim has an owner and an evidence status."""

    __tablename__ = "content_claims"

    claim_text: Mapped[str] = mapped_column(Text)
    category: Mapped[ClaimCategory] = mapped_column(enum_column(ClaimCategory, "claim_category"))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    evidence_status: Mapped[ClaimStatus] = mapped_column(
        enum_column(ClaimStatus, "claim_status"), default=ClaimStatus.PENDING_VERIFICATION
    )
    evidence_ref: Mapped[str | None] = mapped_column(String(300))
    publication_permission: Mapped[bool] = mapped_column(Boolean, default=False)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
