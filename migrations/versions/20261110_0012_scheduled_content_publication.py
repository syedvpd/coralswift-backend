"""schedule future publication of approved content

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-10 15:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("content_items", sa.Column("scheduled_publish_at", sa.DateTime(timezone=True)))
    op.create_index(
        op.f("ix_content_status_scheduled"),
        "content_items",
        ["status", "scheduled_publish_at"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_content_status_scheduled"), table_name="content_items")
    op.drop_column("content_items", "scheduled_publish_at")
