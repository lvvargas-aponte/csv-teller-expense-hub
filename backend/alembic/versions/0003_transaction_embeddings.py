"""transaction_embeddings — pgvector index over individual transactions

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-27 00:00:00.000000

Adds a per-transaction embedding row so the advisor can semantically recall
specific historical charges (e.g. "what was that weird $300 charge from
October?", "find any subscription-like charges I might want to cancel").
Mirrors the structure of ``conversation_turn_embeddings`` introduced in 0001.

``content_hash`` is sha1 of the embedded text — the backfill job re-embeds
when the hash changes (description / category / notes edited), so the
index stays consistent without a separate dirty-flag column.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NOTE: ``transaction_id`` deliberately has NO foreign key to the
    # structured ``transactions`` table. Transactions are still authoritative
    # in ``json_stores`` (PgStore) — the structured ``transactions`` table is
    # currently empty in production. Stale embedding rows are tolerated; the
    # retrieval path filters by current stored_transactions membership.
    op.create_table(
        "transaction_embeddings",
        sa.Column("transaction_id", sa.String(), primary_key=True),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("dim", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(768), nullable=False),
        sa.Column("content_hash", sa.String(40), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.execute(
        "CREATE INDEX ix_transaction_embeddings_hnsw ON transaction_embeddings "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_transaction_embeddings_hnsw")
    op.drop_table("transaction_embeddings")
