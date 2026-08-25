"""Retirement contributions and the projection built on them.

Contributions are the single most sensitive input to any projection, and a
number the user types once and never revisits is how these features rot. Two
signals already exist in ``analytics`` and are combined here rather than
duplicated:

* ``detect_recurring_inbound_transfers`` — money the user tagged as flowing
  into an investment account. Precise, because the tag says where it went.
* ``_compute_account_velocity`` — the slope of the balance snapshots. Catches
  employer 401(k) contributions, which never appear as a transaction anywhere.

The two describe the same dollars whenever both fire, so an account takes one
or the other, never their sum.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional

import config
import health_service
import tax

logger = logging.getLogger(__name__)

# Velocity over a single month is dominated by whichever day the market moved.
# A quarter is long enough that a regular contribution shows through and short
# enough to still describe the user's current behaviour.
_VELOCITY_WINDOW_DAYS = 90

VELOCITY_CAVEAT = (
    "Estimated from the account's balance history, so it includes market "
    "movement as well as contributions."
)


async def _load_investment_accounts() -> List[Any]:
    import balances_service
    from analytics import classify_account_bucket

    summary = await balances_service.build_summary()
    return [
        a for a in summary.accounts
        if classify_account_bucket(a.type, a.subtype) == "investment"
    ]


def _transfer_monthly_by_account(account_ids: set) -> Dict[str, float]:
    """Monthly contribution per account from tagged recurring transfers."""
    import analytics

    out: Dict[str, float] = {}
    for stream in analytics.detect_recurring_inbound_transfers(
        include_tagged_transfers=True
    ):
        account_id = stream.get("account_id")
        if account_id not in account_ids:
            continue
        out[account_id] = round(
            out.get(account_id, 0.0) + float(stream["monthly_estimate"]), 2
        )
    return out


def _account_balance(account: Any) -> float:
    return float(account.available or 0.0) or float(account.ledger or 0.0)


def _velocity_monthly(account_id: str, snapshots: List[Dict[str, Any]]) -> Optional[float]:
    import analytics

    velocity = analytics._compute_account_velocity(
        account_id, snapshots, days=_VELOCITY_WINDOW_DAYS
    )
    if velocity is None or velocity <= 0:
        return None
    return velocity


async def estimate_contributions() -> Dict[str, Any]:
    """What is actually going into the retirement accounts each month.

    Shape::

        {"monthly_total": 1450.0,
         "by_account": [{"account_id", "name", "monthly", "method",
                         "confidence"}],
         "confidence": "high" | "low" | "none",
         "caveat": str | None}

    ``method`` records which signal produced the row so the UI can say so.
    Velocity rows are ``confidence: "low"`` because a rising 401(k) balance is
    contributions *plus* market return; separating the two needs holding-level
    history the app does not have, so the caveat is carried instead of a
    correction that would only look precise.
    """
    from db.accounts_repo import get_repo

    accounts = await _load_investment_accounts()
    by_id = {a.id: a for a in accounts}
    if not by_id:
        return {
            "monthly_total": 0.0, "by_account": [],
            "confidence": "none", "caveat": None,
        }

    transfers = _transfer_monthly_by_account(set(by_id))

    snapshots: List[Dict[str, Any]] = []
    if len(transfers) < len(by_id):
        try:
            snapshots = get_repo().get_snapshots_since(_VELOCITY_WINDOW_DAYS + 1)
        except Exception as e:
            logger.debug(f"[retirement] snapshot read skipped: {e}")

    rows: List[Dict[str, Any]] = []
    for account_id, account in by_id.items():
        monthly = transfers.get(account_id)
        method = "recurring_transfer"
        if monthly is None:
            monthly = _velocity_monthly(account_id, snapshots)
            method = "snapshot_velocity"
        if monthly is None:
            continue
        rows.append({
            "account_id": account_id,
            "name": account.name,
            "monthly": round(monthly, 2),
            "method": method,
            "confidence": "high" if method == "recurring_transfer" else "low",
        })

    rows.sort(key=lambda r: r["monthly"], reverse=True)
    uses_velocity = any(r["method"] == "snapshot_velocity" for r in rows)
    if not rows:
        confidence = "none"
    elif all(r["confidence"] == "high" for r in rows):
        confidence = "high"
    else:
        # A mixed set is only as trustworthy as its weakest row.
        confidence = "low"

    return {
        "monthly_total": round(sum(r["monthly"] for r in rows), 2),
        "by_account": rows,
        "confidence": confidence,
        "caveat": VELOCITY_CAVEAT if uses_velocity else None,
    }


def _load_profile() -> Optional[Dict[str, Any]]:
    """The raw household profile row, or None when nothing has been answered.

    Deliberately not ``analytics._load_user_profile``: that one curates the
    row for prompt context and drops fields this module needs.
    """
    try:
        from db import profile_repo

        return profile_repo.load()
    except Exception as e:
        logger.debug(f"[retirement] user_profile read skipped: {e}")
        return None


def _future_value(balance: float, annual_contribution: float, rate: float, years: int) -> float:
    """Compound ``balance`` and an annual contribution for ``years`` at ``rate``.

    An ordinary annuity — the year's contribution lands at year end. Written
    out rather than pulled from a library so the arithmetic on screen and the
    arithmetic here are the same three terms.
    """
    growth = (1.0 + rate) ** years
    if rate == 0:
        return round(balance + annual_contribution * years, 2)
    return round(balance * growth + annual_contribution * (growth - 1.0) / rate, 2)


def _required_annual_contribution(
    balance: float, target: float, rate: float, years: int
) -> Optional[float]:
    """Invert ``_future_value`` for the contribution that reaches ``target``."""
    if years <= 0:
        return None
    growth = (1.0 + rate) ** years
    if rate == 0:
        return max((target - balance) / years, 0.0)
    factor = (growth - 1.0) / rate
    if factor <= 0:
        return None
    return max((target - balance * growth) / factor, 0.0)


def _resolve_return(profile: Dict[str, Any]) -> tuple:
    """``(nominal_pct, source)`` — the user's own figure, or their risk band."""
    stated = profile.get("expected_return_pct")
    if stated is not None:
        return float(stated), "profile"
    risk = (profile.get("risk_tolerance") or "").strip().lower()
    if risk in config.RETIREMENT_RETURN_PCT_BY_RISK:
        return config.RETIREMENT_RETURN_PCT_BY_RISK[risk], "risk_tolerance"
    return None, "none"


