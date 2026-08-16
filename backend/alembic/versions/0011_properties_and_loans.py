"""properties, property_valuations, loans, rental_terms — real-estate domain

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-15 00:00:00.000000

Backs the Properties feature and, through it, the retirement projection —
the household's plan is to hold rentals, let tenants amortize the
mortgages, and retire onto the resulting net cash flow, so property equity
and principal paydown are first-class rather than a side ledger.

Typed tables rather than the ``json_stores`` JSONB facade that budgets and
goals use. These entities are genuinely relational (a loan encumbers a
property, valuations form a timeseries per property), ``json_stores`` has
no foreign keys or per-field indexes so every read means fetching the whole
store and filtering in Python, and money here is compared against real
servicer statements. This follows the newer ``holdings`` / ``user_facts``
precedent, reached through a sync repo in ``db/properties_repo.py``.

Note on money columns: ``Numeric(14, 2)`` matches the existing convention;
rates use ``Numeric(6, 3)`` to match ``account_details.apr`` exactly so a
credit-card APR and a mortgage rate round-trip identically.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "properties",
        # 'prop_<hex12>', matching the 'goal_<hex12>' convention in routers/goals.py
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("address", sa.Text(), server_default="", nullable=False),
        # 'single_family' | 'multi_family' | 'condo' | 'townhouse' | 'land' | 'commercial'
        sa.Column("property_type", sa.String(20), server_default="single_family", nullable=False),
        # Gates whether the property contributes rent to cash flow and retirement:
        # 'rental' | 'primary_residence' | 'vacation' | 'held_for_sale' | 'under_renovation'
        sa.Column("status", sa.String(20), server_default="rental", nullable=False),
        sa.Column("units", sa.Integer(), server_default="1", nullable=False),

        # Acquisition — drives cash-on-cash. Nullable: a property added years
        # after purchase may not have these to hand, and cash-on-cash returns
        # None rather than a fabricated number when they're missing.
        sa.Column("purchase_date", sa.Date()),
        sa.Column("purchase_price", sa.Numeric(14, 2)),
        sa.Column("closing_costs", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("capital_improvements", sa.Numeric(14, 2), server_default="0", nullable=False),

        # Denormalized cache of the latest property_valuations row, so the
        # common "what is this worth now" read is a single column.
        sa.Column("current_value", sa.Numeric(14, 2)),

        # Scheduled rent per the lease. Actuals come from tagged transactions;
        # the two are reported side by side and never blended.
        sa.Column("monthly_rent", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("other_monthly_income", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("vacancy_rate_pct", sa.Numeric(5, 2), server_default="5", nullable=False),

        # Operating expenses. Present in full so a rental has an honest pro
        # forma on day one, before any transaction has been tagged to it.
        sa.Column("property_tax_annual", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("insurance_annual", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("hoa_monthly", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("utilities_monthly", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("other_monthly_expense", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("mgmt_fee_pct", sa.Numeric(5, 2), server_default="0", nullable=False),
        sa.Column("maintenance_pct_of_rent", sa.Numeric(5, 2), server_default="5", nullable=False),
        sa.Column("capex_reserve_pct_of_rent", sa.Numeric(5, 2), server_default="5", nullable=False),

        # Per-property overrides of the global retirement assumptions. NULL
        # means "use the household default".
        sa.Column("appreciation_pct", sa.Numeric(5, 2)),
        sa.Column("rent_growth_pct", sa.Numeric(5, 2)),

        # Transaction auto-SUGGEST rules; never auto-applied. Shape:
        # [{"match": "merchant_key"|"description_contains"|"account_id",
        #   "value": "...", "direction": "inflow"|"outflow"}]
        sa.Column("rules", postgresql.JSONB(), server_default="[]", nullable=False),

        # Optional: transactions on this account are suggested for this property.
        sa.Column(
            "operating_account_id",
            sa.String(),
            sa.ForeignKey("accounts.id", ondelete="SET NULL"),
        ),
        sa.Column("notes", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "created_at", postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_properties_status", "properties", ["status"])

    op.create_table(
        "property_valuations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "property_id",
            sa.String(),
            sa.ForeignKey("properties.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("value", sa.Numeric(14, 2), nullable=False),
        # 'manual' | 'appraisal' | 'avm' | 'purchase'
        sa.Column("source", sa.String(20), server_default="manual", nullable=False),
        sa.Column("notes", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "created_at", postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        # One valuation per property per day — re-valuing the same day
        # overwrites rather than accumulating near-duplicates.
        sa.UniqueConstraint("property_id", "as_of", name="uq_property_valuation_as_of"),
    )
    op.create_index(
        "ix_property_valuations_property_as_of",
        "property_valuations",
        ["property_id", "as_of"],
    )

    op.create_table(
        "loans",
        sa.Column("id", sa.String(), primary_key=True),   # 'loan_<hex12>'
        sa.Column("name", sa.String(), nullable=False),
        # 'mortgage' | 'heloc' | 'auto' | 'student' | 'personal' | 'business' | 'other'
        sa.Column("loan_type", sa.String(20), server_default="mortgage", nullable=False),
        # A mortgage encumbers a property; an auto loan encumbers nothing.
        # SET NULL so deleting a property doesn't silently delete its debt.
        sa.Column(
            "property_id",
            sa.String(),
            sa.ForeignKey("properties.id", ondelete="SET NULL"),
        ),
        # Links a synced account so the balance stays live. When set, it wins
        # over current_principal — see properties.resolve_loan_balance().
        sa.Column(
            "account_id",
            sa.String(),
            sa.ForeignKey("accounts.id", ondelete="SET NULL"),
        ),
        sa.Column("lender", sa.String(), server_default="", nullable=False),
        # 1 = first mortgage, 2 = HELOC/second. Required to compute CLTV.
        sa.Column("lien_position", sa.SmallInteger(), server_default="1", nullable=False),

        sa.Column("original_principal", sa.Numeric(14, 2), nullable=False),
        # Fallback when no account_id is linked.
        sa.Column("current_principal", sa.Numeric(14, 2)),
        sa.Column("interest_rate_pct", sa.Numeric(6, 3), nullable=False),
        sa.Column("rate_type", sa.String(10), server_default="fixed", nullable=False),
        sa.Column("term_months", sa.Integer(), nullable=False),
        sa.Column("origination_date", sa.Date(), nullable=False),
        sa.Column("first_payment_date", sa.Date()),
        sa.Column("payment_day", sa.SmallInteger()),

        # P&I only. NULL derives it via amortization.pmt().
        sa.Column("payment_amount", sa.Numeric(14, 2)),
        # Deliberately separate from payment_amount: escrowed taxes and
        # insurance do not pay down principal, and property economics already
        # counts them as operating expenses. Folding them into the payment
        # would both double-count the money and overstate equity.
        sa.Column("escrow_monthly", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("pmi_monthly", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("extra_monthly", sa.Numeric(14, 2), server_default="0", nullable=False),

        sa.Column("io_months", sa.Integer(), server_default="0", nullable=False),
        sa.Column("balloon_date", sa.Date()),
        sa.Column("notes", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "created_at", postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_loans_property_id", "loans", ["property_id"])
    op.create_index("ix_loans_account_id", "loans", ["account_id"])

    op.create_table(
        "rental_terms",
        # Per-unit lease detail. Single-unit properties can ignore this and
        # use properties.monthly_rent; multi-unit needs a row per unit.
        sa.Column(
            "property_id",
            sa.String(),
            sa.ForeignKey("properties.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("unit_label", sa.String(40), server_default="", primary_key=True),
        sa.Column("monthly_rent", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("lease_start", sa.Date()),
        sa.Column("lease_end", sa.Date()),
        sa.Column("tenant_name", sa.String(), server_default="", nullable=False),
        sa.Column("notes", sa.Text(), server_default="", nullable=False),
    )


def downgrade() -> None:
    op.drop_table("rental_terms")
    op.drop_index("ix_loans_account_id", table_name="loans")
    op.drop_index("ix_loans_property_id", table_name="loans")
    op.drop_table("loans")
    op.drop_index(
        "ix_property_valuations_property_as_of", table_name="property_valuations"
    )
    op.drop_table("property_valuations")
    op.drop_index("ix_properties_status", table_name="properties")
    op.drop_table("properties")
