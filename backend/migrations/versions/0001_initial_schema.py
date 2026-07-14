"""Initial schema baseline

Revision ID: 0001
Revises:
Create Date: 2026-07-14

This is the full schema baseline for a fresh install. Existing deployments
that were created via Base.metadata.create_all should stamp this revision
without running it:

    alembic stamp 0001
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # categories
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index(op.f("ix_categories_slug"), "categories", ["slug"])

    # products
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("old_price", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("stock_status", sa.Enum("in_stock", "out_of_stock", "preorder", name="stockstatus"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("is_featured", sa.Boolean(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index(op.f("ix_products_id"), "products", ["id"])
    op.create_index(op.f("ix_products_slug"), "products", ["slug"])

    # product_images
    op.create_table(
        "product_images",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_product_images_id"), "product_images", ["id"])

    # product_sizes
    op.create_table(
        "product_sizes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("size", sa.String(length=20), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_product_sizes_id"), "product_sizes", ["id"])

    # admin_users
    op.create_table(
        "admin_users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("login", sa.String(length=50), nullable=False),
        sa.Column("password_hash", sa.String(length=200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("login"),
    )
    op.create_index(op.f("ix_admin_users_id"), "admin_users", ["id"])
    op.create_index(op.f("ix_admin_users_login"), "admin_users", ["login"])

    # tg_users
    op.create_table(
        "tg_users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=True),
        sa.Column("first_name", sa.String(length=100), nullable=True),
        sa.Column("last_name", sa.String(length=100), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("last_seen", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id"),
    )
    op.create_index(op.f("ix_tg_users_id"), "tg_users", ["id"])
    op.create_index(op.f("ix_tg_users_chat_id"), "tg_users", ["chat_id"])

    # orders
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tg_user_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("customer_name", sa.String(length=150), nullable=False),
        sa.Column("customer_contact", sa.String(length=200), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("status", sa.Enum("new", "in_progress", "done", "cancelled", name="orderstatus"), nullable=False),
        sa.Column("order_type", sa.Enum("catalog", "design", name="ordertype"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["tg_user_chat_id"], ["tg_users.chat_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_orders_id"), "orders", ["id"])

    # order_items
    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("product_name", sa.String(length=200), nullable=False),
        sa.Column("product_price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("size", sa.String(length=20), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_order_items_id"), "order_items", ["id"])


def downgrade() -> None:
    op.drop_table("order_items")
    op.drop_table("orders")
    op.drop_index(op.f("ix_tg_users_chat_id"), table_name="tg_users")
    op.drop_index(op.f("ix_tg_users_id"), table_name="tg_users")
    op.drop_table("tg_users")
    op.drop_index(op.f("ix_admin_users_login"), table_name="admin_users")
    op.drop_index(op.f("ix_admin_users_id"), table_name="admin_users")
    op.drop_table("admin_users")
    op.drop_index(op.f("ix_product_sizes_id"), table_name="product_sizes")
    op.drop_table("product_sizes")
    op.drop_index(op.f("ix_product_images_id"), table_name="product_images")
    op.drop_table("product_images")
    op.drop_index(op.f("ix_products_slug"), table_name="products")
    op.drop_index(op.f("ix_products_id"), table_name="products")
    op.drop_table("products")
    op.drop_index(op.f("ix_categories_slug"), table_name="categories")
    op.drop_table("categories")
    # Drop enums last
    sa.Enum(name="ordertype").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="orderstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="stockstatus").drop(op.get_bind(), checkfirst=True)
