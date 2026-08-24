"""category_rules — user-authored merchant→category matching

Revision ID: 0021
Revises: 0020
Create Date: 2026-08-22 00:00:00.000000

Categorization was Ollama-only. These rules run ahead of it: a rule is a
deterministic, offline answer the user wrote themselves, so it wins over
the model's guess and keeps working when Ollama is down.

``position`` carries the user-visible order — first match wins, so the
order is meaningful data, not a display preference.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "category_rules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("match", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_category_rules_position", "category_rules", ["position"]
    )


def downgrade() -> None:
    op.drop_index("ix_category_rules_position", table_name="category_rules")
    op.drop_table("category_rules")
