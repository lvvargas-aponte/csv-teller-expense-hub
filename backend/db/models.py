"""SQLAlchemy ORM models.

Managed by Alembic (see ``backend/alembic/versions/0001_initial.py``).
Phase 1 defines the schema — no routers read from these models yet.
"""
from datetime import date, datetime
from typing import Any, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    # simplefin | manual | csv_synth
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    institution: Mapped[Optional[str]] = mapped_column(String)
    name: Mapped[Optional[str]] = mapped_column(String)
    type: Mapped[Optional[str]] = mapped_column(String)
    subtype: Mapped[Optional[str]] = mapped_column(String)
    manual: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    token_enrollment_id: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Transaction(Base):
    __tablename__ = "transactions"

    transaction_id: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("accounts.id", ondelete="SET NULL")
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    post_date: Mapped[Optional[date]] = mapped_column(Date)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String)
    is_shared: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    who: Mapped[Optional[str]] = mapped_column(String)
    what: Mapped[Optional[str]] = mapped_column(Text)
    person_1_owes: Mapped[float] = mapped_column(Numeric(14, 2), server_default="0", nullable=False)
    person_2_owes: Mapped[float] = mapped_column(Numeric(14, 2), server_default="0", nullable=False)
    notes: Mapped[str] = mapped_column(Text, server_default="", nullable=False)
    reviewed: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    institution: Mapped[Optional[str]] = mapped_column(String)
    transaction_type: Mapped[Optional[str]] = mapped_column(String(20))
    account_type: Mapped[Optional[str]] = mapped_column(String(30))

    __table_args__ = (
        Index("ix_transactions_date", "date"),
        Index("ix_transactions_account_date", "account_id", "date"),
        Index("ix_transactions_is_shared", "is_shared"),
        Index("ix_transactions_reviewed", "reviewed"),
    )


class BalanceSnapshot(Base):
    __tablename__ = "balance_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(
        String, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    captured_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    available: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    ledger: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # simplefin | manual
    raw: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)

    __table_args__ = (
        Index("ix_balance_snapshots_account_captured", "account_id", "captured_at"),
    )


class Budget(Base):
    __tablename__ = "budgets"

    category: Mapped[str] = mapped_column(String, primary_key=True)
    monthly_limit: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    target_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    current_amount: Mapped[float] = mapped_column(
        Numeric(14, 2), server_default="0", nullable=False
    )
    target_date: Mapped[Optional[date]] = mapped_column(Date)
    kind: Mapped[Optional[str]] = mapped_column(String(30))
    priority: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    linked_account_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("accounts.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )


class AccountDetails(Base):
    __tablename__ = "account_details"

    account_id: Mapped[str] = mapped_column(
        String, ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True
    )
    apr: Mapped[Optional[float]] = mapped_column(Numeric(6, 3))
    credit_limit: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    minimum_payment: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    statement_day: Mapped[Optional[int]] = mapped_column(Integer)
    due_day: Mapped[Optional[int]] = mapped_column(Integer)
    # Length of credit history is the one score factor a bank feed cannot
    # infer — SimpleFIN reports balances, not an open date.
    opened_on: Mapped[Optional[date]] = mapped_column(Date)
    # Real assets (a home, a vehicle) have no feed: the value is whatever the
    # user last typed, so the app records when they typed it.
    valuation_updated_on: Mapped[Optional[date]] = mapped_column(Date)
    # Set on the ASSET row, pointing at the credit account it is secured
    # against. Deliberately not a foreign key — see migration 0024.
    secured_by_account_id: Mapped[Optional[str]] = mapped_column(Text)
    # taxable | traditional | roth | hsa | education | other. Null means the
    # user hasn't answered, which is not the same as "taxable".
    tax_treatment: Mapped[Optional[str]] = mapped_column(Text)
    notes: Mapped[Optional[str]] = mapped_column(Text)


class Holding(Base):
    __tablename__ = "holdings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(
        String, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, server_default="", nullable=False)
    # stock | etf | crypto | option | cash | other
    asset_type: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(28, 10), nullable=False)
    average_purchase_price: Mapped[Optional[float]] = mapped_column(Numeric(20, 8))
    last_price: Mapped[Optional[float]] = mapped_column(Numeric(20, 8))
    market_value: Mapped[Optional[float]] = mapped_column(Numeric(16, 2))
    currency: Mapped[str] = mapped_column(String(10), server_default="USD", nullable=False)
    synced_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_holdings_account_id", "account_id"),)


