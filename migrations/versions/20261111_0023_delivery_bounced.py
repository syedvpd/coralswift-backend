"""delivery bounced

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-11 20:37:15
"""

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

BEFORE = ["pending", "sent", "logged", "failed"]


def _check(values: list[str]) -> None:
    # Relaxation on upgrade; downgrade fails if rows are bounced (no silent data loss).
    name = op.f("ck_notifications_delivery_status")
    op.drop_constraint(name, "notifications", type_="check")
    quoted = ", ".join(f"'{v}'" for v in values)
    op.create_check_constraint(name, "notifications", f"delivery_status IN ({quoted})")


def upgrade() -> None:
    _check([*BEFORE, "bounced"])


def downgrade() -> None:
    _check(BEFORE)
