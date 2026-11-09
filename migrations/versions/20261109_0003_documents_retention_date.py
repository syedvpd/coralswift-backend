"""documents retention date

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-09
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Additive and nullable: stays empty until a retention policy is approved (PRD s.19).
    op.add_column(
        "documents", sa.Column("retention_date", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("documents", "retention_date")
