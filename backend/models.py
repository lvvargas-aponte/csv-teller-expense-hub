"""Pydantic request/response models for all route handlers."""
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class Account(BaseModel):
    id: str
    name: str
    type: str
    subtype: str
    balance: Dict[str, Any]
    institution: Dict[str, Any]


class TransactionUpdate(BaseModel):
    is_shared: bool
    who: Optional[str] = None
    what: Optional[str] = None
    person_1_owes: Optional[float] = None
    person_2_owes: Optional[float] = None
    notes: Optional[str] = None
    reviewed: Optional[bool] = None  # server defaults to True on any user edit
    category: Optional[str] = None   # None=no-op, ""=clear, "X"=set to X
    transaction_type: Optional[Literal["debit", "credit"]] = None  # None=no-op
    # Mark this txn as an internal transfer to a manual account. The destination's
    # balance picks it up via the live txn-delta computation in balances.py;
    # spending/recurring aggregates exclude it. None=no-op, ""=clear, "id"=set.
    transfer_to_account_id: Optional[str] = None
    # Attribute this transaction to a property, so rent and repairs land in
    # that property's actuals. None=no-op, ""=clear, "prop_x"=set.
    property_id: Optional[str] = None


class BulkTransactionUpdate(BaseModel):
    transaction_ids: List[str]
    is_shared: bool
    who: Optional[str] = None
    what: Optional[str] = None
    notes: Optional[str] = None
    split_evenly: bool = True  # if True, auto-calculate 50/50 from each transaction's amount
    reviewed: Optional[bool] = None  # server defaults to True on any user edit
    category: Optional[str] = None   # None=no-op, ""=clear, "X"=set to X
    transfer_to_account_id: Optional[str] = None  # None=no-op, ""=clear, "id"=set
    property_id: Optional[str] = None             # None=no-op, ""=clear, "prop_x"=set


class BulkSuggestRequest(BaseModel):
    transaction_ids: List[str]


class CategoryAssignment(BaseModel):
    transaction_id: str
    category: str   # "" allowed = clear


class ApplyCategoriesRequest(BaseModel):
    items: List[CategoryAssignment]


class SimplefinClaimRequest(BaseModel):
    setup_token: str


class SimplefinSyncRequest(BaseModel):
    from_date: Optional[str] = None         # YYYY-MM-DD; defaults to first day of previous month
    to_date: Optional[str] = None           # YYYY-MM-DD; defaults to last day of previous month
    account_ids: Optional[List[str]] = None  # if set, only sync these account IDs (None = all)


class SendToSheetRequest(BaseModel):
    sheet_name:   Optional[str] = None   # overrides SHEET_NAME env var when provided
    filter_month: Optional[str] = None   # "YYYY-MM" — restrict to transactions in this month


class AccountBalance(BaseModel):
    id: str
    institution: str
    name: str
    type: str
    subtype: str
    available: float
    ledger: float
    manual: bool = False   # True for user-added accounts not sourced from SimpleFIN
    # For manual accounts: the user-edited balance is treated as a starting
    # point and the live ``available``/``ledger`` above is computed as
    # ``starting + signed delta of linked transactions``. This field exposes
    # the starting value so the UI can show both. None for SimpleFIN accounts.
    starting_balance: Optional[float] = None
    txn_delta: Optional[float] = None  # signed delta applied to starting balance
    # Count of transactions feeding the delta + most-recent date among them.
    # Drives the "Last updated · from N linked transactions" badge in the UI.
    linked_txn_count: int = 0
    linked_last_date: Optional[str] = None
    # Set when a previously-connected SimpleFIN account was disconnected but
    # kept locally. UI shows a "Disconnected" badge instead of treating it as
    # a native manual account. None for both fresh manuals and live rows.
    disconnected_from: Optional[str] = None
    disconnected_at: Optional[str] = None


