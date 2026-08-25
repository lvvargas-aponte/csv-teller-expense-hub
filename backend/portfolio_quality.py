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


_BOND_CATEGORY_WORDS = ("bond", "fixed income", "treasury", "muni", "government")
_CASH_CATEGORY_WORDS = ("money market", "ultrashort")


def class_from_category(category: Optional[str]) -> Optional[str]:
    """Broad class implied by a yfinance fund category, or None if it says nothing.

    Yahoo's category is a Morningstar-style label ("Intermediate Core Bond",
    "Foreign Large Blend"). It is the cheapest fix for the biggest hole in the
    allocation view: without it every fund reads as equity.
    """
    if not category:
        return None
    text = category.lower()
    if any(word in text for word in _CASH_CATEGORY_WORDS):
        return "cash"
    if any(word in text for word in _BOND_CATEGORY_WORDS):
        return "bond"
    return "equity"


def asset_class(holding: Dict[str, Any], fund_classes: Optional[Dict[str, str]] = None) -> str:
    """Broad class for one holding — the fund's own category wins when known."""
    known = (fund_classes or {}).get(holding.get("symbol"))
    if known:
        return known
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


def _allocation(
    summary: Dict[str, Any],
    profile: Dict[str, Any],
    fund_classes: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    total_value = summary["total_value"]
    actual = {
        a["asset_type"]: a["pct"] for a in summary["allocation"]
    }

    by_class: Dict[str, float] = {"equity": 0.0, "bond": 0.0, "cash": 0.0, "other": 0.0}
    for h in summary["holdings"]:
        by_class[asset_class(h, fund_classes)] += float(h.get("market_value") or 0.0)
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

    # The caveat is per-portfolio and drops away once every fund's category
    # is known — a fund we can place properly is no longer "counted as equity".
    uncategorized_funds = any(
        h.get("asset_type") in _FUND_ASSET_TYPES
        and not (fund_classes or {}).get(h.get("symbol"))
        for h in summary["holdings"]
    )

    return {
        "actual": actual,
        "by_class": by_class,
        "target": target,
        "target_source": target_source,
        "drift": drift,
        "largest_drift": largest_drift,
        "etf_caveat": ETF_CAVEAT if uncategorized_funds else None,
    }


def _cached_fund_classes(summary: Dict[str, Any]) -> Dict[str, str]:
    """Fund classes from whatever the profile cache already holds.

    Cache-only, never a fetch: this card has to render with the machine
    offline, so it uses categories it happens to know and falls back to the
    asset-type mapping (plus the caveat) for the rest.
    """
    try:
        from agent import market_tools

        symbols = [h["symbol"] for h in summary["holdings"]]
        return {
            symbol: cls
            for symbol, profile in market_tools.cached_fund_profiles(symbols).items()
            if (cls := class_from_category(profile.get("category")))
        }
    except Exception:
        logger.warning("Could not read cached fund categories", exc_info=True)
        return {}


def assess(
    summary: Optional[Dict[str, Any]] = None,
    fund_classes: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
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
    if fund_classes is None:
        fund_classes = _cached_fund_classes(summary)
    allocation = _allocation(summary, profile, fund_classes)
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


# ---------------------------------------------------------------------------
# Fees
# ---------------------------------------------------------------------------

async def fee_summary(summary: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """What the portfolio costs in fund fees, in dollars a year.

    Unlike a return, this is knowable in advance, which makes it the most
    actionable number on the page. A holding with no expense ratio — an
    individual stock, or a fund Yahoo doesn't cover — is left out of the
    weighting entirely rather than counted as a free 0%, which would drag the
    average toward a figure nobody is actually paying.
    """
    from agent import market_tools

    summary = summary if summary is not None else _load_summary()
    holdings = [h for h in summary["holdings"] if h.get("asset_type") != "cash"]
    if not holdings:
        return _no_fees("No fund holdings to price.")

    symbols = sorted({h["symbol"] for h in holdings})
    try:
        profiles = await market_tools.get_fund_profiles(symbols)
    except Exception as e:
        logger.info("Fund profiles unavailable: %s", e)
        return _no_fees("Fund data is unreachable right now.")

    rows: List[Dict[str, Any]] = []
    fund_value = 0.0
    annual_cost = 0.0
    unpriced: List[str] = []
    fund_classes: Dict[str, str] = {}
    for h in holdings:
        profile = profiles.get(h["symbol"]) or {}
        cls = class_from_category(profile.get("category"))
        if cls:
            fund_classes[h["symbol"]] = cls
        ratio = profile.get("expense_ratio_pct")
        value = float(h.get("market_value") or 0.0)
        if ratio is None:
            unpriced.append(h["symbol"])
            continue
        cost = value * float(ratio) / 100
        fund_value += value
        annual_cost += cost
        rows.append({
            "symbol": h["symbol"],
            "value": round(value, 2),
            "expense_ratio_pct": round(float(ratio), 3),
            "annual_cost": round(cost, 2),
            "high": float(ratio) > config.PORTFOLIO_HIGH_FEE_PCT,
        })

    if not rows or not fund_value:
        out = _no_fees("No fund holdings to price.")
        out["unpriced_symbols"] = sorted(set(unpriced))
        out["fund_classes"] = fund_classes
        return out

    rows.sort(key=lambda r: r["annual_cost"], reverse=True)
    return {
        "available": True,
        "reason": None,
        "annual_fee_cost": round(annual_cost, 2),
        "weighted_expense_ratio_pct": round(annual_cost / fund_value * 100, 4),
        "funds_priced": len(rows),
        "fund_value": round(fund_value, 2),
        "holdings": rows,
        "high_fee_threshold_pct": config.PORTFOLIO_HIGH_FEE_PCT,
        "unpriced_symbols": sorted(set(unpriced)),
        "fund_classes": fund_classes,
    }


def _no_fees(reason: str) -> Dict[str, Any]:
    return {
        "available": False,
        "reason": reason,
        "annual_fee_cost": None,
        "weighted_expense_ratio_pct": None,
        "funds_priced": 0,
        "fund_value": 0.0,
        "holdings": [],
        "high_fee_threshold_pct": config.PORTFOLIO_HIGH_FEE_PCT,
        "unpriced_symbols": [],
        "fund_classes": {},
    }
