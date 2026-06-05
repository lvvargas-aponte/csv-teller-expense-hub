"""conversation_turns.trajectory JSONB

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-28 00:00:00.000000

Adds a nullable JSONB column on ``conversation_turns`` to persist the
agent-harness trajectory (tool calls, results, termination reason) for
each assistant reply. Used for offline trajectory eval and future
trajectory visualization in the UI. Null when the legacy non-agentic
chat path produced the turn.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversation_turns",
        sa.Column("trajectory", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversation_turns", "trajectory")
