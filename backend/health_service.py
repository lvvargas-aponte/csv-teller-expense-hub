"""Household financial health score — one definition, one caller-facing shape.

The score used to be computed inside the Finances page component, so the
scheduler, the weekly digest and the advisor could not see it, and it was
derived from three separately-fetched payloads that could disagree with each
other. It is household-level aggregation read by more than one caller, so it
belongs beside :mod:`balances_service`.

Version 1 is a straight port of that JavaScript: the same 30/30/40 weights,
the same sub-score curves, the same renormalization over whichever signals
have data. The one input that changed is the spending signal, which now reads
the like-for-like month-to-date comparison instead of holding a partial month
against a complete one.
"""
import logging
from typing import Any, Dict, List, Optional

import analytics
import balances_service
import credit_health_service

logger = logging.getLogger(__name__)

SCORE_VERSION = 1

WEIGHT_NET_WORTH = 30
WEIGHT_UTILIZATION = 30
WEIGHT_SPENDING = 40


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _money(value: float) -> str:
    return f"${value:,.0f}"


def _signal(
    key: str,
    label: str,
    weight: int,
    sub_score: Optional[float],
    detail: str,
) -> Dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "weight": weight,
        "sub_score": sub_score,
        "available": sub_score is not None,
        "detail": detail,
    }


def _net_worth_signal(summary, trend: Dict[str, Any]) -> Dict[str, Any]:
    """30-day net-worth delta as a ratio of the current position."""
    has_trend = bool(trend.get("available"))
    if not has_trend and not summary.accounts:
        return _signal(
            "net_worth_trend", "Net worth direction", WEIGHT_NET_WORTH, None,
            "No accounts yet",
        )

    net_worth = trend.get("current_net_worth")
    if net_worth is None:
        net_worth = summary.net_worth

    delta_30d = trend.get("delta_30d")
    if delta_30d is None:
        # A position but no history to judge it by — a deliberately flat
        # signal rather than a guess in either direction.
        sub = 0.6 if net_worth >= 0 else 0.4
        return _signal(
            "net_worth_trend", "Net worth direction", WEIGHT_NET_WORTH, sub,
            f"{_money(net_worth)} net worth, no 30-day history",
        )

    base = abs(net_worth) or 1.0
    sub = _clamp01(0.5 + (delta_30d / base) * 5)
    sign = "+" if delta_30d >= 0 else "-"
    return _signal(
        "net_worth_trend", "Net worth direction", WEIGHT_NET_WORTH, sub,
        f"{sign}{_money(abs(delta_30d))} over 30 days",
    )


def _utilization_signal(credit: Dict[str, Any]) -> Dict[str, Any]:
    """Overall balance ÷ limit across the household's cards."""
    if not credit.get("accounts"):
        return _signal(
            "credit_utilization", "Credit utilization", WEIGHT_UTILIZATION, None,
            "No credit cards tracked",
        )
    pct = credit.get("overall_utilization_pct") or 0.0
    sub = max(0.0, 1 - pct / 100.0)
    return _signal(
        "credit_utilization", "Credit utilization", WEIGHT_UTILIZATION, sub,
        f"{pct:.0f}% of {_money(credit.get('total_limit') or 0.0)} in limits",
    )


def _spending_signal(comparison: Dict[str, Any]) -> Dict[str, Any]:
    """This month against the same stretch of the prior one — a drop scores high."""
    prior = comparison.get("prior_month_same_period") or 0.0
    current = comparison.get("current_month_to_date") or 0.0
    if prior <= 0:
        return _signal(
            "spending_trend", "Spending trend", WEIGHT_SPENDING, None,
            "Not enough spending history",
        )
    change = (current - prior) / prior
    sub = _clamp01(0.5 - change)
    as_of_day = comparison.get("as_of_day")
    return _signal(
        "spending_trend", "Spending trend", WEIGHT_SPENDING, sub,
        f"{_money(current)} vs {_money(prior)} through day {as_of_day}",
    )


async def compute_health_score() -> Dict[str, Any]:
    """A 0-100 estimate of the household's position, or ``None`` with no data.

    Signals with no data are skipped and the remaining weights renormalized,
    so the score is comparable across households that track different things.
    """
    summary = await balances_service.build_summary()
    trend = analytics.compute_balance_trend()
    credit = await credit_health_service.build()
    comparison = analytics.compute_month_to_date_comparison()

    signals: List[Dict[str, Any]] = [
        _net_worth_signal(summary, trend),
        _utilization_signal(credit),
        _spending_signal(comparison),
    ]

    active = [s for s in signals if s["available"]]
    total_weight = sum(s["weight"] for s in active)
    score = (
        round(sum(s["sub_score"] * s["weight"] for s in active) / total_weight * 100)
        if total_weight
        else None
    )

    return {
        "score": score,
        "version": SCORE_VERSION,
        "signals": signals,
        "missing_signals": [s["key"] for s in signals if not s["available"]],
    }
