"""gap closure columns: token revocation, notification read state, follow-up kind/assignee/cancel

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-10 12:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("auth_tokens", sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("notifications", sa.Column("read_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "enquiry_followups",
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="follow_up"),
    )
    op.add_column("enquiry_followups", sa.Column("assignee_id", sa.Uuid(), nullable=True))
    op.add_column(
        "enquiry_followups", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_enquiry_followups_assignee_id_users"),
        "enquiry_followups",
        "users",
        ["assignee_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        op.f("ix_enquiry_followups_assignee_id"), "enquiry_followups", ["assignee_id"], unique=False
    )
    op.create_check_constraint(
        op.f("ck_enquiry_followups_kind_valid"),
        "enquiry_followups",
        "kind IN ('note', 'follow_up', 'communication')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_enquiry_followups_kind_valid"), "enquiry_followups", type_="check")
    op.drop_index(op.f("ix_enquiry_followups_assignee_id"), table_name="enquiry_followups")
    op.drop_constraint(
        op.f("fk_enquiry_followups_assignee_id_users"), "enquiry_followups", type_="foreignkey"
    )
    op.drop_column("enquiry_followups", "cancelled_at")
    op.drop_column("enquiry_followups", "assignee_id")
    op.drop_column("enquiry_followups", "kind")
    op.drop_column("notifications", "read_at")
    op.drop_column("auth_tokens", "revoked_at")
