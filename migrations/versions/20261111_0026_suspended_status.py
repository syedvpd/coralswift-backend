"""suspended user status

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-11 18:00:00
"""

from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None

CK = "ck_users_user_status"
BEFORE = "'invited','active','deactivated'"


def _check(values: str) -> None:
    op.drop_constraint(op.f(CK), "users", type_="check")
    op.create_check_constraint(op.f(CK), "users", f"status IN ({values})")


def upgrade() -> None:
    _check(BEFORE + ",'suspended'")  # relaxation only


def downgrade() -> None:
    # Fails while any account is suspended (no silent data loss).
    _check(BEFORE)
