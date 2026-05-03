"""Pydantic request/response models for all route handlers."""
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel


class RegisterTokenRequest(BaseModel):
    access_token: str
    enrollment_id: str
    institution: str = ""
    # When the user is reconnecting from a "Connection Error" row but the
    # backend lost its in-memory enrollment_map (e.g. after a restart), the
    # frontend can pass that row's id here so the stale token is removed as
    # part of registering the fresh one — otherwise the dead token lingers.
    old_account_id: Optional[str] = None


class ReplaceTokenRequest(BaseModel):
    old_enrollment_id: str   # identifies the broken token to remove
    new_access_token: str
    new_enrollment_id: str
    institution: str = ""
    # Belt-and-suspenders fallback: if the enrollment map has been cleared,
    # the frontend can also send the _error_ row id to guarantee cleanup.
    old_account_id: Optional[str] = None


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


class BulkTransactionUpdate(BaseModel):
    transaction_ids: List[str]
    is_shared: bool
    who: Optional[str] = None
    what: Optional[str] = None
    notes: Optional[str] = None
    split_evenly: bool = True  # if True, auto-calculate 50/50 from each transaction's amount
    reviewed: Optional[bool] = None  # server defaults to True on any user edit
    category: Optional[str] = None   # None=no-op, ""=clear, "X"=set to X


class BulkSuggestRequest(BaseModel):
    transaction_ids: List[str]


class CategoryAssignment(BaseModel):
    transaction_id: str
    category: str   # "" allowed = clear


class ApplyCategoriesRequest(BaseModel):
    items: List[CategoryAssignment]


class TellerSyncRequest(BaseModel):
    from_date: Optional[str] = None         # YYYY-MM-DD; defaults to first day of previous month
    to_date: Optional[str] = None           # YYYY-MM-DD; defaults to last day of previous month
    count: int = 500                        # max transactions to fetch per account before date filtering
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
    manual: bool = False   # True for user-added accounts not sourced from Teller


class AccountDetailsIn(BaseModel):
    """User-supplied credit-card / savings metadata (not exposed by Teller)."""
    apr: Optional[float] = None
    credit_limit: Optional[float] = None
    minimum_payment: Optional[float] = None
    statement_day: Optional[int] = None   # 1-31 (day of month the statement cuts)
    due_day: Optional[int] = None         # 1-31 (day of month the payment is due)
    notes: str = ""


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
    accounts: List[AccountBalance]
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
    kind: str = "savings"                    # "savings" | "emergency_fund"
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
