"""advisor_style_profile + advisor_turn_feedback

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-11 00:00:00.000000

Backs the "Fin learns how you talk" feature.

* ``advisor_style_profile`` — singleton row (id='household') holding a
  freeform ``style_notes`` blob that the reflection job overwrites with
  a 6-bullet style guide derived from recent messages + thumbed-up
  replies. Injected into the advisor's system prompt every turn.
* ``advisor_turn_feedback`` — 👍/👎 ratings the user attaches to
  individual assistant turns. Drives the reflection job's "what the
  user actually liked" sample.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "advisor_style_profile",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("style_notes", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "turn_count_at_last_update",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "advisor_turn_feedback",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "turn_id",
            sa.BigInteger(),
            sa.ForeignKey("conversation_turns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("turn_id", name="uq_advisor_turn_feedback_turn"),
    )


def downgrade() -> None:
    op.drop_table("advisor_turn_feedback")
    op.drop_table("advisor_style_profile")
