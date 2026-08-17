"""sync bookkeeping — corrections feed, run log, per-row push watermark

Revision ID: 0018
Revises: 0017
Create Date: 2026-08-17 00:00:00.000000

``sync_row_state`` deliberately holds the push watermark and the peer's
disputes OUTSIDE the transaction document. Transactions live in
``json_stores`` behind PgStore, whose every write stamps
``json_stores.updated_at``. That column is the only "the user edited this
row" signal we have, and the corrections feed filters on it. Writing the
watermark back into the transaction would advance ``updated_at`` on every
push, permanently silencing the feed that makes "app wins" safe.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sync_corrections",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("period", sa.Text(), nullable=False),
        sa.Column("txn_id", sa.Text(), nullable=False),
        sa.Column("column_name", sa.Text(), nullable=False),
        sa.Column("sheet_value", sa.Text(), nullable=False, server_default=""),
        sa.Column("app_value", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "detected_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # Never auto-purged: a correction the user never saw is precisely the
        # failure this table exists to prevent.
        sa.Column("acknowledged_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index(
        "sync_corrections_open_idx",
        "sync_corrections",
        ["acknowledged_at", "detected_at"],
    )

    op.create_table(
        "sync_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("period", sa.Text(), nullable=False),
        sa.Column(
            "started_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("direction", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="running"),
        sa.Column("refusal_reason", sa.Text(), nullable=True),
        sa.Column("rows_pushed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_pulled", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_deleted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "direction IN ('push', 'pull', 'both')", name="sync_runs_direction_check"
        ),
        sa.CheckConstraint(
            "status IN ('running', 'ok', 'refused', 'error')",
            name="sync_runs_status_check",
        ),
    )
    op.create_index("sync_runs_period_idx", "sync_runs", ["period", "started_at"])

    op.create_table(
        "sync_row_state",
        sa.Column("txn_id", sa.Text(), primary_key=True),
        sa.Column("transaction_id", sa.Text(), nullable=False),
        sa.Column("period", sa.Text(), nullable=False),
        sa.Column("sheet_synced_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        # Written by the peer on the sheet, read back here. Never authored locally.
        sa.Column("dispute_flag", sa.Text(), nullable=True),
        sa.Column("dispute_by", sa.Text(), nullable=True),
        sa.Column("dispute_note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "dispute_flag IS NULL OR dispute_flag IN ('Y', 'N')",
            name="sync_row_state_dispute_check",
        ),
    )
    op.create_index("sync_row_state_period_idx", "sync_row_state", ["period"])


def downgrade() -> None:
    op.drop_index("sync_row_state_period_idx", table_name="sync_row_state")
    op.drop_table("sync_row_state")
    op.drop_index("sync_runs_period_idx", table_name="sync_runs")
    op.drop_table("sync_runs")
    op.drop_index("sync_corrections_open_idx", table_name="sync_corrections")
    op.drop_table("sync_corrections")
