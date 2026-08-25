"""Tool registry for the Fin agent harness.

Every tool here is a thin wrapper over existing helpers in ``analytics``,
``embeddings``, or ``state``. The single-responsibility rule: this module
adapts existing capabilities into agent-callable shapes — it does NOT
introduce new business logic. New analytics belong in ``analytics.py``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Type

from pydantic import BaseModel

import config
import state
from analytics import (
    _balances_snapshot,
    _debts_from_accounts,
    _investments_snapshot,
    category_spending_summary,
    classify_account_bucket,
    compute_budget_statuses,
    compute_goal_statuses,
    project_cashflow,
)
from db import documents_repo, user_facts_repo
from embeddings import (
    embed_pending_user_facts,
    embed_text,
    retrieve_similar,
    retrieve_similar_facts,
    retrieve_similar_transactions,
)

from agent.schemas import (
    ListAccountsArgs,
    ThinkArgs,
    GetBalanceArgs,
    GetBudgetStatusArgs,
    GetCategorySpendingArgs,
    GetDebtArgs,
    GetGoalStatusArgs,
    GetInvestmentsArgs,
    ProjectCashflowArgs,
    RecallAboutUserArgs,
    RecallPastConversationArgs,
    RememberAboutUserArgs,
    SearchDocumentsArgs,
    SearchTransactionsArgs,
)


Handler = Callable[[BaseModel], Awaitable[Any]]


class TransientToolError(Exception):
    """A tool failure that is likely temporary (rate limit, flaky upstream).

    The harness exempts one retry of the same call from the repeated-call
    guard and tells the model it may try again."""


@dataclass
class Tool:
    name: str
    description: str
    args_model: Type[BaseModel]
    handler: Handler
    result_max_chars: int = 4000


class ToolRegistry:
    def __init__(self, tools: List[Tool]):
        self._by_name: Dict[str, Tool] = {t.name: t for t in tools}

    def get(self, name: str) -> Optional[Tool]:
        return self._by_name.get(name)

    def names(self) -> List[str]:
        return list(self._by_name.keys())

    def openai_tools(self) -> List[Dict[str, Any]]:
        """Render registered tools in Ollama's OpenAI-compatible shape."""
        out: List[Dict[str, Any]] = []
        for t in self._by_name.values():
            schema = t.args_model.model_json_schema()
            # Drop pydantic's `title` keys for a cleaner schema sent to the model.
            schema.pop("title", None)
            for prop in (schema.get("properties") or {}).values():
                prop.pop("title", None)
            out.append({
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": schema,
                },
            })
        return out


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def _think(args: ThinkArgs) -> Dict[str, Any]:
    return {"ok": True, "note": "Plan recorded. Execute it with the other tools now."}


async def _search_transactions(args: SearchTransactionsArgs) -> Dict[str, Any]:
    hits = await retrieve_similar_transactions(args.query, k=args.limit)
    results: List[Dict[str, Any]] = []
    for h in hits:
        if args.category and (h.get("category") or "").lower() != args.category.lower():
            continue
        date_str = (h.get("date") or "")[:10]
        if args.start_date and date_str < args.start_date:
            continue
        if args.end_date and date_str > args.end_date:
            continue
        results.append({
            "date": date_str,
            "description": h.get("description", ""),
            "amount": h.get("amount"),
            "category": h.get("category") or "Uncategorized",
        })
    return {"query": args.query, "count": len(results), "transactions": results}


async def _get_balance(args: GetBalanceArgs) -> Dict[str, Any]:
    snap = _balances_snapshot()
    if args.account_type == "cash":
        return {"total_cash": snap["total_cash"]}
    if args.account_type == "credit":
        return {"total_credit_debt": snap["total_credit_debt"]}
    if args.account_type == "investment":
        return {"total_investments": snap["total_investments"]}
    return {
        "net_worth": snap["net_worth"],
        "total_cash": snap["total_cash"],
        "total_credit_debt": snap["total_credit_debt"],
        "total_investments": snap["total_investments"],
        "total_real_assets": snap["total_real_assets"],
    }


async def _list_accounts(args: ListAccountsArgs) -> Dict[str, Any]:
    snap = _balances_snapshot()
    rows: List[Dict[str, Any]] = []
    for source, accounts in (
        ("simplefin", snap["linked_accounts"]),
        ("snaptrade", snap["snaptrade_accounts"]),
        ("manual", snap["manual_accounts"]),
    ):
        for acct in accounts:
            bucket = classify_account_bucket(
                acct.get("type", ""), acct.get("subtype", "")
            )
            if args.account_type != "all" and bucket != args.account_type:
                continue
            balance = float(acct.get("available", 0.0) or 0.0)
            if bucket == "credit" or balance == 0.0:
                balance = float(acct.get("ledger", 0.0) or 0.0)
            rows.append({
                "name": acct.get("name", ""),
                "institution": acct.get("institution", ""),
                "bucket": bucket,
                "subtype": acct.get("subtype", "") or acct.get("type", ""),
                "balance": round(balance, 2),
                "source": source,
            })
    return {
        "count": len(rows),
        "accounts": rows,
        "as_of": snap.get("cache_fetched_at"),
    }


