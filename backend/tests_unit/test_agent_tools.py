"""Unit tests for each Fin agent tool handler.

Exercises the handlers directly (no LLM, no harness) against seeded
``state.*`` dicts. Confirms each tool returns the shape the harness
will feed back to the model and that filter/edge-case logic is right.
"""
import asyncio
from datetime import date, timedelta
from typing import Any, Dict
from unittest.mock import AsyncMock, patch

import pytest

import state
from agent.schemas import (
    GetBalanceArgs,
    GetBudgetStatusArgs,
    GetCategorySpendingArgs,
    GetDebtArgs,
    GetGoalStatusArgs,
    GetInvestmentsArgs,
    ProjectCashflowArgs,
    SearchDocumentsArgs,
    SearchTransactionsArgs,
)
from agent.tools import (
    _get_balance,
    _list_accounts,
    _get_budget_status,
    _get_category_spending,
    _get_debt,
    _get_goal_status,
    _get_investments,
    _project_cashflow,
    _search_documents,
    _search_transactions,
    default_tool_registry,
)


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# search_transactions — wraps retrieve_similar_transactions + filters
# ---------------------------------------------------------------------------

class TestSearchTransactions:
    def _hits(self, *items: Dict[str, Any]):
        return AsyncMock(return_value=list(items))

    def test_returns_shape_and_count(self):
        fake = self._hits(
            {"date": "2026-05-10", "description": "AMAZON", "amount": 42.50, "category": "Shopping"},
            {"date": "2026-05-12", "description": "STARBUCKS", "amount": 5.25, "category": "Dining"},
        )
        with patch("agent.tools.retrieve_similar_transactions", new=fake):
            out = _run(_search_transactions(SearchTransactionsArgs(query="recent stuff")))
        assert out["query"] == "recent stuff"
        assert out["count"] == 2
        assert {t["description"] for t in out["transactions"]} == {"AMAZON", "STARBUCKS"}
        # Ensure the handler forwarded args.limit (default 5) to the embedding call.
        fake.assert_awaited_once_with("recent stuff", k=5)

    def test_category_filter_is_case_insensitive(self):
        fake = self._hits(
            {"date": "2026-05-10", "description": "AMAZON", "amount": 42.50, "category": "Shopping"},
            {"date": "2026-05-12", "description": "STARBUCKS", "amount": 5.25, "category": "Dining"},
        )
        with patch("agent.tools.retrieve_similar_transactions", new=fake):
            out = _run(_search_transactions(
                SearchTransactionsArgs(query="x", category="dining")
            ))
        assert out["count"] == 1
        assert out["transactions"][0]["description"] == "STARBUCKS"

    def test_date_range_filter(self):
        fake = self._hits(
            {"date": "2026-04-30", "description": "OLD", "amount": 10.0, "category": "X"},
            {"date": "2026-05-15", "description": "MID", "amount": 20.0, "category": "X"},
            {"date": "2026-06-02", "description": "NEW", "amount": 30.0, "category": "X"},
        )
        with patch("agent.tools.retrieve_similar_transactions", new=fake):
            out = _run(_search_transactions(SearchTransactionsArgs(
                query="x", start_date="2026-05-01", end_date="2026-05-31",
            )))
        assert out["count"] == 1
        assert out["transactions"][0]["description"] == "MID"

    def test_missing_category_defaults_to_uncategorized(self):
        fake = self._hits({"date": "2026-05-10", "description": "X", "amount": 1.0, "category": None})
        with patch("agent.tools.retrieve_similar_transactions", new=fake):
            out = _run(_search_transactions(SearchTransactionsArgs(query="x")))
        assert out["transactions"][0]["category"] == "Uncategorized"

    def test_empty_hits_returns_zero(self):
        fake = self._hits()
        with patch("agent.tools.retrieve_similar_transactions", new=fake):
            out = _run(_search_transactions(SearchTransactionsArgs(query="nope")))
        assert out == {"query": "nope", "count": 0, "transactions": []}


