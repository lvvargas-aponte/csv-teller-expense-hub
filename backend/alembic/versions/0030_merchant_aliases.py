"""merchant_aliases — fold several merchant keys into one commitment

Revision ID: 0030
Revises: 0029
Create Date: 2026-09-02 00:00:00.000000

``_normalize_merchant`` collapses a description into a stable key, but it can
only work with what the bank writes. A merchant that renames itself
("Google FIBER" → "GFiber") or varies its own suffix
("PHR*AllergyPartnersPLLC 919-7875995" vs "… Raleigh") forks into two keys, so
one commitment reads as two — each with half the history, and neither with
enough of it to look recurring.

One row per alias: ``alias_key`` is absorbed into ``canonical_key``, and the
detector groups the alias's transactions under the canonical merchant. The
mapping is user-declared rather than inferred; fuzzy-matching merchant names
automatically merges things that merely look alike.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0030"
down_revision: Union[str, None] = "0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "merchant_aliases",
        sa.Column("alias_key", sa.Text(), primary_key=True),
        sa.Column("canonical_key", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # A merchant cannot be its own alias; that would drop it from the
        # grouping entirely.
        sa.CheckConstraint(
            "alias_key <> canonical_key", name="merchant_aliases_not_self_check"
        ),
    )
    op.create_index(
        "ix_merchant_aliases_canonical", "merchant_aliases", ["canonical_key"]
    )


def downgrade() -> None:
    op.drop_index("ix_merchant_aliases_canonical", table_name="merchant_aliases")
    op.drop_table("merchant_aliases")