class AccountDetailsIn(BaseModel):
    """User-supplied credit-card / savings metadata (not exposed by SimpleFIN)."""
    apr: Optional[float] = None
    credit_limit: Optional[float] = None
    minimum_payment: Optional[float] = None
    statement_day: Optional[int] = None   # 1-31 (day of month the statement cuts)
    due_day: Optional[int] = None         # 1-31 (day of month the payment is due)
    notes: str = ""
    # Debt Payoff Planner metadata
    debt_class: Optional[Literal["credit_card", "loan", "other"]] = None
    asset_value: Optional[float] = None       # current market value, for "loan" class — drives equity
    due_date: Optional[str] = None            # ISO YYYY-MM-DD
    deferred_interest: bool = False
    promo_apr: Optional[float] = None         # rate that applies until promo_expires
    promo_expires: Optional[str] = None       # ISO YYYY-MM-DD
    # Minimum-only stretch: the user is deliberately paying just the minimum
    # between these dates, then has to clear the rest before promo_expires.
    # Both ISO YYYY-MM-DD; either may be None (open-ended on that side).
    min_payment_from: Optional[str] = None
    min_payment_until: Optional[str] = None
    # Payoff progress tracking. `payoff_start_balance` is what was owed when
    # the user started working this debt down — the live balance alone can't
    # show progress, since it only ever reports "now".
    payoff_start_balance: Optional[float] = None
    payoff_start_date: Optional[str] = None   # ISO YYYY-MM-DD
    # Account the payments come from, so the funding-side transactions can be
    # matched back to this debt (e.g. a Truist debit paying a Synchrony card).
    payment_account_id: Optional[str] = None


class AccountDetails(AccountDetailsIn):
    account_id: str
    created: str
    updated: str


class ManualAccountIn(BaseModel):
    institution: str
    name: str
    type: str              # "depository" | "credit" | "investment"
    subtype: str = ""
    available: float = 0.0
    ledger: float = 0.0


class PropertyIn(BaseModel):
    """Create/update payload for a real-estate holding.

    The full operating-expense model is present so a rental has an honest
    pro forma from the moment it is created, before any transaction has been
    tagged to it. Percentage fields are whole percents (5 == 5%).
    """
    name: str
    address: str = ""
    property_type: Literal[
        "single_family", "multi_family", "condo", "townhouse", "land", "commercial"
    ] = "single_family"
    # Gates whether the property contributes rent to cash flow / retirement.
    status: Literal[
        "rental", "primary_residence", "vacation", "held_for_sale", "under_renovation"
    ] = "rental"
    units: int = 1

    purchase_date: Optional[str] = None       # ISO YYYY-MM-DD
    purchase_price: Optional[float] = None
    closing_costs: float = 0.0
    capital_improvements: float = 0.0

    # Scheduled rent per the lease; actuals come from tagged transactions.
    monthly_rent: float = 0.0
    other_monthly_income: float = 0.0
    vacancy_rate_pct: float = 5.0

    property_tax_annual: float = 0.0
    insurance_annual: float = 0.0
    hoa_monthly: float = 0.0
    utilities_monthly: float = 0.0
    landscaping_monthly: float = 0.0
    other_monthly_expense: float = 0.0
    mgmt_fee_pct: float = 0.0
    maintenance_pct_of_rent: float = 5.0
    capex_reserve_pct_of_rent: float = 5.0

    # None = fall back to the household retirement assumption.
    appreciation_pct: Optional[float] = None
    rent_growth_pct: Optional[float] = None

    # Transaction auto-SUGGEST rules; matches never write property_id directly.
    rules: List[Dict[str, Any]] = []
    operating_account_id: Optional[str] = None
    notes: str = ""


class ValuationIn(BaseModel):
    """A point-in-time property value. One per property per day — re-valuing
    the same day overwrites rather than accumulating near-duplicates."""
    value: float
    as_of: Optional[str] = None               # ISO YYYY-MM-DD; defaults to today
    source: Literal["manual", "appraisal", "avm", "purchase"] = "manual"
    notes: str = ""


class LoanIn(BaseModel):
    """Create/update payload for amortizing debt.

    ``escrow_monthly`` is deliberately separate from ``payment_amount``:
    escrowed taxes and insurance don't pay down principal, and property
    economics already counts them as operating expenses.
    """
    name: str
    loan_type: Literal[
        "mortgage", "heloc", "auto", "student", "personal", "business", "other"
    ] = "mortgage"
    property_id: Optional[str] = None
    account_id: Optional[str] = None
    lender: str = ""
    lien_position: int = 1                    # 1 = first, 2 = HELOC/second

    original_principal: float
    current_principal: Optional[float] = None
    interest_rate_pct: float
    rate_type: Literal["fixed", "arm", "io"] = "fixed"
    term_months: int
    origination_date: str                     # ISO YYYY-MM-DD
    first_payment_date: Optional[str] = None
    payment_day: Optional[int] = None

    payment_amount: Optional[float] = None    # P&I only; derived when omitted
    escrow_monthly: float = 0.0
    pmi_monthly: float = 0.0
    extra_monthly: float = 0.0
    io_months: int = 0
    balloon_date: Optional[str] = None
    notes: str = ""


