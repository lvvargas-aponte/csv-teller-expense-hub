"""account_details — the loan an asset is secured against

Revision ID: 0024
Revises: 0023
Create Date: 2026-08-24 00:00:00.000000

A house worth $450,000 with a $310,000 mortgage is $140,000 of equity, and
equity is the figure a household actually reasons about. Both numbers already
existed; nothing joined them.

The column is set on the ASSET row and points at the credit account. No
foreign key: the loan may be a SimpleFIN account that later disconnects, and
a cascade would silently rewrite the link to "no debt" — which would present
the entire value of the house as equity. A dangling id is read as unknown
instead, which is the honest answer.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "account_details",
        sa.Column("secured_by_account_id", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("account_details", "secured_by_account_id")
