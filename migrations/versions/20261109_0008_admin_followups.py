"""Phase 3: lead owner, next follow-up, follow-up history (additive)

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-09
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("enquiries", sa.Column("assigned_user_id", sa.Uuid(), nullable=True))
    op.add_column(
        "enquiries", sa.Column("next_follow_up_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_enquiries_assigned_user_id_users"),
        "enquiries",
        "users",
        ["assigned_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(op.f("ix_enquiries_assigned_user_id"), "enquiries", ["assigned_user_id"])
    op.create_index(op.f("ix_enquiries_next_follow_up_at"), "enquiries", ["next_follow_up_at"])
    op.create_table(
        "enquiry_followups",
        sa.Column("enquiry_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["enquiry_id"],
            ["enquiries.id"],
            name=op.f("fk_enquiry_followups_enquiry_id_enquiries"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name=op.f("fk_enquiry_followups_author_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_enquiry_followups")),
    )
    op.create_index(
        op.f("ix_enquiry_followups_enquiry_id"), "enquiry_followups", ["enquiry_id"], unique=False
    )
    op.create_index("ix_followups_open_due", "enquiry_followups", ["completed_at", "due_at"])


def downgrade() -> None:
    op.drop_index("ix_followups_open_due", table_name="enquiry_followups")
    op.drop_index(op.f("ix_enquiry_followups_enquiry_id"), table_name="enquiry_followups")
    op.drop_table("enquiry_followups")
    op.drop_index(op.f("ix_enquiries_next_follow_up_at"), table_name="enquiries")
    op.drop_index(op.f("ix_enquiries_assigned_user_id"), table_name="enquiries")
    op.drop_constraint(op.f("fk_enquiries_assigned_user_id_users"), "enquiries", type_="foreignkey")
    op.drop_column("enquiries", "next_follow_up_at")
    op.drop_column("enquiries", "assigned_user_id")