# ---------------------------------------------------------------------------
# get_balance — read straight off _balances_snapshot
# ---------------------------------------------------------------------------

def _seed_cash(amount: float, acct_id: str = "acc_cash") -> None:
    state._balances_cache["simplefin_accounts"] = [
        {"id": acct_id, "institution": "Ally", "name": "Checking",
         "type": "depository", "subtype": "checking",
         "available": amount, "ledger": amount}
    ]


def _seed_credit(amount: float, acct_id: str = "acc_card") -> None:
    state._balances_cache["simplefin_accounts"] = (
        state._balances_cache.get("simplefin_accounts") or []
    ) + [
        {"id": acct_id, "institution": "Chase", "name": "Sapphire",
         "type": "credit", "subtype": "credit_card",
         "available": 0.0, "ledger": amount}
    ]


class TestGetBalance:
    def test_all_returns_full_snapshot(self):
        _seed_cash(1500.0)
        _seed_credit(420.0)
        out = _run(_get_balance(GetBalanceArgs(account_type="all")))
        assert set(out) == {"net_worth", "total_cash", "total_credit_debt", "total_investments"}
        assert out["total_cash"] == 1500.0
        assert out["total_credit_debt"] == 420.0
        assert out["net_worth"] == round(1500.0 - 420.0, 2)

    def test_cash_only(self):
        _seed_cash(800.0)
        out = _run(_get_balance(GetBalanceArgs(account_type="cash")))
        assert out == {"total_cash": 800.0}

    def test_credit_only(self):
        _seed_credit(250.0)
        out = _run(_get_balance(GetBalanceArgs(account_type="credit")))
        assert out == {"total_credit_debt": 250.0}

    def test_investment_only(self):
        state._balances_cache["snaptrade_accounts"] = [
            {"id": "acc_inv", "institution": "Robinhood", "name": "RH",
             "type": "investment", "subtype": "brokerage",
             "available": 12500.0, "ledger": 12500.0}
        ]
        out = _run(_get_balance(GetBalanceArgs(account_type="investment")))
        assert out == {"total_investments": 12500.0}

    def test_no_accounts_returns_zeros(self):
        out = _run(_get_balance(GetBalanceArgs(account_type="all")))
        assert out["total_cash"] == 0.0
        assert out["total_credit_debt"] == 0.0
        assert out["net_worth"] == 0.0


class TestListAccounts:
    def _seed(self):
        state._balances_cache["simplefin_accounts"] = [
            {"id": "acc_ally", "institution": "Ally", "name": "Interest Checking",
             "type": "depository", "subtype": "checking",
             "available": 25300.46, "ledger": 25300.46},
            {"id": "acc_chase", "institution": "Chase", "name": "Sapphire",
             "type": "credit", "subtype": "credit_card",
             "available": 0.0, "ledger": 1200.0},
        ]
        state._manual_accounts["m1"] = {
            "id": "m1", "institution": "Fidelity", "name": "Brokerage",
            "type": "investment", "subtype": "brokerage",
            "available": 5000.0, "ledger": 5000.0,
        }

    def test_lists_names_across_sources(self):
        self._seed()
        from agent.schemas import ListAccountsArgs
        out = _run(_list_accounts(ListAccountsArgs()))
        assert out["count"] == 3
        names = {a["name"] for a in out["accounts"]}
        assert names == {"Interest Checking", "Sapphire", "Brokerage"}
        checking = next(a for a in out["accounts"] if a["name"] == "Interest Checking")
        assert checking["bucket"] == "cash"
        assert checking["institution"] == "Ally"
        assert checking["balance"] == 25300.46
        manual = next(a for a in out["accounts"] if a["name"] == "Brokerage")
        assert manual["source"] == "manual"

    def test_bucket_filter(self):
        self._seed()
        from agent.schemas import ListAccountsArgs
        out = _run(_list_accounts(ListAccountsArgs(account_type="credit")))
        assert out["count"] == 1
        assert out["accounts"][0]["name"] == "Sapphire"
        assert out["accounts"][0]["balance"] == 1200.0

    def test_empty_cache(self):
        from agent.schemas import ListAccountsArgs
        out = _run(_list_accounts(ListAccountsArgs()))
        assert out == {"count": 0, "accounts": [], "as_of": None}


