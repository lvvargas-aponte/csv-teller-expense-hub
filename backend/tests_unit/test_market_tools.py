"""Unit tests for the Fin market tools — yfinance is mocked, no network."""
import asyncio
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from agent.schemas import (
    GetStockFundamentalsArgs,
    GetStockHistoryArgs,
    GetStockQuoteArgs,
)
from agent.market_tools import (
    _get_stock_fundamentals,
    _get_stock_history,
    _get_stock_quote,
    build_market_tools,
)


def _run(coro):
    return asyncio.run(coro)


def _install_fake_yf(ticker_factory):
    fake_module = ModuleType("yfinance")
    fake_module.Ticker = ticker_factory
    return patch.dict(sys.modules, {"yfinance": fake_module})


class TestGetStockQuote:
    def test_quote_shape(self):
        fast_info = SimpleNamespace(
            last_price=150.0, previous_close=145.0, currency="USD",
            year_high=180.0, year_low=90.0, market_cap=2.5e12,
        )
        ticker = MagicMock(fast_info=fast_info)
        with _install_fake_yf(MagicMock(return_value=ticker)):
            out = _run(_get_stock_quote(GetStockQuoteArgs(symbols=["nvda"])))
        assert out["count"] == 1
        q = out["quotes"][0]
        assert q["symbol"] == "NVDA"
        assert q["available"] is True
        assert q["last_price"] == 150.0
        assert q["day_change_pct"] == 3.45
        assert q["year_high"] == 180.0

    def test_missing_symbol_marked_unavailable(self):
        fast_info = SimpleNamespace(last_price=None, previous_close=None)
        ticker = MagicMock(fast_info=fast_info)
        with _install_fake_yf(MagicMock(return_value=ticker)):
            out = _run(_get_stock_quote(GetStockQuoteArgs(symbols=["FAKE"])))
        q = out["quotes"][0]
        assert q["available"] is False
        assert "note" in q

    def test_symbols_bounds_enforced_by_schema(self):
        with pytest.raises(Exception):
            GetStockQuoteArgs(symbols=[])
        with pytest.raises(Exception):
            GetStockQuoteArgs(symbols=[f"S{i}" for i in range(11)])


class TestGetStockHistory:
    def _fake_df(self, closes, dates):
        import datetime

        class FakeSeries:
            def __init__(self, values, idx):
                self._values = values
                self._idx = idx
                self.iloc = self

            def __getitem__(self, key):
                if isinstance(key, slice):
                    return FakeSeries(self._values[key], self._idx[key])
                return self._values[key]

            def items(self):
                return list(zip(self._idx, self._values))

            def min(self):
                return min(self._values)

            def max(self):
                return max(self._values)

            def __len__(self):
                return len(self._values)

        idx = [SimpleNamespace(date=lambda d=d: d) for d in dates]
        series = FakeSeries(closes, idx)
        df = MagicMock(empty=False)
        df.__getitem__ = MagicMock(return_value=series)
        return df

    def test_history_shape_and_downsampling(self):
        import datetime
        closes = [100.0 + i for i in range(120)]
        dates = [datetime.date(2026, 1, 1) + datetime.timedelta(days=i) for i in range(120)]
        df = self._fake_df(closes, dates)
        ticker = MagicMock()
        ticker.history.return_value = df
        with _install_fake_yf(MagicMock(return_value=ticker)):
            out = _run(_get_stock_history(GetStockHistoryArgs(symbol="nvda", period="6mo")))
        assert out["available"] is True
        assert out["symbol"] == "NVDA"
        assert out["start_price"] == 100.0
        assert out["end_price"] == 219.0
        assert out["pct_change"] == 119.0
        assert len(out["closes"]) <= 12

    def test_empty_history_unavailable(self):
        df = MagicMock(empty=True)
        ticker = MagicMock()
        ticker.history.return_value = df
        with _install_fake_yf(MagicMock(return_value=ticker)):
            out = _run(_get_stock_history(GetStockHistoryArgs(symbol="FAKE")))
        assert out["available"] is False


class TestGetStockFundamentals:
    def test_fundamentals_shape(self):
        info = {
            "shortName": "NVIDIA Corp", "sector": "Technology",
            "trailingPE": 45.2, "forwardPE": 32.1, "dividendYield": 0.0003,
            "beta": 1.7, "fiftyTwoWeekHigh": 180.0, "fiftyTwoWeekLow": 90.0,
            "targetMeanPrice": 190.0, "recommendationKey": "buy",
            "regularMarketPrice": 150.0,
        }
        ticker = MagicMock(info=info)
        with _install_fake_yf(MagicMock(return_value=ticker)):
            out = _run(_get_stock_fundamentals(GetStockFundamentalsArgs(symbol="nvda")))
        assert out["available"] is True
        assert out["name"] == "NVIDIA Corp"
        assert out["trailing_pe"] == 45.2
        assert out["analyst_recommendation"] == "buy"

    def test_info_error_marked_unavailable(self):
        ticker = MagicMock()
        type(ticker).info = property(MagicMock(side_effect=RuntimeError("yahoo down")))
        with _install_fake_yf(MagicMock(return_value=ticker)):
            out = _run(_get_stock_fundamentals(GetStockFundamentalsArgs(symbol="NVDA")))
        assert out["available"] is False


class TestBuildMarketTools:
    def test_three_tools(self):
        tools = build_market_tools()
        assert [t.name for t in tools] == [
            "get_stock_quote", "get_stock_history", "get_stock_fundamentals",
        ]


class TestFundProfiles:
    """Expense ratios change about once a year — they are cached for a week."""

    def _yf(self, info):
        return _install_fake_yf(MagicMock(return_value=MagicMock(info=info)))

    def setup_method(self):
        from agent import market_tools

        market_tools.clear_fund_profile_cache()

    def test_ratio_is_normalized_to_a_percentage(self):
        from agent.market_tools import get_fund_profiles

        with self._yf({"annualReportExpenseRatio": 0.0003, "category": "Large Blend"}):
            out = _run(get_fund_profiles(["VTI"]))
        assert out["VTI"]["expense_ratio_pct"] == pytest.approx(0.03)
        assert out["VTI"]["category"] == "Large Blend"

    def test_a_stock_has_no_ratio(self):
        from agent.market_tools import get_fund_profiles

        with self._yf({"shortName": "NVIDIA Corp"}):
            out = _run(get_fund_profiles(["NVDA"]))
        assert out["NVDA"]["expense_ratio_pct"] is None

    def test_a_second_call_is_served_from_the_cache(self):
        from agent import market_tools

        factory = MagicMock(return_value=MagicMock(
            info={"annualReportExpenseRatio": 0.0003, "category": "Large Blend"}
        ))
        with _install_fake_yf(factory):
            _run(market_tools.get_fund_profiles(["VTI"]))
            _run(market_tools.get_fund_profiles(["VTI"]))
        assert factory.call_count == 1
        assert market_tools.cached_fund_profiles(["VTI"])["VTI"]["category"] == "Large Blend"

    def test_a_stale_entry_is_refetched(self):
        from agent import market_tools

        factory = MagicMock(return_value=MagicMock(
            info={"annualReportExpenseRatio": 0.0003, "category": "Large Blend"}
        ))
        with _install_fake_yf(factory):
            _run(market_tools.get_fund_profiles(["VTI"]))
            market_tools._FUND_PROFILE_CACHE["VTI"] = (
                0.0, market_tools._FUND_PROFILE_CACHE["VTI"][1]
            )
            _run(market_tools.get_fund_profiles(["VTI"]))
        assert factory.call_count == 2
