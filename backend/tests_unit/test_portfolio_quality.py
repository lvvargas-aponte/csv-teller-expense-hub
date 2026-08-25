"""Tests for portfolio_quality — concentration, allocation drift, cash drag."""
import pytest

import portfolio_quality
from db import accounts_repo_memory


def _holding(symbol, asset_type, market_value, account_id="a1"):
    return {
        "account_id": account_id, "symbol": symbol, "asset_type": asset_type,
        "quantity": 1.0, "average_purchase_price": None,
        "market_value": market_value,
    }


_PROFILE = {}


@pytest.fixture(autouse=True)
def _stub_profile(monkeypatch):
    """No stated risk tolerance unless a test seeds one."""
    _PROFILE.clear()
    monkeypatch.setattr(portfolio_quality, "_load_profile", lambda: dict(_PROFILE))


def _seed(holdings, risk=None):
    repo = accounts_repo_memory.active()
    repo.upsert_synced_account(
        {"id": "a1", "name": "Brokerage", "type": "investment",
         "subtype": "brokerage", "institution": {"name": "Robinhood"}},
        source="snaptrade",
    )
    repo.replace_holdings("a1", holdings)
    if risk:
        _PROFILE["risk_tolerance"] = risk


class TestConcentration:
    def test_a_single_position_at_23_pct_is_concentrated(self):
        _seed([
            _holding("NVDA", "stock", 23000.0),
            _holding("AAPL", "stock", 9000.0),
            _holding("MSFT", "stock", 9000.0),
            _holding("VTI", "etf", 59000.0),
        ])

        out = portfolio_quality.assess()

        assert out["concentration"]["largest"]["symbol"] == "VTI"
        assert out["concentration"]["flag"] == "concentrated"
        assert out["concentration"]["positions_over_threshold"] == 1
        assert out["concentration"]["threshold_pct"] == 10.0

    def test_five_equal_funds_are_not_concentrated(self):
        _seed([_holding(s, "etf", 20000.0) for s in ("VTI", "VXUS", "BND", "VNQ", "VB")])

        out = portfolio_quality.assess()

        assert out["concentration"]["flag"] == "diversified"
        assert out["concentration"]["positions_over_threshold"] == 0
        assert out["concentration"]["top_5_pct"] == 100.0

    def test_empty_portfolio_is_unavailable(self):
        _seed([])
        out = portfolio_quality.assess()
        assert out["available"] is False


class TestAllocationDrift:
    def test_all_equity_against_a_balanced_target_drifts_30_points(self):
        _seed([_holding("VTI", "etf", 90000.0), _holding("CASH", "cash", 10000.0)],
              risk="balanced")

        out = portfolio_quality.assess()["allocation"]

        assert out["target"] == {"equity": 60.0, "bond": 30.0, "cash": 10.0}
        assert out["target_source"] == "risk_tolerance:balanced"
        assert out["by_class"]["equity"] == 90.0
        assert out["largest_drift"] == {
            "class": "equity", "actual": 90.0, "target": 60.0, "drift_pts": 30.0,
        }

    def test_aggressive_target_comes_from_config(self):
        _seed([_holding("VTI", "etf", 100000.0)], risk="aggressive")
        out = portfolio_quality.assess()["allocation"]
        assert out["target"] == {"equity": 85.0, "bond": 10.0, "cash": 5.0}

    def test_no_stated_risk_means_no_target(self):
        _seed([_holding("VTI", "etf", 100000.0)])
        out = portfolio_quality.assess()["allocation"]
        assert out["target"] is None
        assert out["target_source"] == "none"
        assert out["largest_drift"] is None

    def test_etfs_are_counted_as_equity_and_the_card_says_so(self):
        _seed([_holding("BND", "etf", 100000.0)], risk="balanced")
        out = portfolio_quality.assess()["allocation"]
        assert out["by_class"]["equity"] == 100.0
        assert out["etf_caveat"] is not None
        assert "counted as equity" in out["etf_caveat"]

    def test_actual_is_reported_by_asset_type_too(self):
        _seed([_holding("VTI", "etf", 78000.0), _holding("NVDA", "stock", 12000.0),
               _holding("CASH", "cash", 10000.0)])
        out = portfolio_quality.assess()["allocation"]
        assert out["actual"] == {"etf": 78.0, "stock": 12.0, "cash": 10.0}


class TestCashDrag:
    def test_cash_drag_is_the_cash_share_of_the_portfolio(self):
        _seed([_holding("VTI", "etf", 90000.0), _holding("CASH", "cash", 10000.0)])
        assert portfolio_quality.assess()["cash_drag_pct"] == 10.0

    def test_no_cash_is_zero_drag(self):
        _seed([_holding("VTI", "etf", 90000.0)])
        assert portfolio_quality.assess()["cash_drag_pct"] == 0.0


