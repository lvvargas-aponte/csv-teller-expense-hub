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

import state
from analytics import (
    _balances_snapshot,
    _debts_from_accounts,
    _investments_snapshot,
    category_spending_summary,
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
    GetBalanceArgs,
    GetBudgetStatusArgs,
    GetCategorySpendingArgs,
    GetDebtArgs,
    GetGoalStatusArgs,
    GetInvestmentsArgs,
    GetNextActionsArgs,
    GetPropertiesArgs,
    GetSafeToSpendArgs,
    GetUsableEquityArgs,
    ProjectCashflowArgs,
    ProjectRetirementArgs,
    RecallAboutUserArgs,
    RecallPastConversationArgs,
    RememberAboutUserArgs,
    SearchDocumentsArgs,
    SearchTransactionsArgs,
)

# How many projection rows a retirement answer carries into the model's
# context. Fifty years of rows is thousands of tokens of arithmetic the
# model will not read carefully and may well misquote; five evenly spaced
# ones plus the retirement year is enough to describe the shape.
_RETIREMENT_SAMPLE_ROWS = 5


Handler = Callable[[BaseModel], Awaitable[Any]]


@dataclass
class Tool:
    name: str
    description: str
    args_model: Type[BaseModel]
    handler: Handler


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


async def _get_safe_to_spend(args: GetSafeToSpendArgs) -> Dict[str, Any]:
    """Today's allowance and everything that produced it.

    Returns the full payload — commitments, pace, excluded categories — so
    Fin can explain *why* the number is what it is rather than just reciting
    it. That explanation is the whole value of asking a chat instead of
    reading the Today page.
    """
    from datetime import date as _date
    from analytics import compute_safe_to_spend

    as_of = None
    if args.as_of:
        try:
            as_of = _date.fromisoformat(args.as_of[:10])
        except ValueError:
            as_of = None
    return compute_safe_to_spend(as_of=as_of)


async def _get_properties(args: GetPropertiesArgs) -> Dict[str, Any]:
    """Rental portfolio economics: NOI, cash flow, DSCR, equity, performance."""
    import properties as properties_domain

    if args.property_id:
        econ = properties_domain.compute_property_economics(args.property_id)
        if econ is None:
            return {
                "available": False,
                "note": f"No property with id {args.property_id}.",
            }
        return {"available": True, "property": econ}

    portfolio = properties_domain.compute_portfolio()
    if not portfolio.get("count"):
        return {
            "available": False,
            "note": (
                "No properties on file. The user tracks rentals under the "
                "Properties tab; suggest adding one if the question needs it."
            ),
            "properties": [],
        }
    return {"available": True, **portfolio}


async def _get_usable_equity(args: GetUsableEquityArgs) -> Dict[str, Any]:
    """Borrowing capacity — always paired with what the borrowing would cost.

    Both scenarios carry the new payment, the delta, and the cash flow that
    survives it. Never quote the extractable amount on its own.
    """
    import properties as properties_domain

    kwargs: Dict[str, Any] = {}
    if args.max_ltv_pct is not None:
        kwargs["max_ltv_pct"] = args.max_ltv_pct
    if args.max_cltv_pct is not None:
        kwargs["max_cltv_pct"] = args.max_cltv_pct

    if args.property_id:
        return properties_domain.compute_usable_equity(args.property_id, **kwargs)

    portfolio = properties_domain.compute_portfolio_equity(**kwargs)
    # Drop the per-property detail; the totals plus anything blocked is what
    # a conversational answer needs.
    return {
        "count": portfolio["count"],
        "total_equity": portfolio["total_equity"],
        "total_cash_out_available": portfolio["total_cash_out_available"],
        "total_heloc_available": portfolio["total_heloc_available"],
        "needs_valuation": portfolio["needs_valuation"],
        "note": (
            "Extractable amounts are gross of their carrying cost. Call this "
            "with a property_id for the payment increase and post-borrow cash "
            "flow before recommending anything."
        ),
    }


