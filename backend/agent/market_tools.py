"""Live market-data tools for the Fin agent, backed by yfinance.

Yahoo's endpoints drift — every field access is defensive (missing data
comes back as None, never a KeyError) and nothing here is persisted.
All yfinance calls run in a thread so the event loop stays free.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from agent.schemas import (
    GetStockFundamentalsArgs,
    GetStockHistoryArgs,
    GetStockQuoteArgs,
)


def _safe(obj: Any, attr: str) -> Optional[Any]:
    try:
        val = getattr(obj, attr, None)
        if val is None:
            return None
        return float(val) if isinstance(val, (int, float)) else val
    except Exception:
        return None


def _quote_one(symbol: str) -> Dict[str, Any]:
    import yfinance as yf

    ticker = yf.Ticker(symbol)
    fi = ticker.fast_info
    last = _safe(fi, "last_price")
    prev = _safe(fi, "previous_close")
    if last is None:
        return {"symbol": symbol.upper(), "available": False,
                "note": "No data — symbol may be invalid or delisted."}
    day_change_pct = (
        round((last - prev) / prev * 100, 2) if prev else None
    )
    return {
        "symbol": symbol.upper(),
        "available": True,
        "last_price": round(last, 2),
        "currency": _safe(fi, "currency"),
        "previous_close": round(prev, 2) if prev else None,
        "day_change_pct": day_change_pct,
        "year_high": _safe(fi, "year_high"),
        "year_low": _safe(fi, "year_low"),
        "market_cap": _safe(fi, "market_cap"),
    }


def _quotes(symbols: List[str]) -> List[Dict[str, Any]]:
    return [_quote_one(s) for s in symbols]


def _history(symbol: str, period: str) -> Dict[str, Any]:
    import yfinance as yf

    df = yf.Ticker(symbol).history(period=period)
    if df is None or df.empty:
        return {"symbol": symbol.upper(), "available": False,
                "note": "No price history — symbol may be invalid."}
    closes = df["Close"]
    start = float(closes.iloc[0])
    end = float(closes.iloc[-1])
    # Downsample to ~12 evenly spaced closes so the tool result stays small.
    step = max(1, len(closes) // 12)
    sampled = [
        {"date": str(idx.date()), "close": round(float(val), 2)}
        for idx, val in list(closes.iloc[::step].items())[:12]
    ]
    return {
        "symbol": symbol.upper(),
        "available": True,
        "period": period,
        "start_price": round(start, 2),
        "end_price": round(end, 2),
        "pct_change": round((end - start) / start * 100, 2) if start else None,
        "min": round(float(closes.min()), 2),
        "max": round(float(closes.max()), 2),
        "closes": sampled,
    }


def _fundamentals(symbol: str) -> Dict[str, Any]:
    import yfinance as yf

    info = {}
    try:
        info = yf.Ticker(symbol).info or {}
    except Exception:
        pass
    if not info or info.get("regularMarketPrice") is None and info.get("shortName") is None:
        return {"symbol": symbol.upper(), "available": False,
                "note": "No fundamentals available for this symbol."}
    return {
        "symbol": symbol.upper(),
        "available": True,
        "name": info.get("shortName"),
        "sector": info.get("sector"),
        "trailing_pe": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "dividend_yield": info.get("dividendYield"),
        "beta": info.get("beta"),
        "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
        "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
        "analyst_target_mean": info.get("targetMeanPrice"),
        "analyst_recommendation": info.get("recommendationKey"),
    }


def _price_changes(symbols: List[str], period: str) -> Dict[str, Optional[float]]:
    out: Dict[str, Optional[float]] = {}
    for symbol in symbols:
        try:
            history = _history(symbol, period)
        except Exception:
            out[symbol] = None
            continue
        out[symbol] = history.get("pct_change") if history.get("available") else None
    return out


async def get_price_changes(
    symbols: List[str], period: str
) -> Dict[str, Optional[float]]:
    """Trailing percent change per symbol over ``period``, None where unknown.

    The one price-history entry point outside the agent tools — same
    ``_history`` call underneath, same thread offload, so nothing else in the
    codebase needs to import yfinance.
    """
    return await asyncio.to_thread(_price_changes, symbols, period)


async def _get_stock_quote(args: GetStockQuoteArgs) -> Dict[str, Any]:
    quotes = await asyncio.to_thread(_quotes, args.symbols)
    return {"count": len(quotes), "quotes": quotes}


async def _get_stock_history(args: GetStockHistoryArgs) -> Dict[str, Any]:
    return await asyncio.to_thread(_history, args.symbol, args.period)


async def _get_stock_fundamentals(args: GetStockFundamentalsArgs) -> Dict[str, Any]:
    return await asyncio.to_thread(_fundamentals, args.symbol)


def build_market_tools() -> list:
    from agent.tools import Tool

    return [
        Tool(
            name="get_stock_quote",
            description=(
                "Live market quote for up to 10 ticker symbols: last price, "
                "day change, 52-week range, market cap. ALWAYS call this "
                "before giving an opinion on a specific ticker — never "
                "guess or recall a price."
            ),
            args_model=GetStockQuoteArgs,
            handler=_get_stock_quote,
        ),
        Tool(
            name="get_stock_history",
            description=(
                "Price history for one ticker over 1mo/3mo/6mo/1y/5y: "
                "start/end price, percent change, min/max, and ~12 sampled "
                "closes. Use for trend and 'how has X performed' questions."
            ),
            args_model=GetStockHistoryArgs,
            handler=_get_stock_history,
        ),
        Tool(
            name="get_stock_fundamentals",
            description=(
                "Fundamentals for one ticker: PE ratios, dividend yield, "
                "beta, sector, analyst mean target and recommendation. Use "
                "when weighing keep/trim/sell or comparing candidates."
            ),
            args_model=GetStockFundamentalsArgs,
            handler=_get_stock_fundamentals,
        ),
    ]