class HoldingCostOverride(Base):
    """A cost basis the user typed, kept out of ``holdings`` on purpose.

    Every sync rewrites that table wholesale, so anything stored on a holding
    row is destroyed the next time the scheduler runs. Joined at read time in
    ``analytics.summarize_holdings``.
    """

    __tablename__ = "holding_cost_overrides"

    account_id: Mapped[str] = mapped_column(
        String, ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True
    )
    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    average_purchase_price: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )


class Conversation(Base):
    __tablename__ = "conversations"

    conversation_id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[Optional[str]] = mapped_column(String)
    created: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ConversationTurn(Base):
    __tablename__ = "conversation_turns"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("conversations.conversation_id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    ts: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        Index(
            "ix_conversation_turns_conv_index",
            "conversation_id",
            "turn_index",
            unique=True,
        ),
    )


class ConversationTurnEmbedding(Base):
    __tablename__ = "conversation_turn_embeddings"

    turn_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("conversation_turns.id", ondelete="CASCADE"),
        primary_key=True,
    )
    model: Mapped[str] = mapped_column(String, nullable=False)
    dim: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(768), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )


class UserProfile(Base):
    __tablename__ = "user_profile"

    # Single-row table — id is always 'household' until multi-tenant lands.
    id: Mapped[str] = mapped_column(String, primary_key=True)
    risk_tolerance: Mapped[Optional[str]] = mapped_column(String(20))
    time_horizon_years: Mapped[Optional[int]] = mapped_column(Integer)
    dependents: Mapped[Optional[int]] = mapped_column(Integer)
    debt_strategy: Mapped[Optional[str]] = mapped_column(String(20))
    # Nullable on purpose: "not answered" has to stay distinct from a
    # deliberate 0, which is a meaningful answer for both of these.
    monthly_income: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    emergency_fund_months: Mapped[Optional[int]] = mapped_column(Integer)
    birth_year: Mapped[Optional[int]] = mapped_column(Integer)
    target_retirement_age: Mapped[Optional[int]] = mapped_column(Integer)
    annual_retirement_spend: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    expected_return_pct: Mapped[Optional[float]] = mapped_column(Numeric(6, 3))
    notes: Mapped[str] = mapped_column(Text, server_default="", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class CategoryRule(Base):
    __tablename__ = "category_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    # First match wins, so ordering is data the user authored — not a
    # display preference the client may re-sort.
    position: Mapped[int] = mapped_column(Integer, nullable=False, index=True)


class TransactionEmbedding(Base):
    __tablename__ = "transaction_embeddings"

    # Intentionally no FK to ``transactions`` — txns are authoritative in
    # ``json_stores`` (PgStore), not the structured table.
    transaction_id: Mapped[str] = mapped_column(String, primary_key=True)
    model: Mapped[str] = mapped_column(String, nullable=False)
    dim: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(768), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )


class AdvisorStyleProfile(Base):
    __tablename__ = "advisor_style_profile"

    # Single-row table — id is always 'household' until multi-tenant lands.
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    style_notes: Mapped[str] = mapped_column(Text, server_default="", nullable=False)
    turn_count_at_last_update: Mapped[int] = mapped_column(
        Integer, server_default="0", nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class AdvisorTurnFeedback(Base):
    __tablename__ = "advisor_turn_feedback"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    turn_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("conversation_turns.id", ondelete="CASCADE"),
        nullable=False,
    )
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    note: Mapped[str] = mapped_column(Text, server_default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("turn_id", name="uq_advisor_turn_feedback_turn"),
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    doc_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default="{}", nullable=False
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), server_default="pending", nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (
        Index("ix_documents_scope_category", "scope", "category"),
        Index("ix_documents_content_hash", "content_hash"),
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(768), nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    dim: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index(
            "ix_document_chunks_doc_chunk",
            "document_id",
            "chunk_index",
            unique=True,
        ),
    )
