"""SnapTrade integration + investments — unit tests (no Postgres, no SDK).

Covers the pure SnapTrade payload parsers, the ``summarize_holdings``
aggregation, the snaptrade/investments routers (with a mocked client), and
the advisor ``investments`` snapshot block.
"""
from unittest.mock import AsyncMock, patch

import pytest

import state
from analytics import _investments_snapshot, summarize_holdings
from db import accounts_repo_memory
from snaptrade import _asset_type, _normalize_account_holdings, _parse_position


# ---------------------------------------------------------------------------
# Pure parsing helpers
# ---------------------------------------------------------------------------

class TestSnapTradeParsers:
    def test_asset_type_mapping(self):
        assert _asset_type("cs") == "stock"
        assert _asset_type("et") == "etf"
        assert _asset_type("crypto") == "crypto"
        assert _asset_type("") == "other"
        assert _asset_type(None) == "other"

    def test_parse_position_stock(self):
        pos = {
            "symbol": {
                "symbol": {
                    "symbol": "AAPL",
                    "description": "Apple Inc.",
                    "currency": {"code": "USD"},
                    "type": {"code": "cs"},
                }
            },
            "units": 10,
            "price": 200.0,
            "average_purchase_price": 150.0,
        }
        h = _parse_position(pos)
        assert h["symbol"] == "AAPL"
        assert h["asset_type"] == "stock"
        assert h["quantity"] == 10.0
        assert h["average_purchase_price"] == 150.0
        assert h["last_price"] == 200.0
        assert h["market_value"] == 2000.0

    def test_parse_position_crypto(self):
        pos = {
            "symbol": {"symbol": {"symbol": "BTC", "type": {"code": "crypto"}}},
            "units": 0.5,
            "price": 40000.0,
        }
        h = _parse_position(pos)
        assert h["symbol"] == "BTC"
        assert h["asset_type"] == "crypto"
        assert h["market_value"] == 20000.0

    def test_parse_position_without_ticker_is_skipped(self):
        assert _parse_position({"symbol": {"symbol": {}}, "units": 1}) is None

    def test_normalize_account_holdings(self):
        item = {
            "account": {"id": "st_1", "name": "Brokerage", "institution_name": "Robinhood"},
            "positions": [
                {"symbol": {"symbol": {"symbol": "AAPL", "type": {"code": "cs"}}},
                 "units": 1, "price": 100.0},
            ],
            "total_value": {"value": 100.0, "currency": "USD"},
        }
        out = _normalize_account_holdings(item)
        assert out["account"]["id"] == "st_1"
        assert out["account"]["institution"] == "Robinhood"
        assert len(out["holdings"]) == 1
        assert out["total_value"] == 100.0


# ---------------------------------------------------------------------------
# Portfolio aggregation
# ---------------------------------------------------------------------------

class TestSummarizeHoldings:
    _holdings = [
        {"symbol": "AAPL", "asset_type": "stock", "quantity": 10.0,
         "average_purchase_price": 150.0, "market_value": 2000.0},
        {"symbol": "BTC", "asset_type": "crypto", "quantity": 0.5,
         "average_purchase_price": 30000.0, "market_value": 20000.0},
    ]

    def test_totals_and_gain(self):
        s = summarize_holdings(self._holdings)
        assert s["total_value"] == 22000.0
        assert s["total_cost"] == 16500.0      # 1500 + 15000
        assert s["total_gain"] == 5500.0
        assert s["holding_count"] == 2

    def test_allocation_sorted_by_value(self):
        s = summarize_holdings(self._holdings)
        assert s["allocation"][0]["asset_type"] == "crypto"
        assert s["allocation"][0]["pct"] == pytest.approx(90.9, abs=0.1)

    def test_concentration_ranks_largest_first(self):
        s = summarize_holdings(self._holdings)
        assert s["concentration"][0]["symbol"] == "BTC"

    def test_empty_portfolio(self):
        s = summarize_holdings([])
        assert s["total_value"] == 0.0
        assert s["total_gain_pct"] is None
        assert s["holding_count"] == 0


# ---------------------------------------------------------------------------
# Router tests — mocked SnapTrade client
# ---------------------------------------------------------------------------

