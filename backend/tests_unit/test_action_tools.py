"""Unit tests for Fin's action tools — the underlying router coroutines
are mocked; no Teller/SnapTrade network calls."""
import asyncio
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from agent.action_tools import (
    _refresh_balances,
    _sync_investments,
    _sync_transactions,
    build_action_tools,
)
from agent.schemas import (
    RefreshBalancesArgs,
    SyncInvestmentsArgs,
    SyncTransactionsArgs,
)


def _run(coro):
    return asyncio.run(coro)


class TestSyncTransactions:
    def test_returns_counts_and_forwards_dates(self):
        fake = AsyncMock(return_value={
            "message": "ok", "from_date": "2026-07-01", "to_date": "2026-07-11",
            "total_fetched": 12, "total_new": 3,
            "details": [{"account": "Ally – Checking", "fetched": 12, "new": 3}],
        })
        with patch("routers.teller.sync_teller_transactions", new=fake):
            out = _run(_sync_transactions(
                SyncTransactionsArgs(from_date="2026-07-01", to_date="2026-07-11")
            ))
        assert out["synced"] is True
        assert out["total_new"] == 3
        assert out["account_errors"] == []
        req = fake.call_args.args[0]
        assert req.from_date == "2026-07-01"
        assert req.to_date == "2026-07-11"

    def test_no_tokens_returns_structured_note(self):
        fake = AsyncMock(side_effect=HTTPException(500, "No Teller access tokens configured."))
        with patch("routers.teller.sync_teller_transactions", new=fake):
            out = _run(_sync_transactions(SyncTransactionsArgs()))
        assert out["synced"] is False
        assert "Teller" in out["note"]

    def test_per_account_errors_surfaced(self):
        fake = AsyncMock(return_value={
            "message": "ok", "from_date": "a", "to_date": "b",
            "total_fetched": 0, "total_new": 0,
            "details": [{"account": "Chase – Card", "error": "enrollment expired",
                         "enrollment_status": "disconnected"}],
        })
        with patch("routers.teller.sync_teller_transactions", new=fake):
            out = _run(_sync_transactions(SyncTransactionsArgs()))
        assert out["synced"] is True
        assert out["account_errors"][0]["error"] == "enrollment expired"


class TestRefreshBalances:
    def test_returns_totals(self):
        from models import BalancesSummary
        fake = AsyncMock(return_value=BalancesSummary(
            net_worth=1000.0, total_cash=1500.0, total_credit_debt=500.0,
            total_investments=0.0, accounts=[],
        ))
        with patch("routers.balances.get_balances_summary", new=fake):
            out = _run(_refresh_balances(RefreshBalancesArgs()))
        assert out["refreshed"] is True
        assert out["net_worth"] == 1000.0
        assert out["account_count"] == 0
        fake.assert_awaited_once_with(force=True)


class TestSyncInvestments:
    def test_returns_account_details(self):
        fake = AsyncMock(return_value={
            "message": "ok", "accounts": 1,
            "details": [{"account": "Robinhood", "holdings": 4, "value": 12500.0}],
        })
        with patch("routers.snaptrade.sync_snaptrade", new=fake):
            out = _run(_sync_investments(SyncInvestmentsArgs()))
        assert out["synced"] is True
        assert out["details"][0]["holdings"] == 4

    def test_not_connected_returns_note(self):
        fake = AsyncMock(side_effect=HTTPException(409, "Connect a brokerage first."))
        with patch("routers.snaptrade.sync_snaptrade", new=fake):
            out = _run(_sync_investments(SyncInvestmentsArgs()))
        assert out["synced"] is False
        assert "brokerage" in out["note"]


class TestBuildActionTools:
    def test_six_tools(self):
        tools = build_action_tools()
        assert [t.name for t in tools] == [
            "sync_transactions", "refresh_balances", "sync_investments",
            "schedule_sync", "list_scheduled_tasks", "cancel_scheduled_task",
        ]
