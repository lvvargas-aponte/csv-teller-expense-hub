"""fact_reflection_state — watermark for the proactive fact-extraction job

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-10 00:00:00.000000

Single-row table recording how many user turns had been persisted the
last time ``fact_reflection.extract_user_facts`` scanned the transcript.
Mirrors the ``advisor_style_profile`` watermark pattern.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fact_reflection_state",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column(
            "turn_count_at_last_scan",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("fact_reflection_state")
