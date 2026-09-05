"""category_rules — merchant-keyed rules, per-row identity, enable/disable

Revision ID: 0031
Revises: 0030
Create Date: 2026-09-05 00:00:00.000000

A rule could only be born in the settings form, as a substring the user
typed against the raw description. That is the weakest key available:
``SQ *COFFEE 4471 SEATTLE`` and ``SQ *COFFEE 8812 PORTLAND`` are one
merchant, and matching them by substring means guessing which fragment is
stable. ``merchant_key.canonical`` already answers that question for
recurring detection, so rules key on it too.

``kind`` says which: ``merchant`` compares the whole normalized key,
``contains`` keeps the old case-insensitive substring test. Existing rows
migrate to ``contains`` — they were written as substrings and still mean
what they meant.

The other columns exist so a rule can be a thing rather than a line in a
list the client replaces wholesale: ``enabled`` turns one off without
losing what it says, and ``created_at`` / ``last_matched_at`` let the UI
show whether a rule is actually earning its place.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0031"
down_revision: Union[str, None] = "0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("category_rules", "match", new_column_name="pattern")
    op.add_column(
        "category_rules",
        sa.Column(
            "kind", sa.Text(), nullable=False, server_default="contains"
        ),
    )
    op.add_column(
        "category_rules",
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default="true"
        ),
    )
    op.add_column(
        "category_rules",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.add_column(
        "category_rules",
        sa.Column("last_matched_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "category_rules_kind_check",
        "category_rules",
        "kind IN ('merchant', 'contains')",
    )
    # A merchant key is exact, so two enabled rules on the same key are a
    # contradiction rather than an ordering question. Substring rules stay
    # unconstrained: overlapping patterns are legitimate and `position`
    # decides between them.
    op.execute(
        "CREATE UNIQUE INDEX ix_category_rules_merchant_pattern "
        "ON category_rules (pattern) WHERE kind = 'merchant'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_category_rules_merchant_pattern")
    op.drop_constraint("category_rules_kind_check", "category_rules")
    op.drop_column("category_rules", "last_matched_at")
    op.drop_column("category_rules", "created_at")
    op.drop_column("category_rules", "enabled")
    op.drop_column("category_rules", "kind")
    op.alter_column("category_rules", "pattern", new_column_name="match")
