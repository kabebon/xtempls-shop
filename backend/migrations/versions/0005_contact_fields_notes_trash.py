"""Add customer_phone/customer_telegram, admin_note and soft-delete columns to orders

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Контактные поля: разделённые телефон и Telegram-ник
    op.add_column(
        "orders",
        sa.Column("customer_phone", sa.String(30), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column("customer_telegram", sa.String(100), nullable=True),
    )

    # Внутренние заметки менеджера
    op.add_column(
        "orders",
        sa.Column("admin_note", sa.Text(), nullable=True),
    )

    # Soft-delete для корзины удалённых заказов
    op.add_column(
        "orders",
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "orders",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_orders_is_deleted", "orders", ["is_deleted"])


def downgrade() -> None:
    op.drop_index("ix_orders_is_deleted", table_name="orders")
    op.drop_column("orders", "deleted_at")
    op.drop_column("orders", "is_deleted")
    op.drop_column("orders", "admin_note")
    op.drop_column("orders", "customer_telegram")
    op.drop_column("orders", "customer_phone")
