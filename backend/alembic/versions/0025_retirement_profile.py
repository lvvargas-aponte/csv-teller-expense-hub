"""user_profile — the inputs a retirement projection needs

Revision ID: 0025
Revises: 0024
Create Date: 2026-08-24 00:00:00.000000

``time_horizon_years`` is deliberately left alone: the advisor reads it and it
means something looser than "years until I stop working". A birth year plus a
target age pins the horizon without going stale the way a stored age would.

``annual_retirement_spend`` is a spending level rather than a pot, because a
pot is derived (spend / withdrawal rate) and a spending level is the number a
household can actually reason about. All four are nullable: the projection
names what it is missing rather than inventing an answer.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_profile", sa.Column("birth_year", sa.Integer(), nullable=True))
    op.add_column(
        "user_profile", sa.Column("target_retirement_age", sa.Integer(), nullable=True)
    )
    op.add_column(
        "user_profile",
        sa.Column("annual_retirement_spend", sa.Numeric(14, 2), nullable=True),
    )
    op.add_column(
        "user_profile", sa.Column("expected_return_pct", sa.Numeric(6, 3), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("user_profile", "expected_return_pct")
    op.drop_column("user_profile", "annual_retirement_spend")
    op.drop_column("user_profile", "target_retirement_age")
    op.drop_column("user_profile", "birth_year")