# ---------------------------------------------------------------------------
# get_debt — credit accounts + side-car details + substring filter
# ---------------------------------------------------------------------------

class TestGetDebt:
    def _seed(self):
        state._balances_cache["simplefin_accounts"] = [
            {"id": "acc_chase", "institution": "Chase", "name": "Sapphire",
             "type": "credit", "subtype": "credit_card",
             "available": 0.0, "ledger": 1200.0},
            {"id": "acc_amex", "institution": "Amex", "name": "Gold",
             "type": "credit", "subtype": "credit_card",
             "available": 0.0, "ledger": 800.0},
        ]
        state.account_details["acc_chase"] = {
            "apr": 24.99, "minimum_payment": 35.0,
            "credit_limit": 5000.0, "due_day": 15,
        }

    def test_all_debts_returned(self):
        self._seed()
        out = _run(_get_debt(GetDebtArgs()))
        assert out["count"] == 2
        assert out["total_balance"] == 2000.0
        # APR pulled from the side-car for Chase only
        chase = next(d for d in out["debts"] if d["name"] == "Sapphire")
        assert chase["apr"] == 24.99
        assert chase["minimum_payment"] == 35.0
        amex = next(d for d in out["debts"] if d["name"] == "Gold")
        assert "apr" not in amex

    def test_account_name_substring_filter(self):
        self._seed()
        out = _run(_get_debt(GetDebtArgs(account_name="chase")))
        assert out["count"] == 1
        assert out["debts"][0]["name"] == "Sapphire"
        assert out["total_balance"] == 1200.0

    def test_account_name_matches_institution(self):
        self._seed()
        out = _run(_get_debt(GetDebtArgs(account_name="amex")))
        assert out["count"] == 1
        assert out["debts"][0]["institution"] == "Amex"

    def test_no_match_returns_empty(self):
        self._seed()
        out = _run(_get_debt(GetDebtArgs(account_name="discover")))
        assert out == {"total_balance": 0.0, "count": 0, "debts": []}

    def test_no_credit_accounts(self):
        out = _run(_get_debt(GetDebtArgs()))
        assert out == {"total_balance": 0.0, "count": 0, "debts": []}


# ---------------------------------------------------------------------------
# get_budget_status — over/under/no-budget
# ---------------------------------------------------------------------------

def _seed_budget_with_spend(category: str, monthly_limit: float, spent: float) -> None:
    state.budgets[category] = {"category": category, "monthly_limit": monthly_limit}
    today = date.today().isoformat()
    txn_id = f"seed_{category}"
    state.stored_transactions[txn_id] = {
        "id": txn_id, "date": today,
        "description": f"{category} charge", "amount": spent,
        "category": category, "type": "debit", "is_shared": False,
    }


class TestGetBudgetStatus:
    def test_over_budget_flagged(self):
        _seed_budget_with_spend("Dining", 300.0, 420.0)
        out = _run(_get_budget_status(GetBudgetStatusArgs(category="Dining")))
        assert out["count"] == 1
        b = out["budgets"][0]
        assert b["over_budget"] is True
        assert b["current_month_spent"] == 420.0
        assert b["percent_used"] == 140.0

    def test_under_budget(self):
        _seed_budget_with_spend("Groceries", 500.0, 200.0)
        out = _run(_get_budget_status(GetBudgetStatusArgs(category="Groceries")))
        assert out["budgets"][0]["over_budget"] is False
        assert out["budgets"][0]["percent_used"] == 40.0

    def test_category_filter_is_case_insensitive(self):
        _seed_budget_with_spend("Dining", 300.0, 100.0)
        out = _run(_get_budget_status(GetBudgetStatusArgs(category="dining")))
        assert out["count"] == 1

    def test_all_budgets_when_no_filter(self):
        _seed_budget_with_spend("Dining", 300.0, 100.0)
        _seed_budget_with_spend("Groceries", 500.0, 200.0)
        out = _run(_get_budget_status(GetBudgetStatusArgs()))
        assert out["count"] == 2

    def test_no_budgets_returns_empty(self):
        out = _run(_get_budget_status(GetBudgetStatusArgs()))
        assert out == {"count": 0, "budgets": []}


