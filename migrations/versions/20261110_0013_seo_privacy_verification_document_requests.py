"""content SEO/media fields, privacy-request verification, document requests

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-10 18:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

SEO_COLUMNS = (
    ("seo_title", 200),
    ("seo_description", 300),
    ("canonical_url", 500),
    ("og_title", 200),
    ("og_description", 300),
    ("og_image_url", 500),
    ("image_url", 500),
    ("image_alt", 200),
)


def upgrade() -> None:
    for name, length in SEO_COLUMNS:
        op.add_column("content_items", sa.Column(name, sa.String(length=length), nullable=True))

    op.add_column(
        "privacy_requests",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "privacy_requests",
        sa.Column("verification_token_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "privacy_requests",
        sa.Column("verification_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("privacy_requests", sa.Column("submitted_by_user_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_privacy_requests_submitted_by_user_id_users"),
        "privacy_requests",
        "users",
        ["submitted_by_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        op.f("ix_privacy_requests_verification_token_hash"),
        "privacy_requests",
        ["verification_token_hash"],
        unique=False,
    )
    op.create_index(
        op.f("ix_privacy_requests_submitted_by_user_id"),
        "privacy_requests",
        ["submitted_by_user_id"],
        unique=False,
    )

    op.create_table(
        "document_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=True),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="open", nullable=False),
        sa.Column("fulfilled_document_id", sa.Uuid(), nullable=True),
        sa.Column("fulfilled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["partner_organizations.id"],
            name=op.f("fk_document_requests_organization_id_partner_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["portal_applications.id"],
            name=op.f("fk_document_requests_application_id_portal_applications"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["fulfilled_document_id"],
            ["partner_documents.id"],
            name=op.f("fk_document_requests_fulfilled_document_id_partner_documents"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_document_requests_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'fulfilled', 'cancelled')",
            name=op.f("ck_document_requests_status_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_requests")),
    )
    op.create_index(
        op.f("ix_document_requests_organization_id"), "document_requests", ["organization_id"]
    )
    op.create_index(
        op.f("ix_document_requests_application_id"), "document_requests", ["application_id"]
    )


def downgrade() -> None:
    op.drop_table("document_requests")
    op.drop_index(op.f("ix_privacy_requests_submitted_by_user_id"), table_name="privacy_requests")
    op.drop_index(
        op.f("ix_privacy_requests_verification_token_hash"), table_name="privacy_requests"
    )
    op.drop_constraint(
        op.f("fk_privacy_requests_submitted_by_user_id_users"),
        "privacy_requests",
        type_="foreignkey",
    )
    for column in (
        "submitted_by_user_id",
        "verification_expires_at",
        "verification_token_hash",
        "email_verified_at",
    ):
        op.drop_column("privacy_requests", column)
    for name, _ in reversed(SEO_COLUMNS):
        op.drop_column("content_items", name)
