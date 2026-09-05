"""subscription_reviews.declared_cadence / declared_type — user overrides

Revision ID: 0029
Revises: 0028
Create Date: 2026-09-01 00:00:00.000000

The detector infers a billing cadence from the gaps between charges, which
is a guess and sometimes a bad one: two charges 45 days apart fit no band and
land on "irregular", and an annual renewal looks dormant for eleven months.
These columns let the user settle it.

* ``declared_cadence`` — the user's answer to "how often is this billed?".
  Overrides the inferred cadence everywhere: ``estimated_monthly_cost`` and
  the staleness math both read the declared value first.
* ``declared_type`` — the user's answer to "what kind of commitment is this?",
  overriding ``_classify_commitment`` when the category and description
  between them guessed wrong.

Both nullable: NULL means "no opinion, keep inferring".
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_VALID_CADENCES = (
    "weekly", "biweekly", "monthly", "bimonthly",
    "quarterly", "semiannual", "annual",
)
_VALID_TYPES = ("bill", "subscription", "recurring_spend")


def upgrade() -> None:
    op.add_column(
        "subscription_reviews",
        sa.Column("declared_cadence", sa.Text(), nullable=True),
    )
    op.add_column(
        "subscription_reviews",
        sa.Column("declared_type", sa.Text(), nullable=True),
    )
    op.create_check_constraint(
        "subscription_reviews_declared_cadence_check",
        "subscription_reviews",
        "declared_cadence IS NULL OR declared_cadence IN ({})".format(
            ", ".join(f"'{c}'" for c in _VALID_CADENCES)
        ),
    )
    op.create_check_constraint(
        "subscription_reviews_declared_type_check",
        "subscription_reviews",
        "declared_type IS NULL OR declared_type IN ({})".format(
            ", ".join(f"'{t}'" for t in _VALID_TYPES)
        ),
    )


def downgrade() -> None:
    op.drop_constraint(
        "subscription_reviews_declared_type_check", "subscription_reviews"
    )
    op.drop_constraint(
        "subscription_reviews_declared_cadence_check", "subscription_reviews"
    )
    op.drop_column("subscription_reviews", "declared_type")
    op.drop_column("subscription_reviews", "declared_cadence")
