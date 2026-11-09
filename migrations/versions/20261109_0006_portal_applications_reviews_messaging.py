"""portal applications reviews messaging

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-09 17:12:53.134251
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE portal_application_seq START 1")
    op.create_table(
        "portal_applications",
        sa.Column("reference", sa.String(length=32), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column(
            "pathway",
            sa.Enum(
                "strategic_merger_integration",
                "direct_project_engagement",
                "vendor_subcontracting",
                name="portal_app_pathway",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "submitted",
                "eligibility_verification",
                "capability_review",
                "commercial_legal_review",
                "pilot_onboarding",
                "scale_up",
                "information_requested",
                "rejected",
                "withdrawn",
                name="portal_app_status",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column(
            "resume_status",
            sa.Enum(
                "draft",
                "submitted",
                "eligibility_verification",
                "capability_review",
                "commercial_legal_review",
                "pilot_onboarding",
                "scale_up",
                "information_requested",
                "rejected",
                "withdrawn",
                name="portal_app_resume_status",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=True,
        ),
        sa.Column("cover_note", sa.Text(), nullable=True),
        sa.Column("assigned_reviewer_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("submission_count", sa.Integer(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
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
            ["assigned_reviewer_id"],
            ["users.id"],
            name=op.f("fk_portal_applications_assigned_reviewer_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_portal_applications_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["partner_organizations.id"],
            name=op.f("fk_portal_applications_organization_id_partner_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portal_applications")),
        sa.UniqueConstraint("reference", name=op.f("uq_portal_applications_reference")),
    )
    op.create_index(
        op.f("ix_portal_applications_assigned_reviewer_id"),
        "portal_applications",
        ["assigned_reviewer_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_portal_applications_organization_id"),
        "portal_applications",
        ["organization_id"],
        unique=False,
    )
    op.create_index("ix_portal_apps_status", "portal_applications", ["status"], unique=False)
    op.create_index(
        "uq_portal_app_one_open_per_org",
        "portal_applications",
        ["organization_id"],
        unique=True,
        postgresql_where=sa.text("status NOT IN ('rejected', 'withdrawn')"),
    )
    op.create_table(
        "application_messages",
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "information_request",
                "partner_response",
                name="message_kind",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "open",
                "answered",
                name="message_status",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=True,
        ),
        sa.Column("author_user_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("requested_categories", postgresql.ARRAY(sa.String(length=50)), nullable=True),
        sa.Column("in_reply_to_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["portal_applications.id"],
            name=op.f("fk_application_messages_application_id_portal_applications"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["author_user_id"],
            ["users.id"],
            name=op.f("fk_application_messages_author_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["in_reply_to_id"],
            ["application_messages.id"],
            name=op.f("fk_application_messages_in_reply_to_id_application_messages"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_messages")),
    )
    op.create_index(
        op.f("ix_application_messages_application_id"),
        "application_messages",
        ["application_id"],
        unique=False,
    )
    op.create_table(
        "application_status_history",
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column(
            "from_status",
            sa.Enum(
                "draft",
                "submitted",
                "eligibility_verification",
                "capability_review",
                "commercial_legal_review",
                "pilot_onboarding",
                "scale_up",
                "information_requested",
                "rejected",
                "withdrawn",
                name="history_from_status",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=True,
        ),
        sa.Column(
            "to_status",
            sa.Enum(
                "draft",
                "submitted",
                "eligibility_verification",
                "capability_review",
                "commercial_legal_review",
                "pilot_onboarding",
                "scale_up",
                "information_requested",
                "rejected",
                "withdrawn",
                name="history_to_status",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("actor_type", sa.String(length=20), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("partner_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name=op.f("fk_application_status_history_actor_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["portal_applications.id"],
            name=op.f("fk_application_status_history_application_id_portal_applications"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_status_history")),
    )
    op.create_index(
        op.f("ix_application_status_history_application_id"),
        "application_status_history",
        ["application_id"],
        unique=False,
    )
    op.create_table(
        "application_submissions",
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("submission_no", sa.Integer(), nullable=False),
        sa.Column("submitted_by", sa.Uuid(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["portal_applications.id"],
            name=op.f("fk_application_submissions_application_id_portal_applications"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["submitted_by"],
            ["users.id"],
            name=op.f("fk_application_submissions_submitted_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_submissions")),
        sa.UniqueConstraint("application_id", "submission_no", name="uq_submission_no"),
    )
    op.create_table(
        "eligibility_verifications",
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("submission_no", sa.Integer(), nullable=False),
        sa.Column("verified_by", sa.Uuid(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_operating_years", sa.Numeric(precision=5, scale=1), nullable=True),
        sa.Column("verified_personnel", sa.Integer(), nullable=True),
        sa.Column("verified_turnover_inr_crore", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column(
            "outcome",
            sa.Enum(
                "verified",
                "verified_with_exception",
                "not_verified",
                "inconclusive",
                name="verification_outcome",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("exception_note", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "supporting_version_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "outcome <> 'verified_with_exception' OR exception_note IS NOT NULL",
            name=op.f("ck_eligibility_verifications_exception_needs_note"),
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["portal_applications.id"],
            name=op.f("fk_eligibility_verifications_application_id_portal_applications"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["verified_by"],
            ["users.id"],
            name=op.f("fk_eligibility_verifications_verified_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eligibility_verifications")),
    )
    op.create_index(
        op.f("ix_eligibility_verifications_application_id"),
        "eligibility_verifications",
        ["application_id"],
        unique=False,
    )
    op.create_table(
        "reviewer_notes",
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["portal_applications.id"],
            name=op.f("fk_reviewer_notes_application_id_portal_applications"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name=op.f("fk_reviewer_notes_author_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reviewer_notes")),
    )
    op.create_index(
        op.f("ix_reviewer_notes_application_id"), "reviewer_notes", ["application_id"], unique=False
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f("ix_reviewer_notes_application_id"), table_name="reviewer_notes")
    op.drop_table("reviewer_notes")
    op.drop_index(
        op.f("ix_eligibility_verifications_application_id"), table_name="eligibility_verifications"
    )
    op.drop_table("eligibility_verifications")
    op.drop_table("application_submissions")
    op.drop_index(
        op.f("ix_application_status_history_application_id"),
        table_name="application_status_history",
    )
    op.drop_table("application_status_history")
    op.drop_index(op.f("ix_application_messages_application_id"), table_name="application_messages")
    op.drop_table("application_messages")
    op.drop_index(
        "uq_portal_app_one_open_per_org",
        table_name="portal_applications",
        postgresql_where=sa.text("status NOT IN ('rejected', 'withdrawn')"),
    )
    op.drop_index("ix_portal_apps_status", table_name="portal_applications")
    op.drop_index(op.f("ix_portal_applications_organization_id"), table_name="portal_applications")
    op.drop_index(
        op.f("ix_portal_applications_assigned_reviewer_id"), table_name="portal_applications"
    )
    op.drop_table("portal_applications")
    op.execute("DROP SEQUENCE portal_application_seq")