async def _get_debt(args: GetDebtArgs) -> Dict[str, Any]:
    snap = _balances_snapshot()
    debts = _debts_from_accounts(snap)
    if args.account_name:
        needle = args.account_name.lower()
        debts = [
            d for d in debts
            if needle in (d.get("name", "").lower())
            or needle in (d.get("institution", "").lower())
        ]
    total = round(sum(float(d.get("balance") or 0.0) for d in debts), 2)
    return {"total_balance": total, "count": len(debts), "debts": debts}


async def _get_budget_status(args: GetBudgetStatusArgs) -> Dict[str, Any]:
    statuses = compute_budget_statuses()
    if args.category:
        needle = args.category.lower()
        statuses = [b for b in statuses if (b.get("category") or "").lower() == needle]
    return {"count": len(statuses), "budgets": statuses}


async def _get_goal_status(args: GetGoalStatusArgs) -> Dict[str, Any]:
    statuses = compute_goal_statuses()
    if args.goal_id:
        statuses = [g for g in statuses if g.get("id") == args.goal_id]
    return {"count": len(statuses), "goals": statuses}


async def _project_cashflow(args: ProjectCashflowArgs) -> Dict[str, Any]:
    return project_cashflow(horizon_days=args.horizon_days)


async def _get_investments(args: GetInvestmentsArgs) -> Dict[str, Any]:
    """Return per-holding investment detail + portfolio summary.

    Wraps ``_investments_snapshot`` so Fin can answer questions about
    stocks, ETFs, crypto, allocation, concentration, and unrealized gain.
    Falls back to a structured "no holdings" response when SnapTrade
    isn't connected — the model needs to know that's why it can't help.
    """
    snap = _investments_snapshot()
    if snap is None:
        return {
            "available": False,
            "note": (
                "No investment holdings synced. The user may not have "
                "connected SnapTrade, or their accounts have no positions. "
                "Suggest connecting via the Investments tab if asked."
            ),
            "holdings": [],
        }

    holdings = list(snap.get("holdings") or [])
    if args.symbol:
        needle = args.symbol.upper()
        holdings = [h for h in holdings if (h.get("symbol") or "").upper() == needle]
    if args.asset_type:
        atype = args.asset_type.lower()
        holdings = [h for h in holdings if (h.get("asset_type") or "").lower() == atype]

    return {
        "available": True,
        "total_value": snap.get("total_value"),
        "total_cost": snap.get("total_cost"),
        "total_gain": snap.get("total_gain"),
        "total_gain_pct": snap.get("total_gain_pct"),
        "holding_count": snap.get("holding_count"),
        "allocation": snap.get("allocation"),
        "concentration": snap.get("concentration"),
        "largest_position_pct": snap.get("largest_position_pct"),
        "concentrated": snap.get("concentrated"),
        "holdings": holdings,
        "symbol_filter": args.symbol,
        "asset_type_filter": args.asset_type,
    }


async def _get_category_spending(args: GetCategorySpendingArgs) -> Dict[str, Any]:
    return category_spending_summary(
        category=args.category,
        start_date=args.start_date,
        end_date=args.end_date,
    )


async def _remember_about_user(args: RememberAboutUserArgs) -> Dict[str, Any]:
    """Persist a fact about the user with status='proposed'.

    The user has to confirm the fact in the memory panel before it
    becomes retrievable via ``recall_about_user`` or gets injected into
    Fin's system prompt. After persistence we kick off a background
    embed pass so semantic recall works the moment the user confirms.
    """
    row = user_facts_repo.create_fact(
        fact=args.fact.strip(),
        category=args.category,
        tags=list(args.tags or [])[:5],
        sensitive=args.sensitive,
        status="proposed",
    )
    # Best-effort embed in the same request (small payload); avoids the
    # extra background-task hop and keeps the recall test deterministic.
    try:
        await embed_pending_user_facts(limit=10)
    except Exception:
        pass
    return {
        "fact_id": row["id"],
        "status": row["status"],
        "category": row["category"],
        "fact": row["fact"],
        "note": (
            "Saved as 'proposed'. The user has to confirm it in the memory "
            "panel before you can recall it next time."
        ),
    }


