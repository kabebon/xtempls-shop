"""Make orders.customer_contact nullable (now that phone/telegram are separate)

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Колонка customer_contact была NOT NULL с начальной миграции.
    # Теперь контакты хранятся в отдельных полях customer_phone /
    # customer_telegram, поэтому customer_contact должна быть nullable.
    op.alter_column(
        "orders",
        "customer_contact",
        existing_type=sa.String(length=200),
        nullable=True,
    )


def downgrade() -> None:
    # Внимание: при откате строки с NULL в customer_contact нужно заполнить,
    # иначе DROP NOT NULL упадёт. Заполняем значением из customer_phone.
    op.execute(
        "UPDATE orders SET customer_contact = customer_phone "
        "WHERE customer_contact IS NULL AND customer_phone IS NOT NULL"
    )
    op.execute(
        "UPDATE orders SET customer_contact = '@' || customer_telegram "
        "WHERE customer_contact IS NULL AND customer_telegram IS NOT NULL"
    )
    op.alter_column(
        "orders",
        "customer_contact",
        existing_type=sa.String(length=200),
        nullable=False,
    )
