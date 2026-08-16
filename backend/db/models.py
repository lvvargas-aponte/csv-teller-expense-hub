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


class Property(Base):
    """A real-estate holding. See ``alembic/versions/0011_properties_and_loans.py``.

    Carries a full operating-expense model so a rental has an honest pro
    forma before any transaction has been tagged to it. Actuals derived
    from tagged transactions are reported alongside, never blended in.
    """
    __tablename__ = "properties"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    address: Mapped[str] = mapped_column(Text, server_default="", nullable=False)
    property_type: Mapped[str] = mapped_column(
        String(20), server_default="single_family", nullable=False
    )
    # Gates whether this property contributes rent.
    status: Mapped[str] = mapped_column(String(20), server_default="rental", nullable=False)
    units: Mapped[int] = mapped_column(Integer, server_default="1", nullable=False)

    purchase_date: Mapped[Optional[date]] = mapped_column(Date)
    purchase_price: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    closing_costs: Mapped[float] = mapped_column(
        Numeric(14, 2), server_default="0", nullable=False
    )
    capital_improvements: Mapped[float] = mapped_column(
        Numeric(14, 2), server_default="0", nullable=False
    )

    # Denormalized latest valuation.
    current_value: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))

    monthly_rent: Mapped[float] = mapped_column(
        Numeric(14, 2), server_default="0", nullable=False
    )
    other_monthly_income: Mapped[float] = mapped_column(
        Numeric(14, 2), server_default="0", nullable=False
    )
    vacancy_rate_pct: Mapped[float] = mapped_column(
        Numeric(5, 2), server_default="5", nullable=False
    )

    property_tax_annual: Mapped[float] = mapped_column(
        Numeric(14, 2), server_default="0", nullable=False
    )
    insurance_annual: Mapped[float] = mapped_column(
        Numeric(14, 2), server_default="0", nullable=False
    )
    hoa_monthly: Mapped[float] = mapped_column(
        Numeric(14, 2), server_default="0", nullable=False
    )
    utilities_monthly: Mapped[float] = mapped_column(
        Numeric(14, 2), server_default="0", nullable=False
    )
    other_monthly_expense: Mapped[float] = mapped_column(
        Numeric(14, 2), server_default="0", nullable=False
    )
    mgmt_fee_pct: Mapped[float] = mapped_column(
        Numeric(5, 2), server_default="0", nullable=False
    )
    maintenance_pct_of_rent: Mapped[float] = mapped_column(
        Numeric(5, 2), server_default="5", nullable=False
    )
    capex_reserve_pct_of_rent: Mapped[float] = mapped_column(
        Numeric(5, 2), server_default="5", nullable=False
    )

    # NULL = fall back to the household retirement assumption.
    appreciation_pct: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    rent_growth_pct: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))

    # Auto-suggest rules only — matches never write property_id directly.
    rules: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default="[]", nullable=False
    )
    operating_account_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("accounts.id", ondelete="SET NULL")
    )
    notes: Mapped[str] = mapped_column(Text, server_default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (Index("ix_properties_status", "status"),)


class PropertyValuation(Base):
    """Point-in-time value for a property — the appreciation timeseries.

    Same shape as ``balance_snapshots``: history here, current value
    denormalized onto the parent for cheap reads.
    """
    __tablename__ = "property_valuations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    property_id: Mapped[str] = mapped_column(
        String, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False
    )
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    # manual | appraisal | avm | purchase
    source: Mapped[str] = mapped_column(String(20), server_default="manual", nullable=False)
    notes: Mapped[str] = mapped_column(Text, server_default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("property_id", "as_of", name="uq_property_valuation_as_of"),
        Index("ix_property_valuations_property_as_of", "property_id", "as_of"),
    )


class Loan(Base):
    """Amortizing debt, optionally secured by a property.

    ``escrow_monthly`` is intentionally separate from ``payment_amount``:
    escrowed taxes and insurance don't pay down principal, and property
    economics already counts them as operating expenses.
    """
    __tablename__ = "loans"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # mortgage | heloc | auto | student | personal | business | other
    loan_type: Mapped[str] = mapped_column(
        String(20), server_default="mortgage", nullable=False
    )
    property_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("properties.id", ondelete="SET NULL")
    )
    # When set, the live account balance wins over current_principal.
    account_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("accounts.id", ondelete="SET NULL")
    )
    lender: Mapped[str] = mapped_column(String, server_default="", nullable=False)
    # 1 = first, 2 = HELOC/second. Needed for CLTV.
    lien_position: Mapped[int] = mapped_column(
        SmallInteger, server_default="1", nullable=False
    )

    original_principal: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    current_principal: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    # Numeric(6,3) matches account_details.apr so rates round-trip identically.
    interest_rate_pct: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    rate_type: Mapped[str] = mapped_column(String(10), server_default="fixed", nullable=False)
    term_months: Mapped[int] = mapped_column(Integer, nullable=False)
    origination_date: Mapped[date] = mapped_column(Date, nullable=False)
    first_payment_date: Mapped[Optional[date]] = mapped_column(Date)
    payment_day: Mapped[Optional[int]] = mapped_column(SmallInteger)

    # P&I only; NULL derives it via amortization.pmt().
    payment_amount: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    escrow_monthly: Mapped[float] = mapped_column(
        Numeric(14, 2), server_default="0", nullable=False
    )
    pmi_monthly: Mapped[float] = mapped_column(
        Numeric(14, 2), server_default="0", nullable=False
    )
    extra_monthly: Mapped[float] = mapped_column(
        Numeric(14, 2), server_default="0", nullable=False
    )

    io_months: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    balloon_date: Mapped[Optional[date]] = mapped_column(Date)
    notes: Mapped[str] = mapped_column(Text, server_default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_loans_property_id", "property_id"),
        Index("ix_loans_account_id", "account_id"),
    )


class RentalTerm(Base):
    """Per-unit lease detail. Single-unit properties use
    ``properties.monthly_rent`` instead and need no row here."""
    __tablename__ = "rental_terms"

    property_id: Mapped[str] = mapped_column(
        String, ForeignKey("properties.id", ondelete="CASCADE"), primary_key=True
    )
    unit_label: Mapped[str] = mapped_column(
        String(40), server_default="", primary_key=True
    )
    monthly_rent: Mapped[float] = mapped_column(
        Numeric(14, 2), server_default="0", nullable=False
    )
    lease_start: Mapped[Optional[date]] = mapped_column(Date)
    lease_end: Mapped[Optional[date]] = mapped_column(Date)
    tenant_name: Mapped[str] = mapped_column(String, server_default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, server_default="", nullable=False)


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