def _sample_portfolios():
    return [
        {
            "account": {
                "id": "st_acc_1",
                "name": "Robinhood Individual",
                "institution": "Robinhood",
                "number": "x",
            },
            "holdings": [
                {"symbol": "AAPL", "description": "Apple Inc.", "asset_type": "stock",
                 "quantity": 10.0, "average_purchase_price": 150.0, "last_price": 200.0,
                 "market_value": 2000.0, "currency": "USD"},
                {"symbol": "BTC", "description": "Bitcoin", "asset_type": "crypto",
                 "quantity": 0.5, "average_purchase_price": 30000.0, "last_price": 40000.0,
                 "market_value": 20000.0, "currency": "USD"},
            ],
            "total_value": 22000.0,
            "currency": "USD",
        },
    ]


class _FakeSnapTrade:
    """Stand-in for SnapTradeClient — all network methods are AsyncMocks."""

    def __init__(self, configured=True):
        self.configured = configured
        self.register_user = AsyncMock(return_value={"user_id": "u1", "user_secret": "s1"})
        self.login_url = AsyncMock(return_value="https://app.snaptrade.com/connect/abc")
        self.get_all_holdings = AsyncMock(return_value=_sample_portfolios())
        self.list_connections = AsyncMock(
            return_value=[{"id": "auth1", "brokerage": "Robinhood", "disabled": False}]
        )
        self.remove_connection = AsyncMock(return_value=True)


@pytest.fixture
def fake_snaptrade():
    fake = _FakeSnapTrade()
    with patch.object(state, "snaptrade", fake):
        yield fake


def _seed_creds():
    state.snaptrade_creds["household"] = {"user_id": "u1", "user_secret": "s1"}


class TestSnapTradeConfig:
    def test_config_reports_configured(self, client, fake_snaptrade):
        body = client.get("/api/config/snaptrade").json()
        assert body["configured"] is True
        assert body["connected"] is False

    def test_config_when_unconfigured(self, client):
        with patch.object(state, "snaptrade", _FakeSnapTrade(configured=False)):
            body = client.get("/api/config/snaptrade").json()
        assert body["configured"] is False

    def test_sync_503_when_unconfigured(self, client):
        with patch.object(state, "snaptrade", _FakeSnapTrade(configured=False)):
            assert client.post("/api/snaptrade/sync").status_code == 503

    def test_sync_409_without_connection(self, client, fake_snaptrade):
        assert client.post("/api/snaptrade/sync").status_code == 409


class TestSnapTradeConnect:
    def test_connect_registers_user_and_returns_url(self, client, fake_snaptrade):
        resp = client.post("/api/snaptrade/connect")
        assert resp.status_code == 200, resp.text
        assert resp.json()["redirect_uri"].startswith("https://")
        # The household user is now persisted.
        assert state.snaptrade_creds.get("household", {}).get("user_secret") == "s1"


class TestSnapTradeSync:
    def test_sync_persists_accounts_holdings_snapshots(self, client, fake_snaptrade):
        _seed_creds()
        resp = client.post("/api/snaptrade/sync")
        assert resp.status_code == 200, resp.text
        assert resp.json()["accounts"] == 1

        record = accounts_repo_memory.get_accounts().get("st_acc_1")
        assert record is not None
        assert record["source"] == "snaptrade"
        assert record["type"] == "investment"
        assert record["manual"] is False

        repo = accounts_repo_memory.active()
        assert len(repo.holdings["st_acc_1"]) == 2
        snaps = [s for s in accounts_repo_memory.get_snapshots() if s["account_id"] == "st_acc_1"]
        assert len(snaps) == 1
        assert float(snaps[0]["available"]) == 22000.0

    def test_sync_replaces_holdings_each_run(self, client, fake_snaptrade):
        _seed_creds()
        client.post("/api/snaptrade/sync")
        # Second sync returns a single holding — the stale one must be dropped.
        fake_snaptrade.get_all_holdings.return_value = [
            {
                "account": {"id": "st_acc_1", "name": "Robinhood Individual",
                            "institution": "Robinhood", "number": "x"},
                "holdings": [
                    {"symbol": "VTI", "description": "Vanguard Total", "asset_type": "etf",
                     "quantity": 5.0, "average_purchase_price": 200.0, "last_price": 220.0,
                     "market_value": 1100.0, "currency": "USD"},
                ],
                "total_value": 1100.0,
                "currency": "USD",
            }
        ]
        client.post("/api/snaptrade/sync")
        repo = accounts_repo_memory.active()
        assert [h["symbol"] for h in repo.holdings["st_acc_1"]] == ["VTI"]

    def test_synced_value_flows_into_balances_summary(self, client, fake_snaptrade):
        _seed_creds()
        client.post("/api/snaptrade/sync")
        summary = client.get("/api/balances/summary").json()
        assert summary["total_investments"] == 22000.0
        assert summary["net_worth"] == 22000.0


