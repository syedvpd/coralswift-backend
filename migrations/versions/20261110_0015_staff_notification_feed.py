"""staff in-app notification feed

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-10 20:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "staff_notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("record_type", sa.String(length=40), nullable=True),
        sa.Column("record_id", sa.Uuid(), nullable=True),
        sa.Column("is_strategic", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_staff_notifications_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staff_notifications")),
    )
    op.create_index(
        "ix_staff_notifications_user_created",
        "staff_notifications",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("staff_notifications")
