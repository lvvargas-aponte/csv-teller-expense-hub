"""account_details — when the user last valued a real asset

Revision ID: 0023
Revises: 0022
Create Date: 2026-08-24 00:00:00.000000

A home or vehicle has no feed behind it: its value is whatever the user last
typed. Nothing may estimate it — no appreciation curve, no depreciation
table, no valuation API — so the only honest thing the app can do is record
when the number was set and tell the user when it is getting old.

Nullable — an asset added before this column existed must stay
distinguishable from one valued today.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "account_details",
        sa.Column("valuation_updated_on", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("account_details", "valuation_updated_on")
