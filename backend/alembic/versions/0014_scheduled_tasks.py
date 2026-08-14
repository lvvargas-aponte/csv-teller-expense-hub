"""scheduled_tasks — recurring data-sync jobs run by backend/scheduler.py

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-12 00:00:00.000000

One row per recurring job. ``task_type`` names a job in the scheduler's
registry (sync_transactions | refresh_balances | sync_investments);
``next_run_at`` drives the due check; ``last_result`` keeps the most
recent outcome for inspection via Fin's list_scheduled_tasks tool.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scheduled_tasks",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("task_type", sa.Text(), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("next_run_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("last_run_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_status", sa.Text(), nullable=True),
        sa.Column("last_result", postgresql.JSONB(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "task_type IN ('sync_transactions', 'refresh_balances', 'sync_investments')",
            name="scheduled_tasks_type_check",
        ),
        sa.CheckConstraint(
            "interval_days >= 1 AND interval_days <= 90",
            name="scheduled_tasks_interval_check",
        ),
    )
    op.create_index("scheduled_tasks_due_idx", "scheduled_tasks", ["enabled", "next_run_at"])


def downgrade() -> None:
    op.drop_index("scheduled_tasks_due_idx", table_name="scheduled_tasks")
    op.drop_table("scheduled_tasks")
