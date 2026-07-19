"""Add delivery_address to orders

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Shipping address — required by the frontend for catalog orders, but kept
    # nullable in the DB so design requests (no shipping) and legacy rows work.
    op.add_column(
        "orders",
        sa.Column("delivery_address", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("orders", "delivery_address")