class DealInputs(BaseModel):
    """A hypothetical property purchase.

    ``funded_from`` matters more than it looks: when the down payment is
    borrowed against a property you already own, that borrowing has a
    carrying cost, and the analyzer reports portfolio-level cash flow rather
    than the deal's own. A deal can be positive standalone and still reduce
    total monthly income.
    """
    purchase_price: float
    down_pct: float = 25.0
    rate_pct: float = 7.0
    term_months: int = 360
    monthly_rent: float = 0.0
    vacancy_pct: float = 5.0
    # Operating expenses as a share of collected rent — a planning estimate,
    # replaced by the property's own expense model once it is owned.
    opex_pct: float = 35.0
    closing_pct: float = 3.0
    rehab: float = 0.0
    funded_from: Literal["cash", "heloc", "cash_out_refi"] = "cash"
    source_property_id: Optional[str] = None


class RetirementAssumptionsIn(BaseModel):
    """Retirement projection assumptions.

    Every field is optional: an omitted value falls back to the module
    default rather than being frozen into the saved record, so improving a
    default later benefits anyone who never set it explicitly.
    """
    current_age: Optional[int] = None
    # None = solve for the earliest sustainable year rather than assume one.
    target_retirement_age: Optional[int] = None
    investment_return_pct: Optional[float] = None
    inflation_pct: Optional[float] = None
    rent_growth_pct: Optional[float] = None
    expense_growth_pct: Optional[float] = None
    appreciation_pct: Optional[float] = None
    safe_withdrawal_rate_pct: Optional[float] = None
    # None = derive from actual trailing spending, which beats a guessed
    # percentage of income: it is what this household really costs.
    retirement_spending_monthly: Optional[float] = None
    monthly_contribution: Optional[float] = None
    contribution_growth_pct: Optional[float] = None
    social_security_monthly: Optional[float] = None
    social_security_start_age: Optional[int] = None
    tax_rate_on_withdrawals_pct: Optional[float] = None
    effective_tax_rate_on_rental_pct: Optional[float] = None
    horizon_years: Optional[int] = None


class LoanWhatIfRequest(BaseModel):
    """"What if I paid $X more each month?" for a single loan."""
    extra_monthly: float = 0.0


class UserProfileIn(BaseModel):
    """Editable household preferences. All fields optional — partial PUTs
    are merged into the stored row so the UI can update one field at a time."""
    risk_tolerance: Optional[Literal["conservative", "balanced", "aggressive"]] = None
    time_horizon_years: Optional[int] = None
    dependents: Optional[int] = None
    debt_strategy: Optional[Literal["avalanche", "snowball", "minimum"]] = None
    notes: Optional[str] = None


class UserProfileOut(BaseModel):
    risk_tolerance: Optional[str] = None
    time_horizon_years: Optional[int] = None
    dependents: Optional[int] = None
    debt_strategy: Optional[str] = None
    notes: str = ""
    updated_at: Optional[str] = None


class ManualAccountUpdate(BaseModel):
    """Edit payload for PUT /balances/manual/{id} — only the balances."""
    available: Optional[float] = None
    ledger: Optional[float] = None


class BalancesSummary(BaseModel):
    net_worth: float
    total_cash: float
    total_credit_debt: float
    total_investments: float = 0.0
    # Real estate. ``total_property_debt`` is reported for display only — the
    # portion secured by a synced account is already inside
    # ``total_credit_debt``, so summing these two double-counts the mortgage.
    total_property_value: float = 0.0
    total_property_debt: float = 0.0
    total_property_equity: float = 0.0
    unvalued_properties: List[str] = []
    accounts: List[AccountBalance]
    from_cache: bool = False
    cache_fetched_at: Optional[str] = None


class PayoffAccount(BaseModel):
    name: str
    balance: float
    apr: float        # e.g. 24.99 means 24.99%
    min_payment: float
    promo_apr: Optional[float] = None       # deferred-interest rate that applies until promo_expires
    promo_expires: Optional[str] = None     # ISO YYYY-MM-DD


class PayoffRequest(BaseModel):
    accounts: list[PayoffAccount]
    strategy: str = "avalanche"   # "avalanche" or "snowball"
    extra_monthly: float = 0.0


