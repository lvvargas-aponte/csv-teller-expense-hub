"""account_details — when the account was opened

Revision ID: 0022
Revises: 0021
Create Date: 2026-08-24 00:00:00.000000

Length of credit history is 15% of a FICO score and the one factor a bank
feed cannot infer: SimpleFIN reports balances, not an open date. The user
enters it per card, and the Credit Factors panel counts how many accounts
still lack it rather than quietly averaging over the ones that have it.

Nullable — an unset date must stay distinguishable from a recently opened
account.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "account_details",
        sa.Column("opened_on", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("account_details", "opened_on")
