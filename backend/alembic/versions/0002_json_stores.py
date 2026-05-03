"""json_stores compat table for PgStore dict-facade

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-20 00:00:00.000000

Phase 2 of the Postgres migration. Introduces a generic key-value
(store_name, key) → JSONB table that backs ``backend/store.py::PgStore``.
This keeps router call-sites dict-shaped while the structured tables
created in 0001 wait to receive data during Phases 4–6.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "json_stores",
        sa.Column("store_name", sa.Text(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("store_name", "key"),
    )
    op.create_index("ix_json_stores_store", "json_stores", ["store_name"])


def downgrade() -> None:
    op.drop_index("ix_json_stores_store", table_name="json_stores")
    op.drop_table("json_stores")