class PayoffAdviceRequest(BaseModel):
    accounts: list[PayoffAccount]
    strategy: str = "avalanche"
    extra_monthly: float = 0.0
    plan_results: Optional[Dict[str, Any]] = None  # optional — include when calc has already been run


# ---------------------------------------------------------------------------
# Allocation waterfall
# ---------------------------------------------------------------------------

class AllocateRequest(BaseModel):
    amount: float = Field(..., gt=0)
    # "monthly" = a recurring surplus; "one_time" = a bonus or refund. The
    # tiers behave differently: an employer match can only be captured
    # through payroll, so a lump sum skips that tier entirely.
    cadence: Literal["monthly", "one_time"] = "monthly"
    as_of: Optional[str] = None      # ISO YYYY-MM-DD, for reproducible tests


class AllocationSettingsIn(BaseModel):
    """The handful of facts the waterfall cannot derive from transactions.

    Every field is optional. ``employer_match_known`` stays ``None`` until
    the user answers, which is what makes the waterfall ask rather than
    quietly assume there is no match.
    """
    emergency_fund_months: Optional[int] = Field(None, ge=0, le=24)
    employer_match_known: Optional[bool] = None
    employer_match_pct: Optional[float] = Field(None, ge=0, le=200)
    employer_match_limit_pct_of_pay: Optional[float] = Field(None, ge=0, le=100)
    annual_gross_income: Optional[float] = Field(None, ge=0)
    annual_contribution_limits: Optional[Dict[str, float]] = None
    contribution_limits_as_of_year: Optional[int] = None
    contributed_ytd: Optional[Dict[str, float]] = None


# ---------------------------------------------------------------------------
# Virtual advisor (chat) models
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str        # "user" | "assistant" | "system"
    content: str
    ts: Optional[str] = None   # ISO timestamp; set by the server on append


class ChatRequest(BaseModel):
    conversation_id: Optional[str] = None   # None starts a new conversation
    message: str


class ChatResponse(BaseModel):
    conversation_id: str
    reply: Optional[str] = None             # None when ai_available=False
    ai_available: bool
    # Stable id of the assistant turn that was just persisted; clients use
    # it to attach 👍/👎 feedback. None when ai_available=False or when the
    # turn couldn't be located (rare, persistence race).
    turn_id: Optional[int] = None


class FeedbackRequest(BaseModel):
    rating: Literal[-1, 1]
    note: Optional[str] = None


class StyleProfileOut(BaseModel):
    style_notes: str
    turn_count_at_last_update: int
    updated_at: Optional[str] = None


class ConversationSummary(BaseModel):
    conversation_id: str
    created: str
    updated: str
    message_count: int
    preview: str                            # first user message, trimmed


class Conversation(BaseModel):
    conversation_id: str
    created: str
    updated: str
    messages: List[ChatMessage]


# ---------------------------------------------------------------------------
# Budgets — monthly per-category caps (household-level)
# ---------------------------------------------------------------------------

class BudgetIn(BaseModel):
    category: str
    monthly_limit: float
    notes: str = ""


class Budget(BaseModel):
    category: str
    monthly_limit: float
    notes: str = ""
    created: str
    updated: str


class BudgetStatus(BaseModel):
    """Budget enriched with current-month progress for display + advisor."""
    category: str
    monthly_limit: float
    notes: str = ""
    current_month_spent: float
    percent_used: float
    over_budget: bool


# ---------------------------------------------------------------------------
# Savings goals
# ---------------------------------------------------------------------------

class GoalIn(BaseModel):
    name: str
    target_amount: float
    target_date: Optional[str] = None        # YYYY-MM-DD
    linked_account_id: Optional[str] = None  # if set, the account's `available` is used live
    current_balance: float = 0.0             # manual progress tracker when no linked account
    kind: str = "savings"                    # "savings" | "emergency_fund" | "travel" | "big_purchase"
    notes: str = ""


class Goal(BaseModel):
    id: str
    name: str
    target_amount: float
    target_date: Optional[str] = None
    linked_account_id: Optional[str] = None
    current_balance: float = 0.0
    kind: str = "savings"
    notes: str = ""
    created: str
    updated: str


class GoalStatus(BaseModel):
    """Goal enriched with current progress + pacing for display + advisor."""
    id: str
    name: str
    kind: str
    target_amount: float
    target_date: Optional[str] = None
    linked_account_id: Optional[str] = None
    current_balance: float
    progress_pct: float
    months_remaining: Optional[int] = None
    monthly_required: Optional[float] = None  # to hit target by target_date
    notes: str = ""
