"""digests — stored weekly digest snapshots

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-04 00:00:00.000000

One row per generated weekly digest. The payload is the fully-composed
JSON the frontend renders (alerts, week-over-week spending, upcoming
bills, subscription flags, optional LLM narrative); ``read_at`` drives
the unread badge.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "digests",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "generated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("read_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("digests_generated_at_idx", "digests", ["generated_at"])


def downgrade() -> None:
    op.drop_index("digests_generated_at_idx", table_name="digests")
    op.drop_table("digests")