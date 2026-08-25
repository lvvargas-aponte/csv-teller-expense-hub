"""user_profile — the marginal rate, and whether to show the after-tax view

Revision ID: 0028
Revises: 0027
Create Date: 2026-08-25 00:00:00.000000

The rate is asked for, never derived. Inferring a bracket from income needs
filing status, deductions and state rules the app does not hold, and a wrong
bracket would move net worth by tens of thousands of dollars silently. Null
therefore means "not answered" and the view reports itself unavailable.

``show_after_tax_net_worth`` is opt-in and defaults to false: the discounted
figure clarifies things for some households and demoralises others, and it is
not the app's call which. Off, the secondary line is not rendered at all.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_profile",
        sa.Column("marginal_tax_rate_pct", sa.Numeric(5, 2), nullable=True),
    )
    op.add_column(
        "user_profile",
        sa.Column(
            "show_after_tax_net_worth",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("user_profile", "show_after_tax_net_worth")
    op.drop_column("user_profile", "marginal_tax_rate_pct")
