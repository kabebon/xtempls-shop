"""Referral program: personal promo codes, bonus spend, settings

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-13

Additive only — no drops of existing data.
  - promo_codes.kind / owner_user_id / cashback_percent
  - backfill a referral promo row for every existing user
  - orders.bonus_spent / referral_cashback_paid / bonus_refunded
  - users.referral_signup_bonus_paid
  - tg_users.pending_ref_code
  - bonus_transactions.order_id
  - app_settings key-value store with default referral rates
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "promo_codes",
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="manual"),
    )
    op.add_column("promo_codes", sa.Column("owner_user_id", sa.Integer(), nullable=True))
    op.add_column("promo_codes", sa.Column("cashback_percent", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_promo_codes_owner_user_id"), "promo_codes", ["owner_user_id"])
    op.create_foreign_key(
        "fk_promo_codes_owner_user_id_users",
        "promo_codes", "users",
        ["owner_user_id"], ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "orders",
        sa.Column("bonus_spent", sa.Numeric(precision=10, scale=2), nullable=False, server_default="0"),
    )
    op.add_column(
        "orders",
        sa.Column("referral_cashback_paid", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.add_column(
        "orders",
        sa.Column("bonus_refunded", sa.Boolean(), nullable=False, server_default="0"),
    )

    op.add_column(
        "users",
        sa.Column("referral_signup_bonus_paid", sa.Boolean(), nullable=False, server_default="0"),
    )

    op.add_column("tg_users", sa.Column("pending_ref_code", sa.String(length=32), nullable=True))

    op.add_column("bonus_transactions", sa.Column("order_id", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_bonus_transactions_order_id"), "bonus_transactions", ["order_id"])
    op.create_foreign_key(
        "fk_bonus_transactions_order_id_orders",
        "bonus_transactions", "orders",
        ["order_id"], ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("key"),
    )

    conn = op.get_bind()
    conn.execute(sa.text(
        "INSERT INTO app_settings (key, value) VALUES "
        "('referral.registration_bonus', '100'), "
        "('referral.purchase_cashback_percent', '5'), "
        "('referral.discount_percent', '5'), "
        "('referral.max_bonus_spend_percent', '100') "
        "ON CONFLICT (key) DO NOTHING"
    ))

    # Персональный промокод = referral_code пользователя.
    conn.execute(sa.text(
        """
        INSERT INTO promo_codes (code, discount_percent, is_active, used_count, kind, owner_user_id)
        SELECT u.referral_code, 5, true, 0, 'referral', u.id
        FROM users u
        WHERE u.referral_code IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM promo_codes p WHERE p.code = u.referral_code
          )
        """
    ))


def downgrade() -> None:
    op.drop_table("app_settings")
    op.drop_constraint("fk_bonus_transactions_order_id_orders", "bonus_transactions", type_="foreignkey")
    op.drop_index(op.f("ix_bonus_transactions_order_id"), table_name="bonus_transactions")
    op.drop_column("bonus_transactions", "order_id")
    op.drop_column("tg_users", "pending_ref_code")
    op.drop_column("users", "referral_signup_bonus_paid")
    op.drop_column("orders", "bonus_refunded")
    op.drop_column("orders", "referral_cashback_paid")
    op.drop_column("orders", "bonus_spent")
    op.drop_constraint("fk_promo_codes_owner_user_id_users", "promo_codes", type_="foreignkey")
    op.drop_index(op.f("ix_promo_codes_owner_user_id"), table_name="promo_codes")
    op.drop_column("promo_codes", "cashback_percent")
    op.drop_column("promo_codes", "owner_user_id")
    op.drop_column("promo_codes", "kind")
    # Реферальные строки, созданные апгрейдом, оставляем — удалять коды опасно.
