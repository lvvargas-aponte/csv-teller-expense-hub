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
        self.get_account_holdings = AsyncMock(return_value=_sample_portfolios()[0])
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
# Empty synced accounts (e.g. Robinhood's auto-created crypto sub-account)
# ---------------------------------------------------------------------------

def _empty_portfolio(name="Robinhood Crypto", account_id="st_empty"):
    return {
        "account": {"id": account_id, "name": name,
                    "institution": "Robinhood", "number": "x"},
        "holdings": [],
        "total_value": 0.0,
        "currency": "USD",
    }


class TestEmptySyncedAccounts:
    def test_empty_account_hidden_from_portfolio_and_balances(self, client, fake_snaptrade):
        _seed_creds()
        fake_snaptrade.get_all_holdings.return_value = (
            _sample_portfolios() + [_empty_portfolio()]
        )
        client.post("/api/snaptrade/sync")

        portfolio = client.get("/api/investments/portfolio").json()
        assert [a["account_id"] for a in portfolio["by_account"]] == ["st_acc_1"]
        assert portfolio["total_value"] == 22000.0

        summary = client.get("/api/balances/summary").json()
        assert "Robinhood Crypto" not in [a["name"] for a in summary["accounts"]]

    def test_sync_still_records_the_empty_account(self, client, fake_snaptrade):
        # Filtering is a display decision — the sync keeps recording whatever
        # the brokerage reported, so the account returns on its own if funded.
        _seed_creds()
        fake_snaptrade.get_all_holdings.return_value = (
            _sample_portfolios() + [_empty_portfolio()]
        )
        assert client.post("/api/snaptrade/sync").json()["accounts"] == 2
        cached = state._balances_cache.get("snaptrade_accounts", [])
        assert {a["id"] for a in cached} == {"st_acc_1", "st_empty"}

    def test_funded_account_without_positions_is_kept(self, client, fake_snaptrade):
        # Some SnapTrade plan tiers report an account total but no positions —
        # that is a real balance and must not be filtered out as "empty".
        _seed_creds()
        funded = _empty_portfolio(name="Schwab Individual", account_id="st_funded")
        funded["total_value"] = 5428.63
        fake_snaptrade.get_all_holdings.return_value = [funded]
        client.post("/api/snaptrade/sync")

        portfolio = client.get("/api/investments/portfolio").json()
        assert [a["account_id"] for a in portfolio["by_account"]] == ["st_funded"]
        assert portfolio["total_value"] == 5428.63

    def test_account_returns_once_it_reports_a_balance(self, client, fake_snaptrade):
        _seed_creds()
        fake_snaptrade.get_all_holdings.return_value = [_empty_portfolio()]
        client.post("/api/snaptrade/sync")
        assert client.get("/api/investments/portfolio").json()["by_account"] == []

        funded = _empty_portfolio()
        funded["total_value"] = 250.0
        fake_snaptrade.get_account_holdings.return_value = funded
        client.post("/api/snaptrade/sync/st_empty")

        portfolio = client.get("/api/investments/portfolio").json()
        assert [a["account_id"] for a in portfolio["by_account"]] == ["st_empty"]
        assert portfolio["total_value"] == 250.0


# ---------------------------------------------------------------------------
# Investment accounts held outside SnapTrade (manual 401k, exchange balances)
# ---------------------------------------------------------------------------

class TestExternalInvestmentAccounts:
    def _add_manual(self, acct_id, name, type_, subtype, available):
        state._manual_accounts[acct_id] = {
            "id": acct_id, "institution": "Slavic401k", "name": name,
            "type": type_, "subtype": subtype, "available": available, "ledger": 0.0,
        }

    def test_manual_investment_accounts_join_the_portfolio(self, client):
        self._add_manual("m_401k", "401(k)", "investment", "401k", 62611.16)
        self._add_manual("m_eth", "Ether", "investment", "crypto", 5728.34)
        # A cash account must not leak in.
        self._add_manual("m_cash", "Checking", "depository", "checking", 900.0)

        portfolio = client.get("/api/investments/portfolio").json()
        by_id = {a["account_id"]: a for a in portfolio["by_account"]}
        assert set(by_id) == {"m_401k", "m_eth"}
        assert by_id["m_401k"]["value"] == 62611.16
        assert by_id["m_401k"]["source"] == "manual"
        assert portfolio["total_value"] == 68339.5
        assert portfolio["balance_only_value"] == 68339.5

    def test_portfolio_total_matches_balances_total_investments(self, client, fake_snaptrade):
        _seed_creds()
        client.post("/api/snaptrade/sync")
        self._add_manual("m_401k", "401(k)", "investment", "401k", 62611.16)

        portfolio = client.get("/api/investments/portfolio").json()
        summary = client.get("/api/balances/summary").json()
        assert portfolio["total_value"] == summary["total_investments"]

    def test_manual_accounts_appear_in_holdings_grouping(self, client):
        self._add_manual("m_401k", "401(k)", "investment", "401k", 62611.16)
        body = client.get("/api/investments/holdings").json()
        assert body["accounts"][0]["account_id"] == "m_401k"
        assert body["accounts"][0]["source"] == "manual"
        assert body["accounts"][0]["holdings"] == []


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
