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
    # The imported record's own figures. None is a no-op, so every existing
    # caller keeps its behaviour; they are settable only so a row a sync
    # refuses to publish — an unreadable date, an unreadable amount — can be
    # repaired without leaving the page that reported the problem.
    date: Optional[str] = None
    amount: Optional[float] = None
    reviewed: Optional[bool] = None  # server defaults to True on any user edit
    category: Optional[str] = None   # None=no-op, ""=clear, "X"=set to X
    transaction_type: Optional[Literal["debit", "credit"]] = None  # None=no-op
    # Mark this txn as an internal transfer to a manual account. The destination's
    # balance picks it up via the live txn-delta computation in balances.py;
    # spending/recurring aggregates exclude it. None=no-op, ""=clear, "id"=set.
    transfer_to_account_id: Optional[str] = None


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
    # Which integration produced this row. Stamped by the append helper that
    # builds it, never read from the cached dict — consumers must not have to
    # infer provenance (inferring it from absence is what made healthy
    # SnapTrade brokerages render as broken SimpleFIN connections).
    source: Literal["simplefin", "manual", "snaptrade"] = "simplefin"
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
    # Real assets only: the ISO date the user last set this account's value.
    # Nothing estimates a house or a car — the app only reports how stale the
    # number the user typed has become.
    valuation_updated_on: Optional[str] = None
    # Real assets with a linked loan only. Presentational: neither figure
    # changes any total on the summary — the loan is counted once, in
    # total_credit_debt. None means "unknown", never "no debt".
    secured_debt: Optional[float] = None
    equity: Optional[float] = None
    # Investment accounts only. All three travel together on purpose: with
    # only the resolved value the UI would present an inference as a fact,
    # and a Roth 401(k) is indistinguishable from a traditional one until the
    # user says which it is.
    tax_treatment: Optional[str] = None
    tax_treatment_inferred: Optional[str] = None
    tax_treatment_set_by_user: bool = False


class AccountDetailsIn(BaseModel):
    """User-supplied credit-card / savings metadata (not exposed by SimpleFIN)."""
    apr: Optional[float] = None
    credit_limit: Optional[float] = None
    minimum_payment: Optional[float] = None
    statement_day: Optional[int] = None   # 1-31 (day of month the statement cuts)
    due_day: Optional[int] = None         # 1-31 (day of month the payment is due)
    opened_on: Optional[str] = None       # YYYY-MM-DD, user-entered
    valuation_updated_on: Optional[str] = None  # YYYY-MM-DD, real assets only
    secured_by_account_id: Optional[str] = None  # real assets: the loan behind it
    # How the balance is taxed. None means unanswered — the app shows an
    # inference beside it rather than storing one on the user's behalf.
    tax_treatment: Optional[
        Literal["taxable", "traditional", "roth", "hsa", "education", "other"]
    ] = None
    notes: str = ""


class AccountDetails(AccountDetailsIn):
    account_id: str
    created: str
    updated: str


class ManualAccountIn(BaseModel):
    institution: str
    name: str
    type: str              # "depository" | "credit" | "investment" | "asset"
    subtype: str = ""
    available: float = 0.0
    ledger: float = 0.0


class UserProfileIn(BaseModel):
    """Editable household preferences. All fields optional — partial PUTs
    are merged into the stored row so the UI can update one field at a time."""
    risk_tolerance: Optional[Literal["conservative", "balanced", "aggressive"]] = None
    time_horizon_years: Optional[int] = None
    dependents: Optional[int] = None
    debt_strategy: Optional[Literal["avalanche", "snowball", "minimum"]] = None
    monthly_income: Optional[float] = None
    emergency_fund_months: Optional[int] = None
    birth_year: Optional[int] = None
    target_retirement_age: Optional[int] = None
    annual_retirement_spend: Optional[float] = None
    expected_return_pct: Optional[float] = None
    notes: Optional[str] = None


class UserProfileOut(BaseModel):
    risk_tolerance: Optional[str] = None
    time_horizon_years: Optional[int] = None
    dependents: Optional[int] = None
    debt_strategy: Optional[str] = None
    monthly_income: Optional[float] = None
    emergency_fund_months: Optional[int] = None
    birth_year: Optional[int] = None
    target_retirement_age: Optional[int] = None
    annual_retirement_spend: Optional[float] = None
    expected_return_pct: Optional[float] = None
    notes: str = ""
    updated_at: Optional[str] = None


class CategoryRuleIn(BaseModel):
    match: str
    category: str


class CategoryRule(CategoryRuleIn):
    id: int
    position: int


class CategoryRulesReplace(BaseModel):
    """Whole-list replace — list order *is* the evaluation order."""
    rules: List[CategoryRuleIn]


class ManualAccountUpdate(BaseModel):
    """Edit payload for PUT /balances/manual/{id} — only the balances."""
    available: Optional[float] = None
    ledger: Optional[float] = None


class ConnectionHealth(BaseModel):
    """One institution's connection state as of the last sync.

    Derived from cached sync results rather than a live provider call, so
    rendering the Accounts page costs no aggregator round-trip.
    """
    institution: str
    status: Literal["connected", "disconnected", "manual"]
    last_error: Optional[str] = None


class BalancesSummary(BaseModel):
    net_worth: float
    total_cash: float
    total_credit_debt: float
    total_investments: float = 0.0
    # Homes, vehicles and the like. Deliberately its own line rather than
    # folded into cash or investments: it raises net worth without improving
    # resilience, and the runway ratio ignores it.
    total_real_assets: float = 0.0
    accounts: List[AccountBalance]
    connections: List[ConnectionHealth] = Field(default_factory=list)
    from_cache: bool = False
    cache_fetched_at: Optional[str] = None


class PayoffAccount(BaseModel):
    name: str
    balance: float
    apr: float        # e.g. 24.99 means 24.99%
    min_payment: float


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
    # Pace: month-to-date spend read against elapsed time, so a budget can be
    # flagged while the month can still be changed.
    month_progress_pct: float = 0.0
    projected_month_end: Optional[float] = None
    pace_status: str = "on_track"   # on_track | over_pace | over_budget | under
    projected_overage: Optional[float] = None


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
