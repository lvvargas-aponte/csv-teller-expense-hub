"""categories.parent_id — group categories so spending can roll up

Revision ID: 0033
Revises: 0032
Create Date: 2026-09-05 00:00:00.000000

Dining, Groceries and Coffee are three answers to "what was this for" and
one answer to "how much goes on food". Without a grouping the dashboard
can only offer the first, so a category list long enough to be useful is
also too granular to read.

One level only, enforced in ``categories_service``: a parent cannot itself
have a parent. Arbitrary depth would mean recursive rollups and a tree
widget, for a distinction ("Food > Groceries > Supermarkets") nobody
managing a household budget has asked for. The column is nullable and
everything ignores it by default, so the grouping is opt-in per view.

``ON DELETE SET NULL`` rather than CASCADE: deleting the "Food" parent
must not delete Groceries and every transaction's link to it.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0033"
down_revision: Union[str, None] = "0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "categories",
        sa.Column("parent_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "categories_parent_id_fkey",
        "categories",
        "categories",
        ["parent_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "categories_parent_not_self_check",
        "categories",
        "parent_id IS NULL OR parent_id <> id",
    )
    op.create_index("ix_categories_parent", "categories", ["parent_id"])


def downgrade() -> None:
    op.drop_index("ix_categories_parent", table_name="categories")
    op.drop_constraint("categories_parent_not_self_check", "categories")
    op.drop_constraint("categories_parent_id_fkey", "categories", type_="foreignkey")
    op.drop_column("categories", "parent_id")