class TestInvestmentsRouter:
    def test_portfolio_aggregates_synced_holdings(self, client, fake_snaptrade):
        _seed_creds()
        client.post("/api/snaptrade/sync")
        portfolio = client.get("/api/investments/portfolio").json()
        assert portfolio["total_value"] == 22000.0
        assert portfolio["total_gain"] == 5500.0
        assert portfolio["holding_count"] == 2
        assert len(portfolio["by_account"]) == 1

    def test_holdings_grouped_by_account(self, client, fake_snaptrade):
        _seed_creds()
        client.post("/api/snaptrade/sync")
        body = client.get("/api/investments/holdings").json()
        assert body["holding_count"] == 2
        assert body["accounts"][0]["account_id"] == "st_acc_1"

    def test_portfolio_empty_without_sync(self, client):
        portfolio = client.get("/api/investments/portfolio").json()
        assert portfolio["holding_count"] == 0


# ---------------------------------------------------------------------------
# Advisor snapshot block
# ---------------------------------------------------------------------------

class TestInvestmentsSnapshot:
    def test_snapshot_none_without_holdings(self):
        assert _investments_snapshot() is None

    def test_snapshot_block_after_holdings(self):
        repo = accounts_repo_memory.active()
        repo.upsert_synced_account(
            {"id": "st_acc_1", "name": "Brokerage", "type": "investment",
             "subtype": "brokerage", "institution": {"name": "Robinhood"}},
            source="snaptrade",
        )
        repo.replace_holdings("st_acc_1", [
            {"symbol": "AAPL", "asset_type": "stock", "quantity": 10.0,
             "average_purchase_price": 150.0, "last_price": 200.0,
             "market_value": 2000.0, "currency": "USD"},
        ])
        snap = _investments_snapshot()
        assert snap is not None
        assert snap["total_value"] == 2000.0
        assert snap["holding_count"] == 1
        assert snap["holdings"][0]["symbol"] == "AAPL"
        assert snap["concentrated"] is True   # single holding = 100%


class TestBankSyncedBrokerages:
    """A brokerage reached through the bank aggregator is an investment
    everywhere else in the app; the Investments page has to agree.

    SimpleFIN reports these accounts' value but never their positions, so they
    arrive as balance-only rows rather than holdings.
    """

    def _cache_simplefin_brokerage(self):
        import state
        state._balances_cache_store.data["simplefin_accounts"] = [{
            "id": "sf_broker_1",
            "institution": "E*Trade",
            "name": "Individual Brokerage (9423)",
            "type": "investment",
            "subtype": "brokerage",
            "available": 1412.25,
            "ledger": 1412.25,
            "source": "simplefin",
        }]
        state._balances_cache_store.data["simplefin_cash"] = 0.0
        state._balances_cache_store.data["simplefin_credit_debt"] = 0.0
        state._balances_cache_store.save()

    def test_portfolio_includes_a_bank_synced_brokerage(self, client):
        self._cache_simplefin_brokerage()

        data = client.get("/api/investments/portfolio").json()

        rows = {a["account_name"]: a for a in data["by_account"]}
        assert "Individual Brokerage (9423)" in rows
        assert rows["Individual Brokerage (9423)"]["value"] == 1412.25
        assert rows["Individual Brokerage (9423)"]["source"] == "simplefin"
        # Its balance counts toward the total, and is reported separately so
        # the UI can say the allocation doesn't cover it.
        assert data["total_value"] == 1412.25
        assert data["balance_only_value"] == 1412.25

    def test_holdings_lists_it_with_no_positions(self, client):
        self._cache_simplefin_brokerage()

        data = client.get("/api/investments/holdings").json()

        account = next(a for a in data["accounts"] if a["account_id"] == "sf_broker_1")
        assert account["holdings"] == []
        assert account["source"] == "simplefin"

    def test_depository_accounts_are_not_pulled_in(self, client):
        """Only the investment bucket crosses over — a checking account must
        not appear on the Investments page."""
        import state
        state._balances_cache_store.data["simplefin_accounts"] = [{
            "id": "sf_checking",
            "institution": "Chase",
            "name": "TOTAL CHECKING",
            "type": "depository",
            "subtype": "checking",
            "available": 500.0,
            "ledger": 500.0,
            "source": "simplefin",
        }]
        state._balances_cache_store.save()

        data = client.get("/api/investments/portfolio").json()

        assert data["by_account"] == []
        assert data["total_value"] == 0
