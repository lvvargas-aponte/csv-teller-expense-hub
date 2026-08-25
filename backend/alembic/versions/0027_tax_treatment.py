"""account_details — how an account's balance is taxed

Revision ID: 0027
Revises: 0026
Create Date: 2026-08-25 00:00:00.000000

A $200,000 traditional 401(k) and a $200,000 Roth IRA are not the same money:
one has an income-tax bill attached and the other does not. Nothing in the
feed says which is which — a Roth 401(k) and a traditional 401(k) report the
identical subtype — so the column holds the user's answer and the app infers
a default to show them.

Nullable, and no default: "unset" has to stay distinguishable from "taxable",
because discounting a balance the user never labelled would be a guess made
in their disfavour.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "account_details", sa.Column("tax_treatment", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("account_details", "tax_treatment")
