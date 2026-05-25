"""documents + document_chunks — RAG corpus for the advisor

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-05 00:00:00.000000

Adds two tables that back the document-ingestion RAG pipeline:

* ``documents``       — one row per uploaded file (PDF / TXT / MD).  Holds
                        the full ``raw_text`` so we can re-chunk later if
                        the chunking strategy changes, plus a content hash
                        for dedupe.
* ``document_chunks`` — one row per ~350-token chunk.  Embedding column
                        sized at ``Vector(768)`` to match the existing
                        ``nomic-embed-text`` pipeline used by
                        ``conversation_turn_embeddings`` and
                        ``transaction_embeddings``.

The HNSW index on ``document_chunks.embedding`` mirrors the index in 0003
so cosine retrieval has the same performance characteristics.

If we later need higher precision (financial-domain accuracy), the plan
is to add a parallel ``embedding_1024`` column rather than break the
existing 768-dim infra — see plan file safeguard #4.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column(
            "id",
            sa.BigInteger(),
            primary_key=True,
            autoincrement=True,
        ),
        # 'external' (reference material) | 'personal' (user's own docs).
        sa.Column("scope", sa.String(20), nullable=False),
        # Free-form within scope: 'tax' | 'credit' | 'investing' | 'literacy'
        # for external; 'tax_return' | 'statement' | 'paystub' | 'loan' for
        # personal.  Stored as plain text so future categories don't need a
        # migration.
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "uploaded_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # Free-form per-doc fields: tax_year, account_id, employer, etc.
        sa.Column(
            "doc_metadata",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("raw_text", sa.Text(), nullable=False),
        # sha256 over raw_text — dedupe + change detection on re-upload.
        sa.Column("content_hash", sa.String(64), nullable=False),
        # 'pending' (queued for embedding) | 'embedding' (in flight) |
        # 'ready' (chunks + embeddings present) | 'failed' (extractor or
        # Ollama errored — see error column).
        sa.Column(
            "status",
            sa.String(20),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("error", sa.Text()),
    )
    op.create_index(
        "ix_documents_scope_category", "documents", ["scope", "category"]
    )
    op.create_index(
        "ix_documents_content_hash", "documents", ["content_hash"]
    )

    op.create_table(
        "document_chunks",
        sa.Column(
            "id",
            sa.BigInteger(),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "document_id",
            sa.BigInteger(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(768), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("dim", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_document_chunks_doc_chunk",
        "document_chunks",
        ["document_id", "chunk_index"],
        unique=True,
    )
    op.execute(
        "CREATE INDEX ix_document_chunks_hnsw ON document_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_hnsw")
    op.drop_index("ix_document_chunks_doc_chunk", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_index("ix_documents_content_hash", table_name="documents")
    op.drop_index("ix_documents_scope_category", table_name="documents")
    op.drop_table("documents")