class TestQualityEndpoint:
    def test_endpoint_returns_the_assessment(self, client):
        _seed([_holding("VTI", "etf", 90000.0), _holding("CASH", "cash", 10000.0)],
              risk="balanced")

        body = client.get("/api/investments/quality").json()

        assert body["available"] is True
        assert body["allocation"]["largest_drift"]["drift_pts"] == pytest.approx(30.0)


# ---------------------------------------------------------------------------
# Trailing mix backtest — today's holdings priced backwards, never "your return"
# ---------------------------------------------------------------------------

class _FakeMarket:
    """Stands in for the yfinance-backed price-history helper. No network."""

    def __init__(self, changes, error=None):
        self.changes = changes
        self.error = error
        self.calls = []

    async def get_price_changes(self, symbols, period):
        self.calls.append((tuple(symbols), period))
        if self.error:
            raise self.error
        return {s: self.changes.get(period, {}).get(s) for s in symbols}


@pytest.fixture
def market(monkeypatch):
    from agent import market_tools

    def _install(changes, error=None):
        fake = _FakeMarket(changes, error)
        monkeypatch.setattr(market_tools, "get_price_changes", fake.get_price_changes)
        portfolio_quality.clear_backtest_cache()
        return fake

    return _install


class TestMixBacktest:
    @pytest.mark.asyncio
    async def test_two_holdings_produce_a_weighted_return(self, market):
        _seed([_holding("VTI", "etf", 60000.0), _holding("NVDA", "stock", 40000.0)])
        market({"1y": {"VTI": 10.0, "NVDA": 20.0, "SPY": 11.8}})

        out = await portfolio_quality.mix_backtest(periods=("1y",))

        assert out["available"] is True
        assert out["periods"]["1y"]["mix_return_pct"] == pytest.approx(14.0)
        assert out["periods"]["1y"]["benchmark_return_pct"] == pytest.approx(11.8)
        assert out["periods"]["1y"]["benchmark"] == "SPY"
        assert out["periods"]["1y"]["coverage_pct"] == 100.0
        assert out["unpriceable_symbols"] == []

    @pytest.mark.asyncio
    async def test_it_never_calls_itself_your_return(self, market):
        _seed([_holding("VTI", "etf", 100000.0)])
        market({"1y": {"VTI": 10.0, "SPY": 8.0}})

        out = await portfolio_quality.mix_backtest(periods=("1y",))

        assert "not your actual return" in out["disclaimer"]

    @pytest.mark.asyncio
    async def test_an_unpriceable_symbol_is_excluded_and_named(self, market):
        _seed([_holding("VTI", "etf", 90000.0),
               _holding("PRIVATEFUND", "other", 10000.0)])
        market({"1y": {"VTI": 10.0, "PRIVATEFUND": None, "SPY": 8.0}})

        out = await portfolio_quality.mix_backtest(periods=("1y",))

        assert out["periods"]["1y"]["mix_return_pct"] == pytest.approx(10.0)
        assert out["periods"]["1y"]["coverage_pct"] == pytest.approx(90.0)
        assert out["unpriceable_symbols"] == ["PRIVATEFUND"]

    @pytest.mark.asyncio
    async def test_below_the_coverage_floor_no_number_is_reported(self, market):
        _seed([_holding("VTI", "etf", 70000.0),
               _holding("PRIVATEFUND", "other", 30000.0)])
        market({"1y": {"VTI": 10.0, "PRIVATEFUND": None, "SPY": 8.0}})

        period = (await portfolio_quality.mix_backtest(periods=("1y",)))["periods"]["1y"]

        assert period["available"] is False
        assert period["mix_return_pct"] is None
        assert period["coverage_pct"] == pytest.approx(70.0)
        assert "70" in period["reason"] or "coverage" in period["reason"].lower()

    @pytest.mark.asyncio
    async def test_cash_counts_as_a_zero_return_slice(self, market):
        _seed([_holding("VTI", "etf", 50000.0), _holding("CASH", "cash", 50000.0)])
        market({"1y": {"VTI": 10.0, "SPY": 8.0}})

        period = (await portfolio_quality.mix_backtest(periods=("1y",)))["periods"]["1y"]

        assert period["mix_return_pct"] == pytest.approx(5.0)
        assert period["coverage_pct"] == 100.0

    @pytest.mark.asyncio
    async def test_offline_degrades_to_unavailable_without_raising(self, market):
        _seed([_holding("VTI", "etf", 100000.0)])
        market({}, error=OSError("no route to host"))

        out = await portfolio_quality.mix_backtest(periods=("1y",))

        assert out["available"] is False
        assert out["reason"]
        assert out["periods"] == {}

    @pytest.mark.asyncio
    async def test_an_empty_portfolio_is_unavailable(self, market):
        _seed([])
        market({"1y": {}})
        out = await portfolio_quality.mix_backtest(periods=("1y",))
        assert out["available"] is False

    @pytest.mark.asyncio
    async def test_the_result_is_cached_for_the_day(self, market):
        _seed([_holding("VTI", "etf", 100000.0)])
        fake = market({"1y": {"VTI": 10.0, "SPY": 8.0}})

        await portfolio_quality.mix_backtest(periods=("1y",))
        await portfolio_quality.mix_backtest(periods=("1y",))

        assert len(fake.calls) == 1


