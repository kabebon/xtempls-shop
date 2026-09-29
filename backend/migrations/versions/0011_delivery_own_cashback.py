"""Delivery service and own-purchase cashback

Revision ID: 0011
Revises: 0010
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("delivery_service", sa.String(length=32), nullable=True))
    op.add_column(
        "orders",
        sa.Column("own_cashback_paid", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    conn = op.get_bind()
    conn.execute(sa.text(
        "INSERT INTO app_settings (key, value) VALUES "
        "('referral.own_cashback_enabled', 'true'), "
        "('referral.own_cashback_percent', '5') "
        "ON CONFLICT (key) DO NOTHING"
    ))


def downgrade() -> None:
    op.drop_column("orders", "own_cashback_paid")
    op.drop_column("orders", "delivery_service")
