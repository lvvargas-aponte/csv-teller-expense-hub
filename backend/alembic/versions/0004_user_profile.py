"""user_profile — single-row household preferences

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-28 00:00:00.000000

PR6 of the data-gap initiative.  Stores the household-wide preferences
the advisor needs to tailor recommendations: risk tolerance, time
horizon, dependents, and debt strategy.  Modeled as a single-row table
(``id`` always ``'household'``) — this is a one-household app; relax
later if multi-tenant becomes a thing.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_profile",
        sa.Column("id", sa.String(), primary_key=True, server_default="household"),
        sa.Column("risk_tolerance", sa.String(20)),
        sa.Column("time_horizon_years", sa.Integer()),
        sa.Column("dependents", sa.Integer()),
        sa.Column("debt_strategy", sa.String(20)),
        sa.Column("notes", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("user_profile")
