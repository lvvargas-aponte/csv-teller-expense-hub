"""holdings — per-position brokerage/crypto investment detail

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-22 00:00:00.000000

Backs the Investments feature.  A ``holdings`` row is one position (a stock,
ETF, or crypto coin) inside an investment ``accounts`` row.  SnapTrade is the
source: each sync fully replaces an account's holdings with the current
positions, so this table is a *current snapshot*, not a timeseries.

Account-level value-over-time history is intentionally NOT stored here — the
existing ``balance_snapshots`` table already captures each account's total
value per sync, which is what the net-worth timeseries charts from.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "holdings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "account_id",
            sa.String(),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        # 'stock' | 'etf' | 'crypto' | 'option' | 'cash' | 'other'
        sa.Column("asset_type", sa.String(20), nullable=False),
        # Wide precision so fractional crypto units survive intact.
        sa.Column("quantity", sa.Numeric(28, 10), nullable=False),
        sa.Column("average_purchase_price", sa.Numeric(20, 8)),
        sa.Column("last_price", sa.Numeric(20, 8)),
        sa.Column("market_value", sa.Numeric(16, 2)),
        sa.Column("currency", sa.String(10), server_default="USD", nullable=False),
        sa.Column(
            "synced_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_holdings_account_id", "holdings", ["account_id"])


def downgrade() -> None:
    op.drop_index("ix_holdings_account_id", table_name="holdings")
    op.drop_table("holdings")