# ---------------------------------------------------------------------------
# get_goal_status — relies on accounts_repo; in-memory variant is installed
# ---------------------------------------------------------------------------

class TestGetGoalStatus:
    def test_no_goals_returns_empty(self):
        out = _run(_get_goal_status(GetGoalStatusArgs()))
        assert out == {"count": 0, "goals": []}

    def test_single_goal_shape(self):
        state.goals["goal_emergency"] = {
            "id": "goal_emergency",
            "name": "Emergency Fund",
            "kind": "emergency_fund",
            "target_amount": 10000.0,
            "current_balance": 2500.0,
        }
        out = _run(_get_goal_status(GetGoalStatusArgs()))
        assert out["count"] == 1
        g = out["goals"][0]
        assert g["id"] == "goal_emergency"
        assert g["progress_pct"] == 25.0
        # No target_date -> monthly_required is None
        assert g["monthly_required"] is None

    def test_goal_id_filter(self):
        state.goals["goal_a"] = {"id": "goal_a", "name": "A", "kind": "savings",
                                  "target_amount": 1000.0, "current_balance": 100.0}
        state.goals["goal_b"] = {"id": "goal_b", "name": "B", "kind": "savings",
                                  "target_amount": 2000.0, "current_balance": 500.0}
        out = _run(_get_goal_status(GetGoalStatusArgs(goal_id="goal_b")))
        assert out["count"] == 1
        assert out["goals"][0]["id"] == "goal_b"

    def test_unknown_goal_id_returns_empty(self):
        state.goals["goal_a"] = {"id": "goal_a", "name": "A", "kind": "savings",
                                  "target_amount": 1000.0, "current_balance": 0.0}
        out = _run(_get_goal_status(GetGoalStatusArgs(goal_id="goal_nope")))
        assert out == {"count": 0, "goals": []}


# ---------------------------------------------------------------------------
# project_cashflow — horizon math + no-data short-circuit
# ---------------------------------------------------------------------------

class TestProjectCashflow:
    def test_no_data_returns_zeros(self):
        out = _run(_project_cashflow(ProjectCashflowArgs(horizon_days=30)))
        assert out["horizon_days"] == 30
        assert out["expected_income"] == 0.0
        assert out["expected_recurring_outflow"] == 0.0
        assert out["expected_inbound_transfers"] == 0.0
        assert out["net"] == 0.0
        assert out["upcoming_bills"] == []

    def test_horizon_scales_income(self):
        # Seed 6 monthly paychecks so compute_income_estimate returns "high"
        # confidence and ~3000/mo.
        today = date.today()
        for i in range(6):
            day = (today.replace(day=1) - timedelta(days=30 * i))
            txn_id = f"pay_{i}"
            state.stored_transactions[txn_id] = {
                "id": txn_id, "date": day.isoformat(),
                "description": "ACME PAYROLL DIRECT DEP",
                "amount": -3000.0,   # credit (income is negative in this app)
                "category": "Income", "type": "credit", "is_shared": False,
            }
        out_30 = _run(_project_cashflow(ProjectCashflowArgs(horizon_days=30)))
        out_60 = _run(_project_cashflow(ProjectCashflowArgs(horizon_days=60)))
        # 60-day horizon should project ~2x the 30-day income.
        if out_30["expected_income"] > 0:
            assert out_60["expected_income"] >= out_30["expected_income"] * 1.9

    def test_horizon_bounds_enforced_by_schema(self):
        # Pydantic should reject 0 / 200 before the handler runs.
        with pytest.raises(Exception):
            ProjectCashflowArgs(horizon_days=0)
        with pytest.raises(Exception):
            ProjectCashflowArgs(horizon_days=200)


