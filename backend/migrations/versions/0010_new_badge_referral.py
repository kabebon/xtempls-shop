"""Separate NEW badge and referral purchase rewards

Revision ID: 0010
Revises: 0009
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("is_new", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    conn = op.get_bind()
    conn.execute(sa.text(
        "INSERT INTO app_settings (key, value) VALUES "
        "('referral.first_purchase_bonus', '1000'), "
        "('referral.first_purchase_bonus_enabled', 'true'), "
        "('referral.max_bonus_spend_percent', '99'), "
        "('referral.signup_bonus_enabled', 'false') "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
    ))


def downgrade() -> None:
    op.drop_column("products", "is_new")
