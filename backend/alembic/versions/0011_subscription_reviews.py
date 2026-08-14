"""subscription_reviews — user decisions on detected recurring charges

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-03 00:00:00.000000

Backs the Subscriptions review page. One row per normalized merchant key
from ``analytics.detect_recurring_charges``:

* ``decision`` — keep (intentional), cancel (user plans to drop it), or
  ignore (not actually a subscription; hide from review prompts).
* ``reviewed_amount`` — the latest charge amount at review time; a later
  price change beyond the re-prompt threshold resurfaces the merchant.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_VALID_DECISIONS = ("keep", "cancel", "ignore")


def upgrade() -> None:
    op.create_table(
        "subscription_reviews",
        sa.Column("merchant_key", sa.Text(), primary_key=True),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("reviewed_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column(
            "reviewed_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "decision IN ({})".format(", ".join(f"'{d}'" for d in _VALID_DECISIONS)),
            name="subscription_reviews_decision_check",
        ),
    )


def downgrade() -> None:
    op.drop_table("subscription_reviews")