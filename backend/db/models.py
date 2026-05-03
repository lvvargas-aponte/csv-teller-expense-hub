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
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    # teller | manual | csv_synth
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
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # teller | manual
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
    notes: Mapped[Optional[str]] = mapped_column(Text)


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
    notes: Mapped[str] = mapped_column(Text, server_default="", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


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
