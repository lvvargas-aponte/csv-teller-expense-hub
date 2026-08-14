"""Pydantic models for tool arguments and trajectory events.

The harness validates every tool call's arguments against the JSON schema
exposed in the tool registry — these Pydantic models are the source of
truth for those schemas. Keep them aligned with the handler signatures
in ``agent.tools``.
"""
from __future__ import annotations

from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Tool argument models
# ---------------------------------------------------------------------------

class SearchTransactionsArgs(BaseModel):
    query: str = Field(..., description="Free-text query, e.g. 'that $300 charge from last month'")
    category: Optional[str] = Field(None, description="Optional category to restrict the search to")
    start_date: Optional[str] = Field(None, description="ISO date (YYYY-MM-DD) inclusive lower bound")
    end_date: Optional[str] = Field(None, description="ISO date (YYYY-MM-DD) inclusive upper bound")
    limit: int = Field(5, ge=1, le=20)


class GetBalanceArgs(BaseModel):
    account_type: Literal["cash", "credit", "investment", "all"] = "all"


class ListAccountsArgs(BaseModel):
    account_type: Literal["cash", "credit", "investment", "all"] = Field(
        "all", description="Filter to one bucket, or 'all' for every account."
    )


class GetDebtArgs(BaseModel):
    account_name: Optional[str] = Field(
        None, description="Substring match on the account name; omit for all credit accounts"
    )


class GetBudgetStatusArgs(BaseModel):
    category: Optional[str] = Field(None, description="Single category to look up; omit for all")


class GetGoalStatusArgs(BaseModel):
    goal_id: Optional[str] = Field(None, description="Specific goal id; omit for all")


class ProjectCashflowArgs(BaseModel):
    horizon_days: int = Field(30, ge=1, le=180)


class GetInvestmentsArgs(BaseModel):
    symbol: Optional[str] = Field(
        None, description="Filter to one ticker symbol (case-insensitive). Omit for the full portfolio.",
    )
    asset_type: Optional[str] = Field(
        None, description="Filter by asset type (e.g. 'stock', 'etf', 'crypto'). Omit for all.",
    )


class SearchDocumentsArgs(BaseModel):
    query: str = Field(..., description="Free-text query, e.g. 'IRS Roth contribution limit'.")
    scope: Optional[str] = Field(
        None, description="Restrict to 'personal' (user-uploaded) or 'external' (reference docs).",
    )
    category: Optional[str] = Field(
        None, description="Optional document category filter (e.g. 'tax', 'statement').",
    )
    limit: int = Field(4, ge=1, le=10)


class RecallPastConversationArgs(BaseModel):
    query: str = Field(..., description="Free-text query, e.g. 'discussion about retirement allocation'.")
    limit: int = Field(5, ge=1, le=20)


class GetCategorySpendingArgs(BaseModel):
    category: str = Field(..., description="Category name to aggregate (case-insensitive), e.g. 'Drinks'")
    start_date: Optional[str] = Field(None, description="ISO date (YYYY-MM-DD) inclusive lower bound")
    end_date: Optional[str] = Field(None, description="ISO date (YYYY-MM-DD) inclusive upper bound")


_FactCategory = Literal["preference", "constraint", "goal", "life_event", "pattern"]


class RememberAboutUserArgs(BaseModel):
    fact: str = Field(..., description="A short statement Fin should remember about the user (one sentence).")
    category: _FactCategory = Field(
        ..., description="preference | constraint | goal | life_event | pattern"
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Freeform tags for grouping, e.g. ['debt','retirement']. Keep to <=5.",
    )
    sensitive: bool = Field(
        False,
        description="Mark true if this fact involves medical, relationship, or income detail the user may not want shoulder-surfed.",
    )


class SyncTransactionsArgs(BaseModel):
    from_date: Optional[str] = Field(
        None, description="ISO YYYY-MM-DD lower bound; omit for the default previous-month range."
    )
    to_date: Optional[str] = Field(
        None, description="ISO YYYY-MM-DD upper bound; omit for the default previous-month range."
    )


class RefreshBalancesArgs(BaseModel):
    pass


class SyncInvestmentsArgs(BaseModel):
    pass


_SyncTaskType = Literal["sync_transactions", "refresh_balances", "sync_investments"]


class ScheduleSyncArgs(BaseModel):
    task_type: _SyncTaskType = Field(
        ..., description="Which sync to run on a schedule."
    )
    interval_days: int = Field(
        7, ge=1, le=90, description="Days between runs; 7 = weekly (default)."
    )


class ListScheduledTasksArgs(BaseModel):
    pass


class CancelScheduledTaskArgs(BaseModel):
    task_id: int = Field(..., description="Id from list_scheduled_tasks.")


class ThinkArgs(BaseModel):
    thought: str = Field(..., description="A short numbered plan or reasoning note for yourself.")


class WebSearchArgs(BaseModel):
    query: str = Field(..., description="Search query, e.g. 'NVDA earnings outlook 2026' or 'current high-yield savings rates'.")
    max_results: int = Field(5, ge=1, le=10)


class FetchWebpageArgs(BaseModel):
    url: str = Field(..., description="Full https:// URL to fetch and read, usually from a web_search result.")


class GetStockQuoteArgs(BaseModel):
    symbols: List[str] = Field(
        ..., min_length=1, max_length=10,
        description="Ticker symbols to quote, e.g. ['NVDA', 'VOO']. Max 10.",
    )


class GetStockHistoryArgs(BaseModel):
    symbol: str = Field(..., description="Single ticker symbol, e.g. 'NVDA'.")
    period: Literal["1mo", "3mo", "6mo", "1y", "5y"] = "6mo"


class GetStockFundamentalsArgs(BaseModel):
    symbol: str = Field(..., description="Single ticker symbol, e.g. 'NVDA'.")


class RecallAboutUserArgs(BaseModel):
    query: str = Field(..., description="Free-text query, e.g. 'retirement goals' or 'feelings about debt'.")
    category: Optional[_FactCategory] = Field(
        None, description="Restrict recall to one category; omit for all."
    )
    limit: int = Field(5, ge=1, le=20)


# ---------------------------------------------------------------------------
# Trajectory event — what we persist alongside each turn
# ---------------------------------------------------------------------------

class TrajectoryEvent(BaseModel):
    iteration: int
    kind: Literal["tool_call", "tool_result", "tool_error", "final", "terminated"]
    tool_name: Optional[str] = None
    arguments: Optional[dict] = None
    result_summary: Optional[str] = None  # truncated string preview
    error: Optional[str] = None
    terminated_reason: Optional[str] = None


class AgentResult(BaseModel):
    reply: Optional[str]
    trajectory: List[TrajectoryEvent]
    terminated_reason: str
    iterations: int
