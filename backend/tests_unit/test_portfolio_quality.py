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
