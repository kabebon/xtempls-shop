"""Add promo codes, size_chart, image reorder

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add size_chart JSON column to products
    op.add_column("products", sa.Column("size_chart", sa.JSON(), nullable=True))

    # Add promo_code and discount_amount to order_items
    op.add_column("order_items", sa.Column("promo_code", sa.String(length=50), nullable=True))
    op.add_column("order_items", sa.Column("discount_amount", sa.Numeric(10, 2), nullable=True))

    # Create promo_codes table
    op.create_table(
        "promo_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("discount_percent", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default="true"),
        sa.Column("usage_limit", sa.Integer(), nullable=True),
        sa.Column("used_count", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(op.f("ix_promo_codes_id"), "promo_codes", ["id"], unique=False)
    op.create_index(op.f("ix_promo_codes_code"), "promo_codes", ["code"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_promo_codes_code"), table_name="promo_codes")
    op.drop_index(op.f("ix_promo_codes_id"), table_name="promo_codes")
    op.drop_table("promo_codes")
    op.drop_column("order_items", "discount_amount")
    op.drop_column("order_items", "promo_code")
    op.drop_column("products", "size_chart")