# ---------------------------------------------------------------------------
# Fees — the one portfolio number that is knowable in advance
# ---------------------------------------------------------------------------

class _FakeFunds:
    def __init__(self, profiles, error=None):
        self.profiles = profiles
        self.error = error
        self.calls = []

    async def get_fund_profiles(self, symbols):
        self.calls.append(tuple(symbols))
        if self.error:
            raise self.error
        return {s: self.profiles.get(s, {}) for s in symbols}

    def cached_fund_profiles(self, symbols):
        return {s: self.profiles[s] for s in symbols if s in self.profiles}


@pytest.fixture
def funds(monkeypatch):
    from agent import market_tools

    def _install(profiles, error=None):
        fake = _FakeFunds(profiles, error)
        monkeypatch.setattr(market_tools, "get_fund_profiles", fake.get_fund_profiles)
        monkeypatch.setattr(
            market_tools, "cached_fund_profiles", fake.cached_fund_profiles
        )
        return fake

    return _install


class TestFeeSummary:
    @pytest.mark.asyncio
    async def test_weighted_expense_ratio_excludes_individual_stocks(self, funds):
        _seed([_holding("VTI", "etf", 60000.0), _holding("ARKK", "etf", 40000.0),
               _holding("NVDA", "stock", 50000.0)])
        funds({
            "VTI": {"expense_ratio_pct": 0.03, "category": "Large Blend"},
            "ARKK": {"expense_ratio_pct": 0.65, "category": "Mid-Cap Growth"},
            "NVDA": {"expense_ratio_pct": None, "category": None},
        })

        out = await portfolio_quality.fee_summary()

        assert out["available"] is True
        assert out["weighted_expense_ratio_pct"] == pytest.approx(0.278, abs=0.001)
        assert out["annual_fee_cost"] == pytest.approx(278.0, abs=1.0)
        assert out["funds_priced"] == 2

    @pytest.mark.asyncio
    async def test_an_expensive_fund_is_flagged(self, funds):
        _seed([_holding("VTI", "etf", 60000.0), _holding("ARKK", "etf", 40000.0)])
        funds({
            "VTI": {"expense_ratio_pct": 0.03, "category": "Large Blend"},
            "ARKK": {"expense_ratio_pct": 0.65, "category": "Mid-Cap Growth"},
        })

        rows = (await portfolio_quality.fee_summary())["holdings"]

        expensive = [r for r in rows if r["high"]]
        assert [r["symbol"] for r in expensive] == ["ARKK"]
        assert rows[0]["symbol"] == "ARKK"        # biggest annual cost first
        assert rows[0]["annual_cost"] == pytest.approx(260.0, abs=0.5)

    @pytest.mark.asyncio
    async def test_a_portfolio_of_only_stocks_reports_no_fee_figure(self, funds):
        _seed([_holding("NVDA", "stock", 50000.0)])
        funds({"NVDA": {"expense_ratio_pct": None, "category": None}})

        out = await portfolio_quality.fee_summary()

        assert out["available"] is False
        assert out["funds_priced"] == 0
        assert out["annual_fee_cost"] is None

    @pytest.mark.asyncio
    async def test_offline_degrades_without_raising(self, funds):
        _seed([_holding("VTI", "etf", 60000.0)])
        funds({}, error=OSError("no route to host"))

        out = await portfolio_quality.fee_summary()

        assert out["available"] is False
        assert out["reason"]


class TestFundCategoriesFeedTheAllocation:
    def test_a_known_bond_fund_leaves_the_equity_bucket(self, funds):
        _seed([_holding("BND", "etf", 40000.0), _holding("VTI", "etf", 60000.0)],
              risk="balanced")
        funds({
            "BND": {"expense_ratio_pct": 0.03, "category": "Intermediate Core Bond"},
            "VTI": {"expense_ratio_pct": 0.03, "category": "Large Blend"},
        })

        out = portfolio_quality.assess()["allocation"]

        assert out["by_class"]["bond"] == 40.0
        assert out["by_class"]["equity"] == 60.0
        assert out["etf_caveat"] is None

    def test_the_caveat_stays_for_funds_with_no_known_category(self, funds):
        _seed([_holding("BND", "etf", 40000.0), _holding("MYSTERY", "etf", 60000.0)])
        funds({"BND": {"expense_ratio_pct": 0.03, "category": "Intermediate Core Bond"}})

        out = portfolio_quality.assess()["allocation"]

        assert out["by_class"]["bond"] == 40.0
        assert out["by_class"]["equity"] == 60.0
        assert out["etf_caveat"] is not None
