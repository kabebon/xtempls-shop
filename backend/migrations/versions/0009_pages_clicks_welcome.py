"""CMS pages, referral click tracking, welcome bonus

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-01

Additive only.
  - site_pages: editable storefront texts (offer, privacy, loyalty)
  - referral_clicks: visits via ?ref=CODE
  - users.welcome_bonus_paid: one-time bonus for any registration
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("welcome_bonus_paid", sa.Boolean(), nullable=False, server_default="0"),
    )

    op.create_table(
        "site_pages",
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("key"),
    )

    op.create_table(
        "referral_clicks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("referral_code", sa.String(length=32), nullable=False),
        sa.Column("landing_path", sa.String(length=300), nullable=True),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_referral_clicks_id"), "referral_clicks", ["id"])
    op.create_index(op.f("ix_referral_clicks_referral_code"), "referral_clicks", ["referral_code"])
    op.create_index(op.f("ix_referral_clicks_ip_hash"), "referral_clicks", ["ip_hash"])
    op.create_index(op.f("ix_referral_clicks_created_at"), "referral_clicks", ["created_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_referral_clicks_created_at"), table_name="referral_clicks")
    op.drop_index(op.f("ix_referral_clicks_ip_hash"), table_name="referral_clicks")
    op.drop_index(op.f("ix_referral_clicks_referral_code"), table_name="referral_clicks")
    op.drop_index(op.f("ix_referral_clicks_id"), table_name="referral_clicks")
    op.drop_table("referral_clicks")
    op.drop_table("site_pages")
    op.drop_column("users", "welcome_bonus_paid")
