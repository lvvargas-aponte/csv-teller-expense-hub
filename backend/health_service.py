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
import statistics
from datetime import date
from typing import Any, Dict, List, Optional

import analytics
import balances_service
import credit_health_service
import state

logger = logging.getLogger(__name__)

SCORE_VERSION = 1

# Months of expenses an emergency fund should cover when the household hasn't
# stated a target of its own. Two earners with no dependents can rebuild faster
# than a household supporting someone, hence the split.
_DEFAULT_RUNWAY_MONTHS = 3
_DEFAULT_RUNWAY_MONTHS_WITH_DEPENDENTS = 6

# Months of completed spending history the expense figure is drawn from.
_EXPENSE_LOOKBACK_MONTHS = 3

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


# ---------------------------------------------------------------------------
# Household ratios — savings rate, emergency runway, debt-to-income
# ---------------------------------------------------------------------------

def _median_monthly_expenses(today: date) -> Optional[float]:
    """Median spend across the last complete months, current month excluded.

    A mean lets one holiday month distort runway and savings rate alike, and
    the in-progress month has to go for the same reason the dashboard stopped
    comparing against it.
    """
    spending = analytics.group_debit_spending()
    current_month = f"{today.year:04d}-{today.month:02d}"
    complete = sorted(m for m in spending if m < current_month)
    if not complete:
        return None
    recent = complete[-_EXPENSE_LOOKBACK_MONTHS:]
    totals = [sum(spending[m].values()) for m in recent]
    return round(statistics.median(totals), 2)


def _resolve_income(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Reconcile stated income against detected income.

    A figure the user typed always wins; detection fills in when the profile
    is blank. Both are reported so the UI can offer the detected number
    instead of quietly averaging two answers into one nobody gave.
    """
    detected = analytics.compute_income_estimate()
    detected_monthly = detected.get("monthly_estimate") or None

    raw_profile_income = profile.get("monthly_income")
    profile_monthly = float(raw_profile_income) if raw_profile_income else None

    if profile_monthly:
        monthly, source, confidence = profile_monthly, "profile", "high"
    elif detected_monthly:
        monthly, source = detected_monthly, "detected"
        confidence = detected.get("confidence", "low")
    else:
        monthly, source, confidence = None, "none", "none"

    return {
        "monthly": monthly,
        "source": source,
        "confidence": confidence,
        "detected_monthly": detected_monthly,
        "profile_monthly": profile_monthly,
    }


def _monthly_debt_payments() -> float:
    """Sum of configured minimum payments across the household's debts.

    Installment loans count here even though they are excluded from revolving
    utilization — a mortgage payment is exactly what debt-to-income measures.
    """
    total = 0.0
    for details in state.account_details.values():
        raw = (details or {}).get("minimum_payment")
        try:
            total += float(raw) if raw is not None else 0.0
        except (TypeError, ValueError):
            continue
    return round(total, 2)


def _target_runway_months(profile: Dict[str, Any]) -> int:
    stated = profile.get("emergency_fund_months")
    if stated:
        return int(stated)
    dependents = profile.get("dependents") or 0
    return (
        _DEFAULT_RUNWAY_MONTHS_WITH_DEPENDENTS if int(dependents) >= 1
        else _DEFAULT_RUNWAY_MONTHS
    )


async def compute_ratios(today: Optional[date] = None) -> Dict[str, Any]:
    """Savings rate, emergency-fund runway and debt-to-income.

    Every input already existed; none of them reached a screen. Ratios that
    need income return ``None`` rather than a number divided by a guess.
    ``today`` is injectable so tests don't reach for a clock.
    """
    today = today or date.today()
    summary = await balances_service.build_summary()
    profile = analytics._load_user_profile() or {}

    income = _resolve_income(profile)
    monthly_income = income["monthly"]
    monthly_expenses = _median_monthly_expenses(today)

    savings_rate_pct = (
        round((monthly_income - monthly_expenses) / monthly_income * 100.0, 1)
        if monthly_income and monthly_expenses is not None
        else None
    )

    cash = round(summary.total_cash, 2)
    target_months = _target_runway_months(profile)
    if monthly_expenses and monthly_expenses > 0:
        months_covered = round(cash / monthly_expenses, 1)
        gap = round(max(0.0, target_months * monthly_expenses - cash), 2)
    else:
        months_covered = None
        gap = None

    debt_payments = _monthly_debt_payments()
    dti_pct = (
        round(debt_payments / monthly_income * 100.0, 1) if monthly_income else None
    )

    return {
        "income": income,
        "savings_rate_pct": savings_rate_pct,
        "monthly_expenses": monthly_expenses,
        "emergency_fund": {
            "cash": cash,
            "months_covered": months_covered,
            "target_months": target_months,
            "gap": gap,
        },
        "monthly_debt_payments": debt_payments,
        "dti_pct": dti_pct,
        "as_of": today.isoformat(),
    }
