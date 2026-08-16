"""properties.landscaping_monthly — lawn / yard service as its own line

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-16 00:00:00.000000

Landscaping was previously folded into ``other_monthly_expense``, which made
it invisible in the pro forma breakdown. It is a recurring, contractually
fixed cost on most rentals, so it gets a named column alongside HOA and
utilities rather than sharing the catch-all.

Existing rows keep whatever they put in ``other_monthly_expense``; this
migration does not try to guess a split out of the catch-all.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "properties",
        sa.Column(
            "landscaping_monthly",
            sa.Numeric(14, 2),
            server_default="0",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("properties", "landscaping_monthly")
