"""peer_shared_transactions — the other party's shared rows, imported from the sheet

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-16 00:00:00.000000

Deliberately separate from local transactions. If these rows shared a table
with our own, every existing analytics, budget, dashboard and advisor query
would silently include the peer's spending. Keeping them apart means those
queries stay correct with no changes, and settlement opts in explicitly.

``txn_id`` is the namespaced sheet key ``{owner_user_id}:{transaction_id}``.
The dispute columns are ours to write — we are not the owner of these rows,
and the non-owner owns the dispute fields.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "peer_shared_transactions",
        sa.Column("txn_id", sa.Text(), primary_key=True),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("who", sa.Text(), nullable=True),
        sa.Column("person_1_owes", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("person_2_owes", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("reviewed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("payer_user_id", postgresql.UUID(as_uuid=False), nullable=True),
        # Provenance label for the user ("carried from 2026-03").
        sa.Column("carried_from_period", sa.Text(), nullable=True),
        # The month whose settlement actually includes this row. NULL means the
        # row settles in the month of its own date. These two differ only for
        # carried rows, and collapsing them would settle a carried row back
        # into the closed month it came from.
        sa.Column("settles_in_period", sa.Text(), nullable=True),
        sa.Column("dispute_flag", sa.Text(), nullable=True),
        sa.Column("dispute_by", sa.Text(), nullable=True),
        sa.Column("dispute_note", sa.Text(), nullable=True),
        sa.Column(
            "imported_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "dispute_flag IS NULL OR dispute_flag IN ('Y', 'N')",
            name="peer_shared_transactions_dispute_check",
        ),
    )
    op.create_index(
        "peer_shared_transactions_date_idx", "peer_shared_transactions", ["date"]
    )
    op.create_index(
        "peer_shared_transactions_settles_idx",
        "peer_shared_transactions",
        ["settles_in_period"],
    )


def downgrade() -> None:
    op.drop_index("peer_shared_transactions_settles_idx", table_name="peer_shared_transactions")
    op.drop_index("peer_shared_transactions_date_idx", table_name="peer_shared_transactions")
    op.drop_table("peer_shared_transactions")
