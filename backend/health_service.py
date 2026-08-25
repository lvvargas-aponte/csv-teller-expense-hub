"""Household financial health score — one definition, one caller-facing shape.

The score used to be computed inside the Finances page component, so the
scheduler, the weekly digest and the advisor could not see it, and it was
derived from three separately-fetched payloads that could disagree with each
other. It is household-level aggregation read by more than one caller, so it
belongs beside :mod:`balances_service`.

Version 2 scores the household on what an advisor assesses first: emergency
runway, savings rate, credit utilization, debt-to-income and the 90-day
net-worth trend. Version 1 (a port of the page component's JavaScript) weighted
month-over-month spending noise at 40% and contained none of the first four.
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

SCORE_VERSION = 2

# Weights sum to 100; a signal with no data drops out and the rest are
# renormalized over what remains. ``coverage_pct`` reports how much of the
# model actually had data, and below this floor no score is returned at all —
# a confident number built on one input is worse than an honest gap.
WEIGHT_RUNWAY = 25
WEIGHT_SAVINGS = 25
WEIGHT_UTILIZATION = 20
WEIGHT_DTI = 15
WEIGHT_TREND = 15
MIN_COVERAGE_PCT = 50.0

# Sub-score endpoints. Each curve is linear between the two.
SAVINGS_RATE_TARGET_PCT = 20.0     # 1.0 at or above
UTILIZATION_FLOOR_PCT = 80.0       # 0.0 at or above
DTI_COMFORTABLE_PCT = 15.0         # 1.0 at or below
DTI_CEILING_PCT = 43.0             # 0.0 at or above — the lending limit
TREND_BAND = 0.05                  # ±5% of net worth over 90 days

# Months of expenses an emergency fund should cover when the household hasn't
# stated a target of its own. Two earners with no dependents can rebuild faster
# than a household supporting someone, hence the split.
_DEFAULT_RUNWAY_MONTHS = 3
_DEFAULT_RUNWAY_MONTHS_WITH_DEPENDENTS = 6

# Months of completed spending history the expense figure is drawn from.
_EXPENSE_LOOKBACK_MONTHS = 3



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


def _runway_signal(ratios: Dict[str, Any]) -> Dict[str, Any]:
    """Months of expenses the cash on hand covers, against the household's target."""
    fund = ratios.get("emergency_fund") or {}
    covered = fund.get("months_covered")
    target = fund.get("target_months") or _DEFAULT_RUNWAY_MONTHS
    if covered is None:
        return _signal(
            "emergency_runway", "Emergency runway", WEIGHT_RUNWAY, None,
            "No complete month of spending to measure against",
        )
    sub = _clamp01(covered / target) if target else 0.0
    return _signal(
        "emergency_runway", "Emergency runway", WEIGHT_RUNWAY, sub,
        f"{covered:.1f} of {target} months covered",
    )


def _savings_signal(ratios: Dict[str, Any]) -> Dict[str, Any]:
    """Share of income kept — 20% is the target, spending it all scores zero."""
    pct = ratios.get("savings_rate_pct")
    if pct is None:
        return _signal(
            "savings_rate", "Savings rate", WEIGHT_SAVINGS, None,
            "Needs your monthly income",
        )
    sub = _clamp01(pct / SAVINGS_RATE_TARGET_PCT)
    return _signal(
        "savings_rate", "Savings rate", WEIGHT_SAVINGS, sub,
        f"{pct:.0f}% of income kept, target {SAVINGS_RATE_TARGET_PCT:.0f}%",
    )


def _utilization_signal(credit: Dict[str, Any]) -> Dict[str, Any]:
    """Revolving balance ÷ limit. 80% is where lenders stop reading it as noise."""
    pct = credit.get("overall_utilization_pct")
    if pct is None:
        return _signal(
            "credit_utilization", "Credit utilization", WEIGHT_UTILIZATION, None,
            "No card with a credit limit set",
        )
    sub = _clamp01(1 - pct / UTILIZATION_FLOOR_PCT)
    return _signal(
        "credit_utilization", "Credit utilization", WEIGHT_UTILIZATION, sub,
        f"{pct:.0f}% of {_money(credit.get('total_limit') or 0.0)} in limits",
    )