# ---------------------------------------------------------------------------
# default_tool_registry sanity
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# get_category_spending — aggregation roll-up
# ---------------------------------------------------------------------------

def _seed_txn(txn_id: str, date_str: str, category: str, amount: float) -> None:
    state.stored_transactions[txn_id] = {
        "id": txn_id, "date": date_str,
        "description": f"{category} charge {txn_id}", "amount": amount,
        "category": category, "type": "debit", "is_shared": False,
    }


def _seed_savings_txn(txn_id: str, date_str: str, amount: float, direction: str, transfer_to: str = "manual_savings") -> None:
    """Seed a Savings transaction with transfer_to_account_id set (like the
    real SimpleFIN-tagged transfers to a manual account)."""
    state.stored_transactions[txn_id] = {
        "id": txn_id, "date": date_str,
        "description": f"SAVINGS XFER {txn_id}", "amount": amount,
        "category": "Savings", "transaction_type": direction,
        "source": "simplefin", "transfer_to_account_id": transfer_to,
        "is_shared": False,
    }


class TestGetCategorySpending:
    def test_aggregates_count_outflow_average_for_spending_category(self):
        _seed_txn("d1", "2026-03-04", "Drinks", 12.0)
        _seed_txn("d2", "2026-04-15", "Drinks", 18.0)
        _seed_txn("d3", "2026-05-20", "Drinks",  30.0)
        # Different category — should be ignored.
        _seed_txn("g1", "2026-04-10", "Groceries", 90.0)

        out = _run(_get_category_spending(GetCategorySpendingArgs(category="Drinks")))
        assert out["count"] == 3
        assert out["outflow"] == 60.0
        assert out["inflow"] == 0.0
        assert out["net_outflow"] == 60.0
        # `total` alias matches outflow for spending categories.
        assert out["total"] == 60.0
        assert out["average"] == 20.0
        assert set(out["by_month"]) == {"2026-03", "2026-04", "2026-05"}

    def test_savings_transfers_are_counted(self):
        """Regression: transfer-tagged rows (transfer_to_account_id set) were
        being dropped by the old _is_expense filter, so 'how much did I save'
        returned 0 even with real transfers in the DB."""
        _seed_savings_txn("s1", "2026-03-17", 1000.0, "debit")   # money to savings
        _seed_savings_txn("s2", "2026-03-24", 1000.0, "debit")
        _seed_savings_txn("s3", "2026-04-14", 1000.0, "debit")
        _seed_savings_txn("s4", "2026-05-05", 1000.0, "debit")
        _seed_savings_txn("s5", "2026-01-06", 2000.0, "credit")  # money back from savings

        out = _run(_get_category_spending(GetCategorySpendingArgs(category="Savings")))
        assert out["count"] == 5
        assert out["outflow"] == 4000.0
        assert out["inflow"] == 2000.0
        assert out["net_outflow"] == 2000.0

    def test_category_match_is_case_insensitive(self):
        _seed_txn("d1", "2026-03-04", "Drinks", 12.0)
        out = _run(_get_category_spending(GetCategorySpendingArgs(category="drinks")))
        assert out["count"] == 1

    def test_date_bounds_inclusive(self):
        _seed_txn("d_early", "2025-12-31", "Drinks", 10.0)
        _seed_txn("d_in",    "2026-01-01", "Drinks", 20.0)
        _seed_txn("d_late",  "2027-01-01", "Drinks", 99.0)

        out = _run(_get_category_spending(GetCategorySpendingArgs(
            category="Drinks",
            start_date="2026-01-01",
            end_date="2026-12-31",
        )))
        assert out["count"] == 1
        assert out["outflow"] == 20.0
        assert out["start_date"] == "2026-01-01"
        assert out["end_date"] == "2026-12-31"

    def test_no_match_returns_zero_aggregates(self):
        _seed_txn("d1", "2026-03-04", "Drinks", 12.0)
        out = _run(_get_category_spending(GetCategorySpendingArgs(category="Yachting")))
        assert out["count"] == 0
        assert out["outflow"] == 0.0
        assert out["inflow"] == 0.0
        assert out["net_outflow"] == 0.0
        assert out["total"] == 0.0

    def test_empty_category_short_circuits(self):
        out = _run(_get_category_spending(GetCategorySpendingArgs(category="   ")))
        assert out["count"] == 0
        assert out["outflow"] == 0.0


