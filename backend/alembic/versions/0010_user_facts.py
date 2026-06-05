"""user_facts + user_fact_embeddings — structured Fin memory

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-30 00:00:00.000000

Backs the "Things Fin remembers about you" feature.

* ``user_facts`` — one row per fact Fin has been told (or proposes) about
  the user: preferences, constraints, goals, life events, behavioral
  patterns. ``status`` gates curation (proposed facts stay quiet until
  the user confirms them in the UI). ``sensitive`` masks the fact in
  the UI list (still injected into the local-LLM prompt verbatim).
* ``user_fact_embeddings`` — 768-dim pgvector mirror so the
  ``recall_about_user`` agent tool can do semantic retrieval against
  confirmed facts.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_VALID_CATEGORIES = ("preference", "constraint", "goal", "life_event", "pattern")
_VALID_STATUSES = ("proposed", "confirmed", "rejected")


def upgrade() -> None:
    op.create_table(
        "user_facts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("fact", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("ARRAY[]::text[]"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Text(),
            server_default=sa.text("'proposed'"),
            nullable=False,
        ),
        sa.Column(
            "sensitive",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "confidence",
            sa.Float(),
            server_default=sa.text("0.5"),
            nullable=False,
        ),
        sa.Column(
            "source_turn_id",
            sa.BigInteger(),
            sa.ForeignKey("conversation_turns.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "category IN ({})".format(", ".join(f"'{c}'" for c in _VALID_CATEGORIES)),
            name="user_facts_category_check",
        ),
        sa.CheckConstraint(
            "status IN ({})".format(", ".join(f"'{s}'" for s in _VALID_STATUSES)),
            name="user_facts_status_check",
        ),
    )
    op.create_index("user_facts_status_idx", "user_facts", ["status"])
    op.create_index("user_facts_category_idx", "user_facts", ["category"])

    op.create_table(
        "user_fact_embeddings",
        sa.Column(
            "fact_id",
            sa.BigInteger(),
            sa.ForeignKey("user_facts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("embedding", Vector(768), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("dim", sa.Integer(), server_default=sa.text("768"), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.execute(
        "CREATE INDEX ix_user_fact_embeddings_hnsw ON user_fact_embeddings "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_user_fact_embeddings_hnsw")
    op.drop_table("user_fact_embeddings")
    op.drop_index("user_facts_category_idx", table_name="user_facts")
    op.drop_index("user_facts_status_idx", table_name="user_facts")
    op.drop_table("user_facts")
