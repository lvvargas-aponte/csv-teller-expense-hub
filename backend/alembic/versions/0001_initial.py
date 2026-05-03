"""initial schema — pgvector + all 9 tables

Revision ID: 0001
Revises:
Create Date: 2026-04-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "accounts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("institution", sa.String()),
        sa.Column("name", sa.String()),
        sa.Column("type", sa.String()),
        sa.Column("subtype", sa.String()),
        sa.Column("manual", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("token_enrollment_id", sa.String()),
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
    )

    op.create_table(
        "transactions",
        sa.Column("transaction_id", sa.String(), primary_key=True),
        sa.Column(
            "account_id",
            sa.String(),
            sa.ForeignKey("accounts.id", ondelete="SET NULL"),
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("post_date", sa.Date()),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("category", sa.String()),
        sa.Column("is_shared", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("who", sa.String()),
        sa.Column("what", sa.Text()),
        sa.Column("person_1_owes", sa.Numeric(14, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("person_2_owes", sa.Numeric(14, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("notes", sa.Text(), server_default="", nullable=False),
        sa.Column("reviewed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("institution", sa.String()),
        sa.Column("transaction_type", sa.String(20)),
        sa.Column("account_type", sa.String(30)),
    )
    op.create_index("ix_transactions_date", "transactions", ["date"])
    op.create_index("ix_transactions_account_date", "transactions", ["account_id", "date"])
    op.create_index("ix_transactions_is_shared", "transactions", ["is_shared"])
    op.create_index("ix_transactions_reviewed", "transactions", ["reviewed"])

    op.create_table(
        "balance_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "account_id",
            sa.String(),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "captured_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("available", sa.Numeric(14, 2)),
        sa.Column("ledger", sa.Numeric(14, 2)),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("raw", postgresql.JSONB()),
    )
    op.create_index(
        "ix_balance_snapshots_account_captured",
        "balance_snapshots",
        ["account_id", "captured_at"],
    )

    op.create_table(
        "budgets",
        sa.Column("category", sa.String(), primary_key=True),
        sa.Column("monthly_limit", sa.Numeric(14, 2), nullable=False),
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
    )

    op.create_table(
        "goals",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("target_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("current_amount", sa.Numeric(14, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("target_date", sa.Date()),
        sa.Column("kind", sa.String(30)),
        sa.Column("priority", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "linked_account_id",
            sa.String(),
            sa.ForeignKey("accounts.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "account_details",
        sa.Column(
            "account_id",
            sa.String(),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("apr", sa.Numeric(6, 3)),
        sa.Column("credit_limit", sa.Numeric(14, 2)),
        sa.Column("minimum_payment", sa.Numeric(14, 2)),
        sa.Column("statement_day", sa.Integer()),
        sa.Column("due_day", sa.Integer()),
        sa.Column("notes", sa.Text()),
    )

    op.create_table(
        "conversations",
        sa.Column("conversation_id", sa.String(), primary_key=True),
        sa.Column("title", sa.String()),
        sa.Column(
            "created",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "conversation_turns",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "conversation_id",
            sa.String(),
            sa.ForeignKey("conversations.conversation_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "ts",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("turn_index", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_conversation_turns_conv_index",
        "conversation_turns",
        ["conversation_id", "turn_index"],
        unique=True,
    )

    op.create_table(
        "conversation_turn_embeddings",
        sa.Column(
            "turn_id",
            sa.BigInteger(),
            sa.ForeignKey("conversation_turns.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("dim", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(768), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.execute(
        "CREATE INDEX ix_embeddings_hnsw ON conversation_turn_embeddings "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_embeddings_hnsw")
    op.drop_table("conversation_turn_embeddings")
    op.drop_index("ix_conversation_turns_conv_index", table_name="conversation_turns")
    op.drop_table("conversation_turns")
    op.drop_table("conversations")
    op.drop_table("account_details")
    op.drop_table("goals")
    op.drop_table("budgets")
    op.drop_index("ix_balance_snapshots_account_captured", table_name="balance_snapshots")
    op.drop_table("balance_snapshots")
    op.drop_index("ix_transactions_reviewed", table_name="transactions")
    op.drop_index("ix_transactions_is_shared", table_name="transactions")
    op.drop_index("ix_transactions_account_date", table_name="transactions")
    op.drop_index("ix_transactions_date", table_name="transactions")
    op.drop_table("transactions")
    op.drop_table("accounts")