def _resolve_target_spend(profile: Dict[str, Any], today) -> tuple:
    """``(annual_spend, source)`` in today's dollars.

    The fallback is a stated share of what the household spends now, and it
    labels itself as an estimate — the card says which of the two it is.
    """
    stated = profile.get("annual_retirement_spend")
    if stated is not None:
        return float(stated), "profile"
    monthly = health_service._median_monthly_expenses(today)
    if monthly:
        return (
            round(monthly * 12 * config.RETIREMENT_SPEND_SHARE_OF_TODAY, 2),
            "estimated_from_expenses",
        )
    return None, "none"


def _unavailable(missing: List[str], assumptions: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "available": False,
        "missing": missing,
        "years_to_retirement": None,
        "retirement_age": None,
        "current_balance": None,
        "balance_split": None,
        "monthly_contribution": None,
        "contribution_confidence": None,
        "contribution_caveat": None,
        "target_pot": None,
        "target_annual_spend": None,
        "scenarios": None,
        "base_shortfall": None,
        "low_shortfall": None,
        "required_monthly_for_target": None,
        "assumptions": assumptions,
    }


async def project(
    today=None,
    inflation_pct: Optional[float] = None,
    withdrawal_rate_pct: Optional[float] = None,
) -> Dict[str, Any]:
    """Project the retirement pot in today's dollars, as a three-point band.

    Real returns, not nominal: inflation is subtracted from the return and the
    target is never inflated, so every figure is comparable to what a dollar
    buys now. Three scenarios rather than one, because the inputs do not
    support a single number. No simulation — deterministic compounding with
    the assumptions visible is the honest shape for inputs this soft.

    ``available`` is False and ``missing`` names the fields whenever an input
    the user has to supply is absent. Nothing is silently defaulted.

    ``inflation_pct`` and ``withdrawal_rate_pct`` override the house constants
    for this call only — the card lets the user test a different assumption
    without storing one.
    """
    today = today or date.today()
    profile = _load_profile() or {}

    missing: List[str] = []
    birth_year = profile.get("birth_year")
    if birth_year is None:
        missing.append("birth_year")
    target_age = profile.get("target_retirement_age")
    if target_age is None:
        missing.append("target_retirement_age")

    nominal_pct, return_source = _resolve_return(profile)
    if nominal_pct is None:
        missing.append("risk_tolerance")

    target_spend, spend_source = _resolve_target_spend(profile, today)
    if target_spend is None:
        missing.append("annual_retirement_spend")

    inflation_pct = (
        config.RETIREMENT_INFLATION_PCT if inflation_pct is None else float(inflation_pct)
    )
    withdrawal_pct = (
        config.RETIREMENT_WITHDRAWAL_RATE_PCT
        if withdrawal_rate_pct is None else float(withdrawal_rate_pct)
    )
    assumptions = {
        "nominal_return_pct": nominal_pct,
        "inflation_pct": inflation_pct,
        "real_return_pct": (
            round(nominal_pct - inflation_pct, 4) if nominal_pct is not None else None
        ),
        "withdrawal_rate_pct": withdrawal_pct,
        "scenario_spread_pct": config.RETIREMENT_SCENARIO_SPREAD_PCT,
        "source": return_source,
        "target_spend_source": spend_source,
    }

    if missing:
        return _unavailable(missing, assumptions)

    retirement_year = int(birth_year) + int(target_age)
    years = max(retirement_year - today.year, 0)

    accounts = await _load_investment_accounts()
    # A taxable brokerage is savings, not a retirement pot, and counting it
    # here quietly moves the retirement date. Once accounts carry a tax
    # treatment the projection runs on the retirement-labelled ones and
    # reports what it left out; with no labels at all it falls back to every
    # investment account rather than projecting from zero.
    retirement_ids = {a.id for a in accounts if tax.is_retirement(a)}
    pool = [a for a in accounts if a.id in retirement_ids] or accounts
    current_balance = round(sum(_account_balance(a) for a in pool), 2)
    balance_split = {
        "retirement": round(
            sum(_account_balance(a) for a in accounts if a.id in retirement_ids), 2
        ),
        "other": round(
            sum(_account_balance(a) for a in accounts if a.id not in retirement_ids), 2
        ),
        "basis": "tax_treatment" if retirement_ids else "all_investments",
    }

    contributions = await estimate_contributions()
    monthly = float(contributions["monthly_total"])
    annual = monthly * 12

    real_pct = assumptions["real_return_pct"]
    spread = config.RETIREMENT_SCENARIO_SPREAD_PCT
    scenarios = {
        "low": _future_value(current_balance, annual, (real_pct - spread) / 100.0, years),
        "base": _future_value(current_balance, annual, real_pct / 100.0, years),
        "high": _future_value(current_balance, annual, (real_pct + spread) / 100.0, years),
    }

    target_pot = round(target_spend / (withdrawal_pct / 100.0), 2)
    required_annual = _required_annual_contribution(
        current_balance, target_pot, real_pct / 100.0, years
    )

    def shortfall(value: float) -> Optional[float]:
        gap = round(target_pot - value, 2)
        return gap if gap > 0 else None

    return {
        "available": True,
        "missing": [],
        "years_to_retirement": years,
        "retirement_age": int(target_age),
        "current_balance": current_balance,
        "balance_split": balance_split,
        "monthly_contribution": round(monthly, 2),
        "contribution_confidence": contributions["confidence"],
        "contribution_caveat": contributions["caveat"],
        "contribution_by_account": contributions["by_account"],
        "target_pot": target_pot,
        "target_annual_spend": round(target_spend, 2),
        "scenarios": scenarios,
        "base_shortfall": shortfall(scenarios["base"]),
        "low_shortfall": shortfall(scenarios["low"]),
        "required_monthly_for_target": (
            round(required_annual / 12, 2) if required_annual is not None else None
        ),
        "assumptions": assumptions,
    }
