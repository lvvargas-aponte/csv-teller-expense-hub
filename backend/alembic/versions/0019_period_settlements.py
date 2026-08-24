"""period_settlements — each instance's standing position on a month

Revision ID: 0019
Revises: 0018
Create Date: 2026-08-22 00:00:00.000000

One row per (period, instance), mirroring the ``period`` records in the hidden
``_sync`` worksheet whose columns ``sheet_sync/sync_sheet.py`` reserved
since Part II. Mine is authored here and pushed; the peer's is pulled and never
written locally — the same ownership rule ``peer_shared_transactions`` follows.

Settlement is deliberately ADVISORY: either instance may mark a month paid
without the other agreeing, so ``pif_at`` lives on each side's own row rather
than on a single shared record. A month counts as settled when EITHER row
carries a ``pif_at``, and the UI names who said so.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "period_settlements",
        sa.Column("period", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), primary_key=True),
        # "My rows for this month are complete." Advisory on both sides.
        sa.Column("ready_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("closed_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        # The net as THIS instance computed it when it declared ready. Kept per
        # instance precisely so a disagreement is visible instead of averaged.
        sa.Column("net_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("debtor_user_id", sa.Text(), nullable=True),
        sa.Column("pif_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("pif_note", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "period_settlements_period_idx", "period_settlements", ["period"]
    )


def downgrade() -> None:
    op.drop_index("period_settlements_period_idx", table_name="period_settlements")
    op.drop_table("period_settlements")
