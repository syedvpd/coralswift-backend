"""phase 1 public submissions

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-09 16:15:31.991909
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Gap-tolerant, never-reused counter behind CS-ENQ-<year>-<nnnnnn> (concurrency safe).
    op.execute("CREATE SEQUENCE enquiry_reference_seq START 1")
    op.create_table(
        "activities",
        sa.Column("record_type", sa.String(length=50), nullable=False),
        sa.Column("record_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column(
            "actor_type",
            sa.Enum(
                "public",
                "system",
                "staff",
                name="activity_actor_type",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_activities")),
    )
    op.create_index(
        "ix_activities_record", "activities", ["record_type", "record_id"], unique=False
    )
    op.create_table(
        "companies",
        sa.Column("legal_name", sa.String(length=200), nullable=False),
        sa.Column("website", sa.String(length=300), nullable=True),
        sa.Column("year_established", sa.SmallInteger(), nullable=True),
        sa.Column("registered_address", sa.String(length=500), nullable=True),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.Column("business_category", sa.String(length=100), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("country ~ '^[A-Z]{2}$'", name=op.f("ck_companies_country_iso2")),
        sa.CheckConstraint(
            "year_established BETWEEN 1800 AND 2100", name=op.f("ck_companies_year_range")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_companies")),
    )
    op.create_table(
        "idempotency_keys",
        sa.Column("scope", sa.String(length=100), nullable=False),
        sa.Column("client_hash", sa.String(length=64), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False),
        sa.Column("response_status", sa.SmallInteger(), nullable=True),
        sa.Column("response_body", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_idempotency_keys")),
        sa.UniqueConstraint("scope", "client_hash", "key", name="uq_idempotency_scope_client_key"),
    )
    op.create_index("ix_idempotency_expires_at", "idempotency_keys", ["expires_at"], unique=False)
    op.create_table(
        "contacts",
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column("full_name", sa.String(length=150), nullable=False),
        sa.Column("designation", sa.String(length=150), nullable=True),
        sa.Column("business_email", sa.String(length=254), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column(
            "consent_status",
            sa.Enum(
                "granted",
                "withdrawn",
                name="consent_status",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("consent_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consent_notice_version", sa.String(length=50), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("country ~ '^[A-Z]{2}$'", name=op.f("ck_contacts_country_iso2")),
        sa.CheckConstraint("phone ~ '^\\+[0-9]{7,15}$'", name=op.f("ck_contacts_phone_e164")),
        sa.CheckConstraint(
            "business_email = lower(business_email)", name=op.f("ck_contacts_email_lowercase")
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_contacts_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contacts")),
    )
    op.create_index(
        op.f("ix_contacts_business_email"), "contacts", ["business_email"], unique=False
    )
    op.create_index(op.f("ix_contacts_company_id"), "contacts", ["company_id"], unique=False)
    op.create_table(
        "enquiries",
        sa.Column("reference_number", sa.String(length=32), nullable=False),
        sa.Column(
            "enquiry_type",
            sa.Enum(
                "general",
                "project",
                "partner",
                "strategic",
                name="enquiry_type",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "received",
                "in_review",
                "closed",
                name="enquiry_status",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column(
            "priority",
            sa.Enum(
                "low",
                "normal",
                "high",
                name="enquiry_priority",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("assigned_owner", sa.String(length=100), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_enquiries_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["contact_id"],
            ["contacts.id"],
            name=op.f("fk_enquiries_contact_id_contacts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_enquiries")),
        sa.UniqueConstraint("reference_number", name=op.f("uq_enquiries_reference_number")),
    )
    op.create_index(op.f("ix_enquiries_company_id"), "enquiries", ["company_id"], unique=False)
    op.create_index(op.f("ix_enquiries_contact_id"), "enquiries", ["contact_id"], unique=False)
    op.create_index(
        "ix_enquiries_type_status_created",
        "enquiries",
        ["enquiry_type", "status", "created_at"],
        unique=False,
    )
    op.create_table(
        "documents",
        sa.Column(
            "owner_type",
            sa.Enum(
                "unattached",
                "enquiry",
                name="document_owner_type",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.Column(
            "purpose",
            sa.Enum(
                "project_attachment",
                "partner_evidence",
                "strategic_attachment",
                name="upload_purpose",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column(
            "category",
            sa.Enum(
                "registration_proof",
                "operating_history",
                "employee_strength",
                "financial_statements",
                "service_portfolio",
                "infrastructure_summary",
                "client_references",
                name="evidence_category",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=True,
        ),
        sa.Column("original_filename", sa.String(length=150), nullable=False),
        sa.Column("storage_key", sa.String(length=200), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column(
            "classification",
            sa.Enum(
                "restricted",
                "confidential",
                name="document_classification",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column(
            "upload_status",
            sa.Enum(
                "uploading",
                "quarantined",
                "clean",
                "rejected",
                "failed",
                name="upload_status",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "(owner_type = 'unattached' AND owner_id IS NULL) OR (owner_type = 'enquiry' AND owner_id IS NOT NULL)",
            name=op.f("ck_documents_owner_consistent"),
        ),
        sa.CheckConstraint("file_size > 0", name=op.f("ck_documents_positive_size")),
        sa.CheckConstraint("length(checksum) = 64", name=op.f("ck_documents_sha256_length")),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["enquiries.id"],
            name=op.f("fk_documents_owner_id_enquiries"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_documents_storage_key")),
    )
    op.create_index("ix_documents_owner", "documents", ["owner_type", "owner_id"], unique=False)
    op.create_index(
        "ix_documents_status_uploaded", "documents", ["upload_status", "uploaded_at"], unique=False
    )
    op.create_table(
        "notifications",
        sa.Column("enquiry_id", sa.Uuid(), nullable=True),
        sa.Column("recipient", sa.String(length=254), nullable=False),
        sa.Column(
            "notification_type",
            sa.Enum(
                "acknowledgement",
                "internal",
                name="notification_type",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column(
            "template_key",
            sa.Enum(
                "ack_general",
                "ack_project",
                "ack_partner",
                "ack_strategic",
                "internal_new_enquiry",
                name="template_key",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "delivery_status",
            sa.Enum(
                "pending",
                "sent",
                "logged",
                "failed",
                name="delivery_status",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("retry_count", sa.SmallInteger(), nullable=False),
        sa.Column("provider_reference", sa.String(length=120), nullable=True),
        sa.Column("last_error", sa.String(length=300), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dedupe_key", sa.String(length=320), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("retry_count >= 0", name=op.f("ck_notifications_retry_non_negative")),
        sa.ForeignKeyConstraint(
            ["enquiry_id"],
            ["enquiries.id"],
            name=op.f("fk_notifications_enquiry_id_enquiries"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
        sa.UniqueConstraint("dedupe_key", name=op.f("uq_notifications_dedupe_key")),
    )
    op.create_index(
        op.f("ix_notifications_enquiry_id"), "notifications", ["enquiry_id"], unique=False
    )
    op.create_index(
        "ix_notifications_status_created",
        "notifications",
        ["delivery_status", "created_at"],
        unique=False,
    )
    op.create_table(
        "partner_applications",
        sa.Column("enquiry_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column(
            "preferred_engagement_pathway",
            sa.Enum(
                "strategic_merger_integration",
                "direct_project_engagement",
                "vendor_subcontracting",
                name="engagement_pathway",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column(
            "workforce_range",
            sa.Enum(
                "under_50",
                "50_to_100",
                "101_to_250",
                "over_250",
                name="workforce_range",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column(
            "turnover_range",
            sa.Enum(
                "under_inr_2_crore",
                "inr_2_to_10_crore",
                "over_inr_10_crore",
                name="turnover_range",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("service_categories", postgresql.ARRAY(sa.String(length=50)), nullable=False),
        sa.Column("infrastructure_summary", sa.Text(), nullable=False),
        sa.Column("client_experience", sa.Text(), nullable=False),
        sa.Column("client_references", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "application_status",
            sa.Enum(
                "submitted",
                "under_review",
                name="application_status",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "cardinality(service_categories) >= 1",
            name=op.f("ck_partner_applications_has_service_category"),
        ),
        sa.CheckConstraint(
            "jsonb_array_length(client_references) >= 2",
            name=op.f("ck_partner_applications_two_client_references"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_partner_applications_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["enquiry_id"],
            ["enquiries.id"],
            name=op.f("fk_partner_applications_enquiry_id_enquiries"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_partner_applications")),
        sa.UniqueConstraint("enquiry_id", name=op.f("uq_partner_applications_enquiry_id")),
    )
    op.create_index(
        op.f("ix_partner_applications_application_status"),
        "partner_applications",
        ["application_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_partner_applications_company_id"),
        "partner_applications",
        ["company_id"],
        unique=False,
    )
    op.create_table(
        "project_enquiries",
        sa.Column("enquiry_id", sa.Uuid(), nullable=False),
        sa.Column(
            "project_category",
            sa.Enum(
                "erp_implementation",
                "web_app_development",
                "custom_software",
                "cloud_infrastructure",
                "testing_maintenance",
                "medical_coding_billing",
                "healthcare_support",
                "data_entry",
                "document_processing",
                "banking_kyc",
                "mortgage_processing",
                "mutual_fund_operations",
                "back_office",
                name="project_category",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("requirement_summary", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("expected_timeline", sa.String(length=200), nullable=False),
        sa.Column("estimated_volume", sa.String(length=200), nullable=True),
        sa.Column("geography", sa.String(length=200), nullable=False),
        sa.Column("security_constraints", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["enquiry_id"],
            ["enquiries.id"],
            name=op.f("fk_project_enquiries_enquiry_id_enquiries"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_enquiries")),
        sa.UniqueConstraint("enquiry_id", name=op.f("uq_project_enquiries_enquiry_id")),
    )
    op.create_index(
        op.f("ix_project_enquiries_project_category"),
        "project_enquiries",
        ["project_category"],
        unique=False,
    )
    op.create_table(
        "strategic_enquiries",
        sa.Column("enquiry_id", sa.Uuid(), nullable=False),
        sa.Column(
            "discussion_type",
            sa.Enum(
                "merger",
                "integration",
                "strategic_partnership",
                name="discussion_type",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("business_overview", sa.Text(), nullable=False),
        sa.Column("confidential_summary", sa.Text(), nullable=False),
        sa.Column(
            "access_classification",
            sa.Enum(
                "restricted",
                "confidential",
                name="strategic_access_classification",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["enquiry_id"],
            ["enquiries.id"],
            name=op.f("fk_strategic_enquiries_enquiry_id_enquiries"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_strategic_enquiries")),
        sa.UniqueConstraint("enquiry_id", name=op.f("uq_strategic_enquiries_enquiry_id")),
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("strategic_enquiries")
    op.drop_index(op.f("ix_project_enquiries_project_category"), table_name="project_enquiries")
    op.drop_table("project_enquiries")
    op.drop_index(op.f("ix_partner_applications_company_id"), table_name="partner_applications")
    op.drop_index(
        op.f("ix_partner_applications_application_status"), table_name="partner_applications"
    )
    op.drop_table("partner_applications")
    op.drop_index("ix_notifications_status_created", table_name="notifications")
    op.drop_index(op.f("ix_notifications_enquiry_id"), table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_documents_status_uploaded", table_name="documents")
    op.drop_index("ix_documents_owner", table_name="documents")
    op.drop_table("documents")
    op.drop_index("ix_enquiries_type_status_created", table_name="enquiries")
    op.drop_index(op.f("ix_enquiries_contact_id"), table_name="enquiries")
    op.drop_index(op.f("ix_enquiries_company_id"), table_name="enquiries")
    op.drop_table("enquiries")
    op.drop_index(op.f("ix_contacts_company_id"), table_name="contacts")
    op.drop_index(op.f("ix_contacts_business_email"), table_name="contacts")
    op.drop_table("contacts")
    op.drop_index("ix_idempotency_expires_at", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")
    op.drop_table("companies")
    op.drop_index("ix_activities_record", table_name="activities")
    op.drop_table("activities")
    op.execute("DROP SEQUENCE enquiry_reference_seq")
