"""Integration tests for the holdings repo + SnapTrade sync (real Postgres).

The SnapTrade *client* is mocked — these tests exercise the SQL path
(``holdings`` table, ``replace_holdings``, ``get_holdings``) and the sync
router end-to-end against the real ``financial_freedom_test`` database.
"""
from unittest.mock import AsyncMock, patch

import pytest

import state
from db.accounts_repo import get_repo


def _seed_account(repo, account_id="st_acc_1"):
    repo.upsert_synced_account(
        {
            "id": account_id,
            "name": "Robinhood Individual",
            "type": "investment",
            "subtype": "brokerage",
            "institution": {"name": "Robinhood"},
        },
        source="snaptrade",
    )


def _holding(symbol, asset_type, qty, avg, price, mv):
    return {
        "symbol": symbol,
        "description": f"{symbol} desc",
        "asset_type": asset_type,
        "quantity": qty,
        "average_purchase_price": avg,
        "last_price": price,
        "market_value": mv,
        "currency": "USD",
    }


class TestHoldingsRepo:
    def test_replace_and_get_holdings(self):
        repo = get_repo()
        _seed_account(repo)
        repo.replace_holdings("st_acc_1", [
            _holding("AAPL", "stock", 10, 150.0, 200.0, 2000.0),
            _holding("BTC", "crypto", 0.5, 30000.0, 40000.0, 20000.0),
        ])
        holdings = repo.get_holdings()
        assert len(holdings) == 2
        # Sorted by market_value DESC — BTC first.
        assert holdings[0]["symbol"] == "BTC"
        assert holdings[0]["account_name"] == "Robinhood Individual"
        assert holdings[0]["institution"] == "Robinhood"
        aapl = next(h for h in holdings if h["symbol"] == "AAPL")
        assert aapl["asset_type"] == "stock"
        assert aapl["quantity"] == 10.0
        assert aapl["market_value"] == 2000.0

    def test_replace_is_a_full_replace(self):
        repo = get_repo()
        _seed_account(repo)
        repo.replace_holdings("st_acc_1", [
            _holding("AAPL", "stock", 10, 150.0, 200.0, 2000.0),
            _holding("BTC", "crypto", 0.5, 30000.0, 40000.0, 20000.0),
        ])
        repo.replace_holdings("st_acc_1", [
            _holding("VTI", "etf", 5, 200.0, 220.0, 1100.0),
        ])
        holdings = repo.get_holdings_for_account("st_acc_1")
        assert [h["symbol"] for h in holdings] == ["VTI"]

    def test_replace_with_empty_clears_account(self):
        repo = get_repo()
        _seed_account(repo)
        repo.replace_holdings("st_acc_1", [_holding("AAPL", "stock", 1, 1.0, 2.0, 2.0)])
        repo.replace_holdings("st_acc_1", [])
        assert repo.get_holdings_for_account("st_acc_1") == []


# ---------------------------------------------------------------------------
# Sync endpoint — mocked SnapTrade client, real DB
# ---------------------------------------------------------------------------

class _FakeSnapTrade:
    def __init__(self):
        self.configured = True
        self.get_all_holdings = AsyncMock(return_value=[
            {
                "account": {"id": "st_acc_1", "name": "Robinhood Individual",
                            "institution": "Robinhood", "number": "x"},
                "holdings": [
                    {"symbol": "AAPL", "description": "Apple", "asset_type": "stock",
                     "quantity": 10.0, "average_purchase_price": 150.0,
                     "last_price": 200.0, "market_value": 2000.0, "currency": "USD"},
                ],
                "total_value": 2000.0,
                "currency": "USD",
            },
        ])


@pytest.fixture
def fake_snaptrade():
    fake = _FakeSnapTrade()
    with patch.object(state, "snaptrade", fake):
        yield fake