async def _project_retirement(args: ProjectRetirementArgs) -> Dict[str, Any]:
    """When the rentals and the portfolio can carry the household.

    Sampled, not dumped: the retirement year plus a handful of evenly spaced
    rows. The mortgage-payoff milestones are included because they are the
    mechanic the whole plan rests on.
    """
    import retirement as retirement_domain

    inputs = retirement_domain.build_retirement_inputs()
    overrides = {
        k: v for k, v in args.model_dump().items() if v is not None
    }
    if overrides:
        inputs.assumptions = {**inputs.assumptions, **overrides}

    projection = retirement_domain.project_retirement(inputs)
    rows = projection["rows"]
    step = max(1, len(rows) // _RETIREMENT_SAMPLE_ROWS)
    sampled = rows[::step][:_RETIREMENT_SAMPLE_ROWS]

    return {
        "model": projection["model"],
        "monte_carlo": projection["monte_carlo"],
        "feasible": projection["feasible"],
        "earliest_retirement_year": projection["earliest_retirement_year"],
        "earliest_retirement_age": projection["earliest_retirement_age"],
        "years_away": projection["years_away"],
        "at_retirement": projection["at_retirement"],
        "required_monthly_contribution": projection.get("required_monthly_contribution"),
        "mortgage_payoff_milestones": projection["milestones"],
        "sampled_rows": sampled,
        "assumptions_used": projection["assumptions"],
        "warnings": projection["warnings"],
        "sensitivity": retirement_domain.build_sensitivity(inputs),
        "note": (
            "Deterministic, not a simulation. The sensitivity rows are the "
            "honest substitute for a probability figure — quote them alongside "
            "any retirement year."
        ),
    }


async def _get_next_actions(args: GetNextActionsArgs) -> Dict[str, Any]:
    """The Today page's ranked action list, verbatim.

    Same rules, same ranking, same numbers — so "what should I do?" in chat
    and "what should I do?" on the Today page cannot disagree. That
    consistency is worth more than a cleverer chat-specific answer.
    """
    import coach

    result = coach.build_actions(limit=args.limit)
    return {
        "generated_at": result["generated_at"],
        "count": len(result["actions"]),
        "total_available": result["total"],
        "actions": [
            {
                "rank": a["rank"],
                "urgency": a["urgency"],
                "kind": a["kind"],
                "title": a["title"],
                "detail": a["detail"],
                "amount": a["amount"],
                "impact": a["impact"],
                "due_date": a["due_date"],
                "why": a["why"],
            }
            for a in result["actions"]
        ],
        "note": (
            "These are rule-derived and already quantified. Use their figures "
            "as given — do not recompute or round them."
        ),
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

    return ToolRegistry([
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
                "transfers, net, and a list of upcoming projected bills."
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
        Tool(
            name="get_safe_to_spend",
            description=(
                "Return today's spending allowance and the whole envelope "
                "behind it: income, fixed bills, debt minimums, required goal "
                "contributions, spend so far this month, days remaining, and "
                "pace. Use for 'can I afford X', 'how much can I spend "
                "today/this week', 'am I over budget'. Returns "
                "available=false when no income has been detected — say so "
                "rather than estimating."
            ),
            args_model=GetSafeToSpendArgs,
            handler=_get_safe_to_spend,
        ),
        Tool(
            name="get_properties",
            description=(
                "Return rental-property economics: NOI, operating expenses, "
                "debt service, monthly cash flow, cap rate, cash-on-cash, "
                "DSCR, equity, LTV, and a performance rating with quantified "
                "reasons. Omit property_id for portfolio totals. Use for any "
                "question about rentals, tenants, landlording, or whether a "
                "property is worth keeping. NEVER recommend selling — surface "
                "the reasons and let the user decide."
            ),
            args_model=GetPropertiesArgs,
            handler=_get_properties,
        ),
        Tool(
            name="get_usable_equity",
            description=(
                "Return how much could be borrowed against property equity — "
                "cash-out refinance and HELOC — together with the new payment, "
                "the payment increase, the DSCR that survives it, and the "
                "resulting cash flow. Use for 'can I pull money out', 'how do "
                "I fund the next property', 'should I refinance'. ALWAYS quote "
                "the payment increase alongside the amount; the extractable "
                "figure on its own is the most misleading number in real "
                "estate."
            ),
            args_model=GetUsableEquityArgs,
            handler=_get_usable_equity,
        ),
        Tool(
            name="project_retirement",
            description=(
                "Project when the household can retire and on what. Returns "
                "the earliest sustainable year, the income mix at that point "
                "(rental net, portfolio withdrawals, Social Security), the "
                "years each mortgage is paid off, sensitivity rows, and a few "
                "sampled projection years. Pass any argument to run a what-if "
                "without saving it. Deterministic — there is no probability "
                "figure, so quote the sensitivity rows instead of implying "
                "one."
            ),
            args_model=ProjectRetirementArgs,
            handler=_project_retirement,
        ),
        Tool(
            name="get_next_actions",
            description=(
                "Return the ranked, dollar-quantified next actions from the "
                "Today page — the same rules, ranking and figures the UI "
                "shows. Use for open-ended 'what should I do', 'what should I "
                "focus on', 'what am I missing'. Quote the amounts exactly as "
                "returned; they are rule-derived, and recomputing them makes "
                "chat disagree with the app."
            ),
            args_model=GetNextActionsArgs,
            handler=_get_next_actions,
        ),
    ])
