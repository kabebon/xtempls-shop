"""Add YooMoney payment fields to orders

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enum для статуса оплаты
    payment_status_enum = sa.Enum(
        "pending", "paid", "failed",
        name="paymentstatus"
    )
    payment_status_enum.create(op.get_bind(), checkfirst=True)

    # Статус оплаты (по умолчанию pending)
    op.add_column(
        "orders",
        sa.Column(
            "payment_status",
            sa.Enum("pending", "paid", "failed", name="paymentstatus"),
            nullable=False,
            server_default="pending",
        ),
    )

    # Уникальный label для связки с ЮМани (например "order_42")
    op.add_column(
        "orders",
        sa.Column("payment_label", sa.String(100), nullable=True),
    )
    op.create_unique_constraint("uq_orders_payment_label", "orders", ["payment_label"])
    op.create_index("ix_orders_payment_label", "orders", ["payment_label"])

    # Итоговая сумма заказа (для генерации ссылки QuickPay)
    op.add_column(
        "orders",
        sa.Column("amount", sa.Numeric(10, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_index("ix_orders_payment_label", table_name="orders")
    op.drop_constraint("uq_orders_payment_label", "orders", type_="unique")
    op.drop_column("orders", "amount")
    op.drop_column("orders", "payment_label")
    op.drop_column("orders", "payment_status")
    sa.Enum(name="paymentstatus").drop(op.get_bind(), checkfirst=True)
