"""Portfolio quality — concentration, allocation drift, and cash drag.

Reads ``analytics.summarize_holdings``, which is the single source of truth
for portfolio aggregation: the concentration ranking it already produces is
reused here rather than re-ranked, and the effective cost basis it resolves
(provider or user override) is the one these figures describe.

What this module deliberately does not do is suggest trades. Rebalancing is
advice, and the app cannot see the tax consequences of selling a position.
It states where the mix sits against the household's own stated risk band
and stops there.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import config

logger = logging.getLogger(__name__)

# asset_type is one of stock | etf | crypto | option | cash | other. It cannot
# tell a bond ETF from an equity ETF, so every fund lands in equity and the
# card says so out loud rather than showing a confidently wrong bond figure.
_CLASS_BY_ASSET_TYPE = {
    "stock": "equity",
    "etf": "equity",
    "option": "equity",
    "crypto": "other",
    "other": "other",
    "cash": "cash",
}

_FUND_ASSET_TYPES = {"etf"}

ETF_CAVEAT = (
    "ETFs are counted as equity — we can't see inside them yet, so a bond "
    "fund shows up on the equity side."
)


def _load_profile() -> Dict[str, Any]:
    """The household profile row, or an empty dict when nothing is answered."""
    try:
        from db import profile_repo

        return profile_repo.load() or {}
    except Exception:
        logger.warning("Could not load the user profile", exc_info=True)
        return {}


def _load_summary() -> Dict[str, Any]:
    from analytics import summarize_holdings
    from db.accounts_repo import get_repo

    return summarize_holdings(get_repo().get_holdings())


def asset_class(holding: Dict[str, Any]) -> str:
    """Broad class for one holding."""
    return _CLASS_BY_ASSET_TYPE.get(holding.get("asset_type"), "other")


def _target_allocation(profile: Dict[str, Any]) -> tuple:
    risk = (profile.get("risk_tolerance") or "").strip().lower()
    target = config.PORTFOLIO_TARGET_ALLOCATION_BY_RISK.get(risk)
    if not target:
        return None, "none"
    return dict(target), f"risk_tolerance:{risk}"


def _concentration(summary: Dict[str, Any]) -> Dict[str, Any]:
    """Built on the ranking ``summarize_holdings`` already produced.

    The threshold applies to individual securities. A broad fund at 20% is a
    diversified 20%; a single stock at 20% is one company's bad quarter.
    """
    ranked = summary["concentration"]
    total_value = summary["total_value"]
    fund_symbols = {
        h["symbol"] for h in summary["holdings"]
        if h.get("asset_type") in _FUND_ASSET_TYPES
    }
    threshold = config.PORTFOLIO_CONCENTRATION_THRESHOLD_PCT

    over: List[Dict[str, Any]] = []
    for h in summary["holdings"]:
        if h.get("asset_type") in _FUND_ASSET_TYPES or h.get("asset_type") == "cash":
            continue
        pct = (
            round(float(h.get("market_value") or 0.0) / total_value * 100, 1)
            if total_value else 0.0
        )
        if pct > threshold:
            over.append({"symbol": h["symbol"], "pct": pct})
    over.sort(key=lambda r: r["pct"], reverse=True)

    return {
        "largest": ranked[0] if ranked else None,
        "top_5": ranked,
        "top_5_pct": round(sum(r["pct"] for r in ranked), 1),
        "positions_over_threshold": len(over),
        "positions_over": over,
        "threshold_pct": threshold,
        "flag": "concentrated" if over else "diversified",
        "fund_symbols_excluded": sorted(fund_symbols),
    }


def _allocation(summary: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    total_value = summary["total_value"]
    actual = {
        a["asset_type"]: a["pct"] for a in summary["allocation"]
    }

    by_class: Dict[str, float] = {"equity": 0.0, "bond": 0.0, "cash": 0.0, "other": 0.0}
    for h in summary["holdings"]:
        by_class[asset_class(h)] += float(h.get("market_value") or 0.0)
    by_class = {
        k: round(v / total_value * 100, 1) if total_value else 0.0
        for k, v in by_class.items()
    }

    target, target_source = _target_allocation(profile)
    drift: Optional[List[Dict[str, Any]]] = None
    largest_drift = None
    if target:
        drift = [
            {
                "class": cls,
                "actual": by_class.get(cls, 0.0),
                "target": target[cls],
                "drift_pts": round(by_class.get(cls, 0.0) - target[cls], 1),
            }
            for cls in ("equity", "bond", "cash")
        ]
        largest = max(drift, key=lambda d: abs(d["drift_pts"]))
        largest_drift = {
            "class": largest["class"],
            "actual": largest["actual"],
            "target": largest["target"],
            "drift_pts": abs(largest["drift_pts"]),
        }

    holds_funds = any(
        h.get("asset_type") in _FUND_ASSET_TYPES for h in summary["holdings"]
    )

    return {
        "actual": actual,
        "by_class": by_class,
        "target": target,
        "target_source": target_source,
        "drift": drift,
        "largest_drift": largest_drift,
        "etf_caveat": ETF_CAVEAT if holds_funds else None,
    }


def assess(summary: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Concentration, allocation drift against the stated risk, and cash drag.

    ``available`` is False when there is nothing to judge — no positions, or
    no market value on any of them — rather than reporting zeros that read
    like a finding.
    """
    summary = summary if summary is not None else _load_summary()
    if not summary["holdings"] or not summary["total_value"]:
        return {
            "available": False,
            "reason": "No priced positions to assess yet.",
            "concentration": None,
            "allocation": None,
            "cash_drag_pct": None,
        }

    profile = _load_profile()
    allocation = _allocation(summary, profile)
    return {
        "available": True,
        "total_value": summary["total_value"],
        "concentration": _concentration(summary),
        "allocation": allocation,
        "cash_drag_pct": allocation["by_class"].get("cash", 0.0),
    }