class TestSnapTradeSyncEndpoint:
    def test_sync_writes_holdings_and_snapshot(self, client, fake_snaptrade):
        state.snaptrade_creds["household"] = {"user_id": "u1", "user_secret": "s1"}
        resp = client.post("/api/snaptrade/sync")
        assert resp.status_code == 200, resp.text

        holdings = get_repo().get_holdings()
        assert len(holdings) == 1
        assert holdings[0]["symbol"] == "AAPL"

        # The synced account total flows into the balances summary.
        summary = client.get("/api/balances/summary").json()
        assert summary["total_investments"] == 2000.0

    def test_portfolio_endpoint_after_sync(self, client, fake_snaptrade):
        state.snaptrade_creds["household"] = {"user_id": "u1", "user_secret": "s1"}
        client.post("/api/snaptrade/sync")
        portfolio = client.get("/api/investments/portfolio").json()
        assert portfolio["total_value"] == 2000.0
        assert portfolio["total_gain"] == 500.0   # 2000 - 10*150


# ---------------------------------------------------------------------------
# User cost-basis overrides — the point is that they outlive a resync
# ---------------------------------------------------------------------------

class TestCostBasisOverrides:
    def _sync(self, repo, avg=None):
        repo.replace_holdings("st_acc_1", [
            _holding("VTI", "etf", 100, avg, 300.0, 30000.0),
        ])

    def test_user_cost_basis_survives_a_resync(self):
        from analytics import summarize_holdings

        repo = get_repo()
        _seed_account(repo)
        self._sync(repo)                      # provider sends no average cost
        repo.set_cost_override("st_acc_1", "VTI", 210.0)
        self._sync(repo)                      # provider still sends none

        row = summarize_holdings(repo.get_holdings())["holdings"][0]
        assert row["cost_basis"] == 21000.0
        assert row["unrealized_gain"] == 9000.0
        assert row["cost_basis_source"] == "user"

    def test_override_is_upserted_not_duplicated(self):
        repo = get_repo()
        _seed_account(repo)
        self._sync(repo)
        repo.set_cost_override("st_acc_1", "VTI", 210.0)
        repo.set_cost_override("st_acc_1", "VTI", 190.0)
        assert repo.get_cost_overrides() == {("st_acc_1", "VTI"): 190.0}

    def test_delete_restores_the_provider_value(self):
        from analytics import summarize_holdings

        repo = get_repo()
        _seed_account(repo)
        self._sync(repo, avg=100.0)
        repo.set_cost_override("st_acc_1", "VTI", 210.0)
        assert repo.delete_cost_override("st_acc_1", "VTI") == 1

        row = summarize_holdings(repo.get_holdings())["holdings"][0]
        assert row["cost_basis"] == 10000.0
        assert row["cost_basis_source"] == "provider"


class TestCostBasisEndpoints:
    def test_put_then_delete_round_trip(self, client):
        repo = get_repo()
        _seed_account(repo)
        repo.replace_holdings("st_acc_1", [_holding("VTI", "etf", 100, None, 300.0, 30000.0)])

        resp = client.put(
            "/api/investments/holdings/st_acc_1/VTI/cost-basis",
            json={"average_purchase_price": 210.0},
        )
        assert resp.status_code == 200, resp.text
        portfolio = client.get("/api/investments/portfolio").json()
        row = next(h for h in portfolio["holdings"] if h["symbol"] == "VTI")
        assert row["cost_basis"] == 21000.0
        assert row["cost_basis_source"] == "user"

        assert client.delete("/api/investments/holdings/st_acc_1/VTI/cost-basis").status_code == 200
        portfolio = client.get("/api/investments/portfolio").json()
        row = next(h for h in portfolio["holdings"] if h["symbol"] == "VTI")
        assert row["cost_basis"] is None
        assert row["cost_basis_source"] is None

    def test_a_non_positive_price_is_rejected(self, client):
        repo = get_repo()
        _seed_account(repo)
        repo.replace_holdings("st_acc_1", [_holding("VTI", "etf", 100, None, 300.0, 30000.0)])

        resp = client.put(
            "/api/investments/holdings/st_acc_1/VTI/cost-basis",
            json={"average_purchase_price": 0},
        )
        assert resp.status_code == 422