class TestGetInvestments:
    """Patches ``agent.tools._investments_snapshot`` since the in-memory
    accounts repo doesn't have holdings during unit tests."""

    def test_no_snapshot_returns_unavailable(self):
        with patch("agent.tools._investments_snapshot", return_value=None):
            out = _run(_get_investments(GetInvestmentsArgs()))
        assert out["available"] is False
        assert "SnapTrade" in out["note"]
        assert out["holdings"] == []

    def test_full_portfolio_round_trip(self):
        fake_snap = {
            "total_value": 12500.0, "total_cost": 10000.0,
            "total_gain": 2500.0, "total_gain_pct": 25.0,
            "holding_count": 2,
            "allocation": [{"asset_type": "etf", "value": 12500.0, "pct": 100.0}],
            "concentration": [{"symbol": "VTI", "value": 10000.0, "pct": 80.0}],
            "largest_position_pct": 80.0,
            "concentrated": True,
            "holdings": [
                {"symbol": "VTI", "asset_type": "etf", "quantity": 50, "market_value": 10000.0},
                {"symbol": "BTC", "asset_type": "crypto", "quantity": 0.04, "market_value": 2500.0},
            ],
        }
        with patch("agent.tools._investments_snapshot", return_value=fake_snap):
            out = _run(_get_investments(GetInvestmentsArgs()))
        assert out["available"] is True
        assert out["total_value"] == 12500.0
        assert out["concentrated"] is True
        assert len(out["holdings"]) == 2

    def test_symbol_filter_case_insensitive(self):
        fake_snap = {
            "total_value": 12500.0, "total_cost": 10000.0, "total_gain": 2500.0,
            "total_gain_pct": 25.0, "holding_count": 2,
            "allocation": [], "concentration": [],
            "largest_position_pct": 0.0, "concentrated": False,
            "holdings": [
                {"symbol": "VTI", "asset_type": "etf", "quantity": 50, "market_value": 10000.0},
                {"symbol": "BTC", "asset_type": "crypto", "quantity": 0.04, "market_value": 2500.0},
            ],
        }
        with patch("agent.tools._investments_snapshot", return_value=fake_snap):
            out = _run(_get_investments(GetInvestmentsArgs(symbol="vti")))
        assert len(out["holdings"]) == 1
        assert out["holdings"][0]["symbol"] == "VTI"
        assert out["symbol_filter"] == "vti"

    def test_asset_type_filter(self):
        fake_snap = {
            "total_value": 12500.0, "total_cost": 10000.0, "total_gain": 2500.0,
            "total_gain_pct": 25.0, "holding_count": 2,
            "allocation": [], "concentration": [],
            "largest_position_pct": 0.0, "concentrated": False,
            "holdings": [
                {"symbol": "VTI", "asset_type": "etf", "quantity": 50, "market_value": 10000.0},
                {"symbol": "BTC", "asset_type": "crypto", "quantity": 0.04, "market_value": 2500.0},
            ],
        }
        with patch("agent.tools._investments_snapshot", return_value=fake_snap):
            out = _run(_get_investments(GetInvestmentsArgs(asset_type="crypto")))
        assert len(out["holdings"]) == 1
        assert out["holdings"][0]["symbol"] == "BTC"


