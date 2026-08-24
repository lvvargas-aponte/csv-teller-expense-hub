"""user_profile — monthly take-home and emergency-fund target

Revision ID: 0020
Revises: 0019
Create Date: 2026-08-22 00:00:00.000000

The Profile & Settings page surfaces two answers the advisor was guessing
at: what actually lands in the account each month, and how many months of
expenses the household wants held in cash. Both nullable — the profile is
entirely optional and an unset field must stay distinguishable from a
deliberate zero.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_profile",
        sa.Column("monthly_income", sa.Numeric(14, 2), nullable=True),
    )
    op.add_column(
        "user_profile",
        sa.Column("emergency_fund_months", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_profile", "emergency_fund_months")
    op.drop_column("user_profile", "monthly_income")
