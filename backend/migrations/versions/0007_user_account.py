"""User accounts, addresses, favorites, bonuses, referral codes

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-30

Adds the personal-account layer for the storefront:
  - users: registered customers (email + password), verification token,
    referral code, bonus balance, notification prefs.
  - addresses: saved shipping addresses per user.
  - favorites: user wishlist (unique user/product).
  - bonus_transactions: audit log of bonus accruals/spends.
  - orders.user_id: link an order to the account that placed it (nullable,
    so anonymous orders keep working).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── users (self-referencing referred_by_id — add column + FK after table) ──
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=200), nullable=False),
        sa.Column("password_hash", sa.String(length=200), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=True),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("verification_token", sa.String(length=100), nullable=True),
        sa.Column("referred_by_id", sa.Integer(), nullable=True),
        sa.Column("referral_code", sa.String(length=32), nullable=False),
        sa.Column("bonus_balance", sa.Numeric(precision=10, scale=2), nullable=False, server_default="0"),
        sa.Column("notification_prefs", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("referral_code"),
    )
    op.create_index(op.f("ix_users_id"), "users", ["id"])
    op.create_index(op.f("ix_users_email"), "users", ["email"])
    op.create_index(op.f("ix_users_verification_token"), "users", ["verification_token"])
    op.create_index(op.f("ix_users_referral_code"), "users", ["referral_code"])
    # Self-reference (added after the table exists) + index.
    op.create_foreign_key(
        "fk_users_referred_by_id_users",
        "users", "users",
        ["referred_by_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_users_referred_by_id"), "users", ["referred_by_id"])

    # ── addresses ──────────────────────────────────────────────────────────────
    op.create_table(
        "addresses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=50), nullable=True),
        sa.Column("recipient", sa.String(length=150), nullable=True),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("street", sa.String(length=200), nullable=True),
        sa.Column("house", sa.String(length=20), nullable=True),
        sa.Column("apt", sa.String(length=20), nullable=True),
        sa.Column("zip", sa.String(length=20), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_addresses_id"), "addresses", ["id"])
    op.create_index(op.f("ix_addresses_user_id"), "addresses", ["user_id"])

    # ── favorites (unique user+product) ────────────────────────────────────────
    op.create_table(
        "favorites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "product_id", name="uq_favorite_user_product"),
    )
    op.create_index(op.f("ix_favorites_id"), "favorites", ["id"])
    op.create_index(op.f("ix_favorites_user_id"), "favorites", ["user_id"])
    op.create_index(op.f("ix_favorites_product_id"), "favorites", ["product_id"])

    # ── bonus_transactions ─────────────────────────────────────────────────────
    op.create_table(
        "bonus_transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("reason", sa.String(length=200), nullable=True),
        sa.Column("type", sa.Enum("accrual", "spend", name="bonustxtype"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_bonus_transactions_id"), "bonus_transactions", ["id"])
    op.create_index(op.f("ix_bonus_transactions_user_id"), "bonus_transactions", ["user_id"])

    # ── orders.user_id (nullable — anonymous orders stay valid) ─────────────────
    op.add_column("orders", sa.Column("user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_orders_user_id_users",
        "orders", "users",
        ["user_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_orders_user_id"), "orders", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_orders_user_id"), table_name="orders")
    op.drop_constraint("fk_orders_user_id_users", "orders", type_="foreignkey")
    op.drop_column("orders", "user_id")

    op.drop_index(op.f("ix_bonus_transactions_user_id"), table_name="bonus_transactions")
    op.drop_index(op.f("ix_bonus_transactions_id"), table_name="bonus_transactions")
    op.drop_table("bonus_transactions")
    sa.Enum(name="bonustxtype").drop(op.get_bind(), checkfirst=True)

    op.drop_index(op.f("ix_favorites_product_id"), table_name="favorites")
    op.drop_index(op.f("ix_favorites_user_id"), table_name="favorites")
    op.drop_index(op.f("ix_favorites_id"), table_name="favorites")
    op.drop_table("favorites")

    op.drop_index(op.f("ix_addresses_user_id"), table_name="addresses")
    op.drop_index(op.f("ix_addresses_id"), table_name="addresses")
    op.drop_table("addresses")

    op.drop_index(op.f("ix_users_referred_by_id"), table_name="users")
    op.drop_constraint("fk_users_referred_by_id_users", "users", type_="foreignkey")
    op.drop_index(op.f("ix_users_referral_code"), table_name="users")
    op.drop_index(op.f("ix_users_verification_token"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_index(op.f("ix_users_id"), table_name="users")
    op.drop_table("users")