class TestSearchDocuments:
    """Patches the embedding + repo call so the handler can be exercised
    without a live Ollama instance or seeded documents."""

    def test_no_embedding_returns_empty(self):
        async_none = AsyncMock(return_value=None)
        with patch("agent.tools.embed_text", new=async_none), \
             patch("agent.tools.documents_repo.retrieve_similar_docs") as repo:
            out = _run(_search_documents(SearchDocumentsArgs(query="roth limit")))
        assert out["count"] == 0
        assert out["results"] == []
        assert "unavailable" in out["note"]
        repo.assert_not_called()

    def test_returns_excerpts_with_title(self):
        vec = [0.1] * 768
        fake_hits = [
            {
                "document_id": 1, "chunk_index": 0,
                "content": "Roth IRA annual contribution limit is $7,000 for 2026.",
                "title": "IRS Pub 590-A",
                "scope": "external", "category": "tax",
                "distance": 0.12,
            },
        ]
        with patch("agent.tools.embed_text", new=AsyncMock(return_value=vec)), \
             patch("agent.tools.documents_repo.retrieve_similar_docs",
                   return_value=fake_hits) as repo:
            out = _run(_search_documents(SearchDocumentsArgs(
                query="roth limit", scope="external", category="tax", limit=2,
            )))
        assert out["count"] == 1
        assert out["results"][0]["title"] == "IRS Pub 590-A"
        assert "$7,000" in out["results"][0]["excerpt"]
        repo.assert_called_once()
        kwargs = repo.call_args.kwargs
        assert kwargs == {"scope": "external", "category": "tax", "k": 2}


class TestRecallPastConversation:
    def test_uses_conversation_id_for_exclude(self):
        fake_hits = [
            {"conversation_id": "conv_old", "role": "assistant",
             "content": "We talked about Roth IRA last time.",
             "distance": 0.15},
        ]
        async_fn = AsyncMock(return_value=fake_hits)
        with patch("agent.tools.retrieve_similar", new=async_fn):
            reg = default_tool_registry(current_conversation_id="conv_current")
            tool = reg.get("recall_past_conversation")
            assert tool is not None
            out = _run(tool.handler(tool.args_model(query="roth ira")))

        async_fn.assert_awaited_once()
        kwargs = async_fn.call_args.kwargs
        assert kwargs["exclude_conv_id"] == "conv_current"
        assert kwargs["k"] == 5  # default limit
        assert out["count"] == 1
        assert out["turns"][0]["conversation_id"] == "conv_old"

    def test_no_conversation_id_means_no_exclusion(self):
        async_fn = AsyncMock(return_value=[])
        with patch("agent.tools.retrieve_similar", new=async_fn):
            reg = default_tool_registry()
            tool = reg.get("recall_past_conversation")
            _run(tool.handler(tool.args_model(query="x")))
        assert async_fn.call_args.kwargs["exclude_conv_id"] is None


_CORE_TOOLS = {
    "think",
    "search_transactions", "get_balance", "get_debt", "list_accounts",
    "get_budget_status", "get_goal_status",
    "get_category_spending", "project_cashflow",
    "get_investments",
    "search_documents", "recall_past_conversation",
    "remember_about_user", "recall_about_user",
}

_ACTION_TOOLS = {
    "sync_transactions", "refresh_balances", "sync_investments",
    "schedule_sync", "list_scheduled_tasks", "cancel_scheduled_task",
}

_WEB_TOOLS = {
    "web_search", "fetch_webpage",
    "get_stock_quote", "get_stock_history", "get_stock_fundamentals",
}


class TestRegistry:
    def test_all_tools_present_with_web_enabled(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "ADVISOR_WEB_TOOLS_ENABLED", True)
        reg = default_tool_registry()
        assert set(reg.names()) == _CORE_TOOLS | _ACTION_TOOLS | _WEB_TOOLS

    def test_web_tools_absent_when_disabled(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "ADVISOR_WEB_TOOLS_ENABLED", False)
        reg = default_tool_registry()
        assert set(reg.names()) == _CORE_TOOLS | _ACTION_TOOLS

    def test_openai_tools_have_required_shape(self):
        reg = default_tool_registry()
        for t in reg.openai_tools():
            assert t["type"] == "function"
            fn = t["function"]
            assert "name" in fn and "description" in fn and "parameters" in fn
            params = fn["parameters"]
            assert params.get("type") == "object"
            assert "properties" in params