# ---------------------------------------------------------------------------
# Trailing mix backtest
# ---------------------------------------------------------------------------

BACKTEST_DISCLAIMER = (
    "Based on today's holdings priced backwards — not your actual return."
)

# One entry per (day, periods, holdings mix). Keyed by day because the figures
# only move once a day and a page refresh should not re-hit Yahoo.
_BACKTEST_CACHE: Dict[Any, Dict[str, Any]] = {}


def clear_backtest_cache() -> None:
    _BACKTEST_CACHE.clear()


def _mix_fingerprint(summary: Dict[str, Any]) -> tuple:
    return tuple(sorted(
        (h.get("symbol"), h.get("asset_type"), float(h.get("market_value") or 0.0))
        for h in summary["holdings"]
    ))


def _unavailable_backtest(reason: str, as_of, unpriceable: List[str]) -> Dict[str, Any]:
    return {
        "available": False,
        "reason": reason,
        "as_of": as_of.isoformat(),
        "periods": {},
        "unpriceable_symbols": unpriceable,
        "benchmark": config.PORTFOLIO_BENCHMARK_SYMBOL,
        "disclaimer": BACKTEST_DISCLAIMER,
    }


async def mix_backtest(
    periods: Optional[tuple] = None,
    summary: Optional[Dict[str, Any]] = None,
    today=None,
) -> Dict[str, Any]:
    """What today's holdings would have returned over trailing windows.

    Not a return. A true time-weighted return needs every buy, sell and
    dividend, and the app has none of that — only current quantities. This
    prices the *current* mix backwards and says so in ``disclaimer``.

    Cash is carried at a 0% return rather than dropped, so the drag it puts on
    the mix is visible instead of being quietly excluded. Below
    ``PORTFOLIO_BACKTEST_MIN_COVERAGE_PCT`` of the portfolio priced, the
    period reports no number and names what it could not price. Offline, the
    whole thing reports ``available: false`` with a reason — never an
    exception, never a blank card.
    """
    from datetime import date

    from agent import market_tools

    today = today or date.today()
    periods = tuple(periods or config.PORTFOLIO_BACKTEST_PERIODS)
    summary = summary if summary is not None else _load_summary()

    if not summary["holdings"] or not summary["total_value"]:
        return _unavailable_backtest("No priced positions to price backwards.", today, [])

    cache_key = (today, periods, _mix_fingerprint(summary))
    cached = _BACKTEST_CACHE.get(cache_key)
    if cached is not None:
        return cached

    benchmark = config.PORTFOLIO_BENCHMARK_SYMBOL
    total_value = summary["total_value"]
    # Cash has no ticker and needs none: its trailing return is 0%.
    cash_value = sum(
        float(h.get("market_value") or 0.0)
        for h in summary["holdings"] if h.get("asset_type") == "cash"
    )
    priced_candidates = [
        h for h in summary["holdings"] if h.get("asset_type") != "cash"
    ]
    symbols = sorted({h["symbol"] for h in priced_candidates})

    out_periods: Dict[str, Any] = {}
    unpriceable: set = set()
    for period in periods:
        try:
            changes = await market_tools.get_price_changes(symbols + [benchmark], period)
        except Exception as e:
            logger.info("Backtest unavailable for %s: %s", period, e)
            _BACKTEST_CACHE.pop(cache_key, None)
            return _unavailable_backtest(
                "Market data is unreachable right now.", today, sorted(unpriceable)
            )

        covered_value = cash_value
        weighted = 0.0
        for h in priced_candidates:
            change = changes.get(h["symbol"])
            value = float(h.get("market_value") or 0.0)
            if change is None:
                unpriceable.add(h["symbol"])
                continue
            covered_value += value
            weighted += value * float(change)

        coverage_pct = round(covered_value / total_value * 100, 1) if total_value else 0.0
        benchmark_change = changes.get(benchmark)
        entry: Dict[str, Any] = {
            "period": period,
            "coverage_pct": coverage_pct,
            "benchmark": benchmark,
            "benchmark_return_pct": (
                round(float(benchmark_change), 2) if benchmark_change is not None else None
            ),
        }
        if coverage_pct < config.PORTFOLIO_BACKTEST_MIN_COVERAGE_PCT or not covered_value:
            entry.update({
                "available": False,
                "mix_return_pct": None,
                "reason": (
                    f"Only {coverage_pct}% of the portfolio could be priced over "
                    f"{period}, so a return figure would describe a different mix."
                ),
            })
        else:
            entry.update({
                "available": True,
                "mix_return_pct": round(weighted / covered_value, 2),
                "reason": None,
            })
        out_periods[period] = entry

    result = {
        "available": any(p["available"] for p in out_periods.values()),
        "reason": None,
        "as_of": today.isoformat(),
        "periods": out_periods,
        "unpriceable_symbols": sorted(unpriceable),
        "benchmark": benchmark,
        "disclaimer": BACKTEST_DISCLAIMER,
    }
    if not result["available"]:
        result["reason"] = "Not enough of the portfolio could be priced."
    _BACKTEST_CACHE[cache_key] = result
    return result