def _dti_signal(ratios: Dict[str, Any]) -> Dict[str, Any]:
    """Minimum payments ÷ income, on the band lenders themselves use."""
    pct = ratios.get("dti_pct")
    if pct is None:
        return _signal(
            "debt_to_income", "Debt-to-income", WEIGHT_DTI, None,
            "Needs your monthly income",
        )
    span = DTI_CEILING_PCT - DTI_COMFORTABLE_PCT
    sub = _clamp01((DTI_CEILING_PCT - pct) / span)
    return _signal(
        "debt_to_income", "Debt-to-income", WEIGHT_DTI, sub,
        f"{pct:.0f}% of income committed, comfortable below {DTI_COMFORTABLE_PCT:.0f}%",
    )


def _trend_signal(trend: Dict[str, Any], real_assets: float = 0.0) -> Dict[str, Any]:
    """90-day net-worth movement as a share of the position.

    The window is 90 days, not 30: a month of household balance-sheet movement
    is mostly paycheck timing, which made the old score swing on nothing.

    When the household holds property, the caveat is spelled out: retyping
    what a house is worth moves this signal exactly as far as three months of
    saving would, and the user should not read one as the other.
    """
    delta = trend.get("delta_90d") if trend.get("available") else None
    if delta is None:
        return _signal(
            "net_worth_trend", "Net worth trend", WEIGHT_TREND, None,
            "Needs 90 days of balance history",
        )
    net_worth = trend.get("current_net_worth") or 0.0
    base = abs(net_worth) or 1.0
    sub = _clamp01(0.5 + (delta / base) / TREND_BAND * 0.5)
    sign = "+" if delta >= 0 else "-"
    detail = f"{sign}{_money(abs(delta))} over 90 days"
    if real_assets > 0:
        detail += " · a property revaluation moves this too, not just spending"
    return _signal("net_worth_trend", "Net worth trend", WEIGHT_TREND, sub, detail)


async def compute_health_score() -> Dict[str, Any]:
    """A 0-100 estimate of the household's position, or ``None`` with too little data.

    Signals with no data are skipped and the remaining weights renormalized;
    ``coverage_pct`` says how much of the model that left. Below
    ``MIN_COVERAGE_PCT`` no score is returned — connecting a credit card should
    not silently redefine what the number means.
    """
    ratios = await compute_ratios()
    credit = await credit_health_service.build()
    trend = analytics.compute_balance_trend()

    signals: List[Dict[str, Any]] = [
        _runway_signal(ratios),
        _savings_signal(ratios),
        _utilization_signal(credit),
        _dti_signal(ratios),
        _trend_signal(
            trend, (ratios.get("emergency_fund") or {}).get("excluded_real_assets") or 0.0
        ),
    ]

    active = [s for s in signals if s["available"]]
    covered_weight = sum(s["weight"] for s in active)
    total_weight = sum(s["weight"] for s in signals)
    coverage_pct = round(covered_weight / total_weight * 100.0, 1) if total_weight else 0.0

    score = (
        round(sum(s["sub_score"] * s["weight"] for s in active) / covered_weight * 100)
        if covered_weight and coverage_pct >= MIN_COVERAGE_PCT
        else None
    )

    return {
        "score": score,
        "version": SCORE_VERSION,
        "coverage_pct": coverage_pct,
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
            # Homes and vehicles are deliberately absent from ``cash`` above.
            # Reporting how much was left out is what lets the UI explain why
            # a six-figure net worth still shows a two-month runway, instead
            # of leaving the two numbers looking inconsistent.
            "excluded_real_assets": round(summary.total_real_assets, 2),
        },
        "monthly_debt_payments": debt_payments,
        "dti_pct": dti_pct,
        "as_of": today.isoformat(),
    }