async def _search_documents(args: SearchDocumentsArgs) -> Dict[str, Any]:
    """Semantic search over Knowledge-base documents.

    Wraps ``documents_repo.retrieve_similar_docs`` so Fin can pull excerpts
    from user-uploaded references (IRS pubs, tax returns, statements) on
    demand instead of every turn.
    """
    vec = await embed_text(args.query)
    if vec is None:
        return {
            "query": args.query, "count": 0, "results": [],
            "note": "Ollama embeddings unavailable; document search degraded.",
        }
    hits = documents_repo.retrieve_similar_docs(
        vec, scope=args.scope, category=args.category, k=args.limit,
    )
    return {
        "query": args.query,
        "count": len(hits),
        "results": [
            {
                "title": h["title"],
                "scope": h["scope"],
                "category": h["category"],
                "chunk_index": h["chunk_index"],
                "excerpt": (h.get("content") or "")[:600],
                "distance": h["distance"],
            }
            for h in hits
        ],
    }


async def _recall_about_user(args: RecallAboutUserArgs) -> Dict[str, Any]:
    """Semantic search over CONFIRMED user facts only."""
    hits = await retrieve_similar_facts(
        query=args.query,
        status="confirmed",
        category=args.category,
        k=args.limit,
    )
    return {
        "query": args.query,
        "count": len(hits),
        "facts": [
            {
                "fact": h["fact"],
                "category": h["category"],
                "tags": h["tags"],
                "confidence": h["confidence"],
                "sensitive": h["sensitive"],
            }
            for h in hits
        ],
    }


