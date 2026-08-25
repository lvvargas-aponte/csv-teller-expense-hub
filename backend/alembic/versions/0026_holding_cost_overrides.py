"""holding_cost_overrides — user-entered cost basis that outlives a sync

Revision ID: 0026
Revises: 0025
Create Date: 2026-08-24 00:00:00.000000

``holdings`` is a snapshot table: every SnapTrade sync deletes an account's
rows and re-inserts the current positions. A cost basis typed by the user and
stored there would be destroyed by the next scheduler run, silently. So the
override lives in its own table keyed by (account_id, symbol) and is joined at
read time in ``analytics.summarize_holdings``.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "holding_cost_overrides",
        sa.Column(
            "account_id",
            sa.String(),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("symbol", sa.String(), primary_key=True),
        sa.Column("average_purchase_price", sa.Numeric(20, 8), nullable=False),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("holding_cost_overrides")