def default_tool_registry(
    *, current_conversation_id: Optional[str] = None,
) -> ToolRegistry:
    """Build the registry. ``current_conversation_id`` is closed over by
    ``recall_past_conversation`` so trivial self-matches in the current
    chat are excluded from results.
    """

    async def _recall_past_conversation(args: RecallPastConversationArgs) -> Dict[str, Any]:
        hits = await retrieve_similar(
            query=args.query,
            exclude_conv_id=current_conversation_id,
            k=args.limit,
        )
        return {
            "query": args.query,
            "count": len(hits),
            "turns": [
                {
                    "conversation_id": h["conversation_id"],
                    "role": h["role"],
                    "content": (h.get("content") or "")[:400],
                    "distance": h["distance"],
                }
                for h in hits
            ],
        }

    tools = [
        Tool(
            name="think",
            description=(
                "Scratchpad for planning. For multi-step questions, call this "
                "FIRST with a short numbered plan (which tools, in what order, "
                "what you'll compare). The user never sees it; it just keeps "
                "your next steps on track. Not for simple lookups."
            ),
            args_model=ThinkArgs,
            handler=_think,
        ),
        Tool(
            name="search_transactions",
            description=(
                "Search the user's transaction history by free-text query. "
                "Use when the user references a specific charge ('that $300 hit', "
                "'the Amazon thing'), or when you need to ground an answer in "
                "concrete past transactions. Optional category and date filters."
            ),
            args_model=SearchTransactionsArgs,
            handler=_search_transactions,
        ),
        Tool(
            name="get_balance",
            description=(
                "Return current balances: net worth, cash, credit-card debt, "
                "investments. Use account_type='cash' for spendable money, "
                "'credit' for total card debt, 'investment' for brokerage value, "
                "or 'all' for the full picture."
            ),
            args_model=GetBalanceArgs,
            handler=_get_balance,
        ),
        Tool(
            name="list_accounts",
            description=(
                "List the user's individual accounts with NAME, institution, "
                "bucket (cash/credit/investment), subtype, and balance. THE "
                "tool for 'what accounts do I have', 'details about my "
                "checking accounts', or any question naming a specific "
                "account. Never invent account names or per-account balances "
                "— call this. get_balance only returns totals."
            ),
            args_model=ListAccountsArgs,
            handler=_list_accounts,
        ),
        Tool(
            name="get_debt",
            description=(
                "Return credit-card / debt accounts with balances, APR, minimum "
                "payment, credit limit, and due day when configured. Filter by "
                "account_name substring (e.g. 'chase', 'amex') or omit for all."
            ),
            args_model=GetDebtArgs,
            handler=_get_debt,
        ),
        Tool(
            name="get_budget_status",
            description=(
                "Return budget vs. actual spending for the current month, "
                "including over_budget flags and percent used. Optional "
                "category filter (e.g. 'Dining')."
            ),
            args_model=GetBudgetStatusArgs,
            handler=_get_budget_status,
        ),
        Tool(
            name="get_goal_status",
            description=(
                "Return savings-goal progress: target, current, monthly required, "
                "pace status (ahead/on_pace/behind/stalled). Optional goal_id."
            ),
            args_model=GetGoalStatusArgs,
            handler=_get_goal_status,
        ),
        Tool(
            name="get_category_spending",
            description=(
                "Aggregate activity for one category over a date range. "
                "Returns count, outflow (debits), inflow (credits), "
                "net_outflow, average, and monthly breakdown. "
                "Use for any roll-up question: 'average X', 'how much did "
                "I spend on Y', 'how much did I save this year', 'total Z "
                "last month'. Do NOT use search_transactions for these. "
                "For spending categories (Dining, Drinks, …) inflow is ~0 "
                "and `outflow` IS the total spend. For transfer-tagged "
                "categories like Savings, use `net_outflow` for 'how much "
                "did I actually put in' — that's outflow minus inflow. "
                "Pass start_date and end_date as ISO YYYY-MM-DD; omit "
                "either side for an open-ended range."
            ),
            args_model=GetCategorySpendingArgs,
            handler=_get_category_spending,
        ),
        Tool(
            name="get_investments",
            description=(
                "Return investment portfolio detail: per-holding rows "
                "(symbol, account, asset_type, quantity, market_value, "
                "cost_basis, unrealized_gain, gain_pct), totals, allocation "
                "by asset_type, and concentration ranking (top positions "
                "by value). Use whenever the user asks about stocks, ETFs, "
                "crypto, portfolio, allocation, holdings, or specific "
                "tickers. Filter by `symbol` for one position or "
                "`asset_type` to slice the portfolio. Returns "
                "available=false when no SnapTrade-synced holdings exist."
            ),
            args_model=GetInvestmentsArgs,
            handler=_get_investments,
        ),
        Tool(
            name="project_cashflow",
            description=(
                "Project net cashflow over the next horizon_days (1-180). "
                "Returns expected income, recurring outflow, expected inbound "
                "transfers, typical discretionary spending, net, and a list of "
                "upcoming projected bills. net already subtracts both the bills "
                "and the discretionary baseline (median of the last three "
                "complete months of non-recurring spend), so it is what the "
                "household would actually have left. "
                "discretionary_basis.confidence is high/low/none; when it is "
                "none the discretionary figure is omitted and "
                "projection_incomplete is true — say so rather than quoting the "
                "net as the whole picture."
            ),
            args_model=ProjectCashflowArgs,
            handler=_project_cashflow,
        ),
        Tool(
            name="search_documents",
            description=(
                "Semantic search over the user's Knowledge-base documents "
                "(uploaded IRS pubs, tax returns, statements, reference "
                "material). Use whenever the user references a rule, "
                "contribution limit, formula, or asks 'what does the IRS "
                "say about X', 'per my tax return…', 'based on my statement…'. "
                "Cite the title of any document you use. Returns excerpts "
                "with title + chunk_index for citation."
            ),
            args_model=SearchDocumentsArgs,
            handler=_search_documents,
        ),
        Tool(
            name="recall_past_conversation",
            description=(
                "Semantic search over past chat turns (excluding the current "
                "conversation). Use when the user references something they "
                "discussed before ('like we talked about', 'last time we "
                "discussed retirement', 'what did you say about my budget?'). "
                "Returns matching user + assistant turns from other "
                "conversations with conversation_id for context."
            ),
            args_model=RecallPastConversationArgs,
            handler=_recall_past_conversation,
        ),
        Tool(
            name="remember_about_user",
            description=(
                "Save a fact about the user (preference, constraint, goal, "
                "life_event, or pattern). The fact lands as 'proposed' and "
                "the user must confirm it in the memory panel before you "
                "can recall it. Use SPARINGLY — only for durable, "
                "non-obvious facts ('I won't tap my 401k', 'aiming for FI "
                "by 45', 'Friday dinners are budgeted as social'). Do NOT "
                "save trivia or transient context."
            ),
            args_model=RememberAboutUserArgs,
            handler=_remember_about_user,
        ),
        Tool(
            name="recall_about_user",
            description=(
                "Semantic search over CONFIRMED facts the user has approved "
                "Fin to remember. Use when the user references something "
                "personal you might already know ('what did I say about "
                "retirement?'), or to check before giving advice that hinges "
                "on the user's stated preferences or constraints. Returns "
                "an empty list when nothing is confirmed yet."
            ),
            args_model=RecallAboutUserArgs,
            handler=_recall_about_user,
        ),
    ]

    from agent.action_tools import build_action_tools

    tools += build_action_tools()

    if config.ADVISOR_WEB_TOOLS_ENABLED:
        from agent.market_tools import build_market_tools
        from agent.web_tools import build_web_tools

        tools += build_web_tools() + build_market_tools()

    return ToolRegistry(tools)
