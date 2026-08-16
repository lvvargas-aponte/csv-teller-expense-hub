"""Rental-property economics: NOI, cash flow, cap rate, DSCR, equity.

Separate from ``analytics.py`` because this needs the properties repo and
the amortization engine, and ``analytics`` is already 1,400 lines scoped to
"shared aggregations over the in-memory stores". Dependency direction is
``properties -> analytics``; the reverse only ever happens inside a function
body (the pattern ``analytics.compute_goal_statuses`` already uses for
``db.accounts_repo``).

Two pieces of rental arithmetic are easy to get wrong and both are load
bearing here:

**NOI excludes debt service.** Net operating income measures the property,
not the financing. Folding the mortgage in makes cap rate meaningless and
lets a cash purchase and a leveraged one look identical.

**Escrowed taxes and insurance belong to operating expenses, not to debt
service.** They arrive bundled in the mortgage payment, so it is tempting to
count the whole payment as debt service — but ``property_tax_annual`` and
``insurance_annual`` are already in the expense model, and counting the
escrow again would double-charge the property. This is why
``loans.escrow_monthly`` is stored separately from ``payment_amount``.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Dict, List, Optional

import amortization
import state
from db import properties_repo

# A property needs this much tagged history before actuals are trusted over
# the pro forma. Six months smooths a quarterly insurance bill and at least
# one maintenance surprise.
_ACTUALS_CONFIDENCE_MONTHS = 6

# Performance thresholds. Each is deliberately a named constant rather than
# a magic number in a conditional, because every one of them is a judgement
# call the user may want to argue with.
_DSCR_UNDERPERFORMING = 1.00     # can't cover its own debt service
_DSCR_WATCH = 1.25               # the standard lender comfort threshold
_EXPENSE_RATIO_WATCH = 0.55      # opex eating >55% of effective gross income
_NEGATIVE_MONTHS_UNDERPERFORMING = 3
_HIGH_EQUITY_PCT = 40.0          # informational: candidate for a cash-out


def new_property_id() -> str:
    """``prop_<hex12>`` — matches the ``goal_<hex12>`` convention."""
    return f"prop_{uuid.uuid4().hex[:12]}"


def new_loan_id() -> str:
    return f"loan_{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# Value / balance resolution
# ---------------------------------------------------------------------------
#
# After the properties feature landed, two places in the codebase could claim
# to know what a house is worth: properties.current_value, and the
# account_details.asset_value field added by the Debt Payoff work ("current
# market value, for 'loan' class — drives equity"). Rather than deprecate
# one, both are resolved here in a documented order, and every reader goes
# through these two functions. Changing the precedence means changing it once.

def resolve_asset_value(loan: Dict[str, Any]) -> Optional[float]:
    """What the asset securing this loan is worth.

    Precedence:
      1. ``properties.current_value`` when the loan is linked to a property —
         the richer model, backed by a valuation timeseries.
      2. ``account_details.asset_value`` for the linked account — keeps auto
         loans and any pre-properties setup working unchanged.
      3. ``None``. Never guess: callers show "add a valuation" rather than
         computing equity against a number nobody supplied.
    """
    property_id = loan.get("property_id")
    if property_id:
        prop = properties_repo.get_repo().get_property(property_id)
        if prop and prop.get("current_value") is not None:
            return float(prop["current_value"])

    account_id = loan.get("account_id")
    if account_id:
        details = state.account_details.get(account_id) or {}
        asset_value = details.get("asset_value")
        if asset_value is not None:
            return float(asset_value)

    return None


def amortized_balance(
    loan: Dict[str, Any], as_of: Optional[date] = None
) -> Optional[float]:
    """Balance implied by the payment schedule as of today.

    Closed-form, so this is cheap enough to call per loan per render.
    Returns None when the loan lacks the dates or terms to place itself on
    a schedule.
    """
    principal = loan.get("original_principal")
    if not principal:
        return None

    first_payment = loan.get("first_payment_date") or loan.get("origination_date")
    if not first_payment:
        return None
    try:
        start = date.fromisoformat(str(first_payment)[:10])
    except ValueError:
        return None

    periods = amortization.current_period_index(start, as_of or date.today())
    if periods < 1:
        return float(principal)

    payment = loan_payment(loan)
    if payment <= 0:
        return None
    return float(amortization.remaining_balance(
        principal, loan.get("interest_rate_pct") or 0, payment, periods
    ))


def resolve_loan_balance(
    loan: Dict[str, Any], as_of: Optional[date] = None
) -> Optional[float]:
    """Outstanding principal on this loan.

    Precedence:
      1. A linked account — refreshed by sync, so it is the freshest truth.
      2. ``current_principal`` — explicitly supplied by the user.
      3. The amortized balance implied by the schedule. Not merely a
         fallback: for a hand-entered loan with no linked account this is
         the only figure that reflects payments already made. Using
         ``original_principal`` here instead understates equity by every
         dollar of principal paid to date — on a six-year-old mortgage that
         is tens of thousands of dollars.
      4. ``original_principal``, when the loan can't be placed on a
         schedule at all.

    Balances are returned positive even though credit-type accounts store
    them as negative ledger values.
    """
    account_id = loan.get("account_id")
    if account_id:
        for acct in state._balances_cache.get("simplefin_accounts", []) or []:
            if acct.get("id") == account_id:
                return abs(float(acct.get("ledger", 0.0) or 0.0))
        manual = state._manual_accounts.get(account_id)
        if manual is not None:
            return abs(float(manual.get("ledger", 0.0) or 0.0))

    if loan.get("current_principal") is not None:
        return float(loan["current_principal"])

    scheduled = amortized_balance(loan, as_of)
    if scheduled is not None:
        return scheduled

    if loan.get("original_principal") is not None:
        return float(loan["original_principal"])
    return None


def loan_payment(loan: Dict[str, Any]) -> float:
    """Scheduled P&I, excluding escrow. Derived when not stored."""
    stored = loan.get("payment_amount")
    if stored is not None:
        return float(stored)
    try:
        return float(amortization.pmt(
            loan.get("original_principal") or 0,
            loan.get("interest_rate_pct") or 0,
            int(loan.get("term_months") or 0),
        ))
    except (ValueError, TypeError):
        return 0.0


def loan_current_split(
    loan: Dict[str, Any], as_of: Optional[date] = None
) -> Dict[str, Any]:
    """Interest vs. principal for the payment due now — goal #6.

    Returns the split plus the running totals, so the UI can say both
    "this month: $412 principal, $1,388 interest" and "you've paid down
    $38,400 of principal so far".
    """
    today = as_of or date.today()
    payment = loan_payment(loan)
    principal = float(loan.get("original_principal") or 0)
    rate = float(loan.get("interest_rate_pct") or 0)

    first_payment = loan.get("first_payment_date") or loan.get("origination_date")
    period = 0
    if first_payment:
        try:
            start = date.fromisoformat(str(first_payment)[:10])
            period = amortization.current_period_index(start, today)
        except ValueError:
            period = 0

    if period < 1 or payment <= 0 or principal <= 0:
        return {
            "period": period, "payment": payment,
            "interest": 0.0, "principal": 0.0,
            "escrow": float(loan.get("escrow_monthly") or 0),
            "balance": resolve_loan_balance(loan),
            "cumulative_principal_paid": 0.0,
        }

    interest, principal_portion = amortization.split_for_period(
        principal=principal, annual_rate_pct=rate,
        payment=payment, period_index=period,
    )
    remaining = float(amortization.remaining_balance(principal, rate, payment, period))
    return {
        "period": period,
        "payment": payment,
        "interest": interest,
        "principal": principal_portion,
        "escrow": float(loan.get("escrow_monthly") or 0),
        "balance": remaining,
        "cumulative_principal_paid": round(principal - remaining, 2),
    }


# ---------------------------------------------------------------------------
# Pro forma economics
# ---------------------------------------------------------------------------

def _pct(value: Any, default: float = 0.0) -> float:
    return float(value) if value is not None else default


def compute_pro_forma(prop: Dict[str, Any], loans: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Monthly economics from the property's configured assumptions.

    Available the moment a property is created, before any transaction has
    been tagged to it. All figures monthly unless the name says otherwise.
    """
    gross_scheduled = (
        float(prop.get("monthly_rent") or 0)
        + float(prop.get("other_monthly_income") or 0)
    )
    # A non-rental contributes no income — a primary residence is a liability
    # on the cash-flow statement, however much equity it holds.
    if (prop.get("status") or "rental") != "rental":
        gross_scheduled = 0.0

    vacancy_loss = gross_scheduled * _pct(prop.get("vacancy_rate_pct")) / 100.0
    egi = gross_scheduled - vacancy_loss

    monthly_rent = float(prop.get("monthly_rent") or 0)
    operating_expenses = (
        float(prop.get("property_tax_annual") or 0) / 12.0
        + float(prop.get("insurance_annual") or 0) / 12.0
        + float(prop.get("hoa_monthly") or 0)
        + float(prop.get("utilities_monthly") or 0)
        + float(prop.get("other_monthly_expense") or 0)
        + egi * _pct(prop.get("mgmt_fee_pct")) / 100.0
        + monthly_rent * _pct(prop.get("maintenance_pct_of_rent")) / 100.0
        + monthly_rent * _pct(prop.get("capex_reserve_pct_of_rent")) / 100.0
    )

    # NOI excludes debt service, by definition.
    noi = egi - operating_expenses

    # Debt service is P&I only. Escrow is already inside operating_expenses
    # via property_tax_annual / insurance_annual; counting it here too would
    # charge the property twice for the same money.
    debt_service = sum(loan_payment(loan) for loan in loans)
    cash_flow = noi - debt_service

    return {
        "gross_scheduled_income": round(gross_scheduled, 2),
        "vacancy_loss": round(vacancy_loss, 2),
        "effective_gross_income": round(egi, 2),
        "operating_expenses": round(operating_expenses, 2),
        "noi": round(noi, 2),
        "debt_service": round(debt_service, 2),
        "cash_flow": round(cash_flow, 2),
        "expense_ratio": round(operating_expenses / egi, 4) if egi > 0 else None,
    }


def compute_actuals(
    property_id: str, months: int = 12, as_of: Optional[date] = None
) -> Dict[str, Any]:
    """Observed inflows and outflows from transactions tagged to this property.

    Uses ``analytics._is_expense`` for direction so "money leaving" means the
    same thing here as everywhere else in the app, including the Discover
    sign inversion and the transfer/non-spending exclusions.
    """
    from analytics import _is_expense, _parse_date_obj, _parse_month_key

    today = as_of or date.today()
    by_month: Dict[str, Dict[str, float]] = {}
    inflow_total = 0.0
    outflow_total = 0.0

    for txn in state.stored_transactions.values():
        if txn.get("property_id") != property_id:
            continue
        parsed = _parse_date_obj(txn.get("date", ""))
        if parsed is None:
            continue
        age_months = (today.year - parsed.year) * 12 + (today.month - parsed.month)
        if age_months < 0 or age_months >= months:
            continue
        try:
            amount = abs(float(txn.get("amount", 0)))
        except (TypeError, ValueError):
            continue

        month_key = _parse_month_key(txn.get("date", ""))
        bucket = by_month.setdefault(month_key, {"inflow": 0.0, "outflow": 0.0})
        if _is_expense(txn):
            bucket["outflow"] += amount
            outflow_total += amount
        else:
            bucket["inflow"] += amount
            inflow_total += amount

    months_of_data = len(by_month)
    if months_of_data == 0:
        confidence = "none"
    elif months_of_data >= _ACTUALS_CONFIDENCE_MONTHS:
        confidence = "high"
    else:
        confidence = "low"

    divisor = months_of_data or 1
    return {
        "months_of_data": months_of_data,
        "confidence": confidence,
        "total_inflow": round(inflow_total, 2),
        "total_outflow": round(outflow_total, 2),
        "avg_monthly_inflow": round(inflow_total / divisor, 2),
        "avg_monthly_outflow": round(outflow_total / divisor, 2),
        "avg_monthly_net": round((inflow_total - outflow_total) / divisor, 2),
        "by_month": {k: {kk: round(vv, 2) for kk, vv in v.items()}
                     for k, v in sorted(by_month.items())},
    }


def compute_property_economics(
    property_id: str, as_of: Optional[date] = None
) -> Optional[Dict[str, Any]]:
    """Full economics for one property: pro forma, actuals, returns, equity.

    Returns pro forma and actuals as separate blocks and names which one the
    headline figures came from via ``basis``. They are never blended — a
    half-real half-assumed number is the kind of thing that looks precise
    and misleads.
    """
    repo = properties_repo.get_repo()
    prop = repo.get_property(property_id)
    if prop is None:
        return None

    loans = repo.list_loans(property_id)
    pro_forma = compute_pro_forma(prop, loans)
    actual = compute_actuals(property_id, as_of=as_of)
    basis = "actual" if actual["confidence"] == "high" else "pro_forma"

    current_value = prop.get("current_value")
    total_debt = 0.0
    for loan in loans:
        balance = resolve_loan_balance(loan)
        if balance is not None:
            total_debt += balance

    equity = None
    ltv = None
    cltv = None
    if current_value:
        equity = round(float(current_value) - total_debt, 2)
        first_lien = sum(
            resolve_loan_balance(l) or 0.0
            for l in loans if int(l.get("lien_position") or 1) == 1
        )
        ltv = round(first_lien / float(current_value) * 100.0, 2)
        cltv = round(total_debt / float(current_value) * 100.0, 2)

    noi = pro_forma["noi"]
    cap_rate = (
        round(noi * 12 / float(current_value) * 100.0, 2)
        if current_value else None
    )

    # Cash invested is only knowable when the purchase was recorded. Returning
    # None beats inventing a denominator.
    cash_invested = None
    purchase_price = prop.get("purchase_price")
    if purchase_price is not None:
        original_debt = sum(
            float(l.get("original_principal") or 0)
            for l in loans if int(l.get("lien_position") or 1) == 1
        )
        cash_invested = (
            float(purchase_price) - original_debt
            + float(prop.get("closing_costs") or 0)
            + float(prop.get("capital_improvements") or 0)
        )
        if cash_invested <= 0:
            cash_invested = None

    cash_on_cash = (
        round(pro_forma["cash_flow"] * 12 / cash_invested * 100.0, 2)
        if cash_invested else None
    )
    annual_debt_service = pro_forma["debt_service"] * 12
    dscr = round(noi * 12 / annual_debt_service, 2) if annual_debt_service > 0 else None

    economics = {
        "property_id": property_id,
        "name": prop.get("name"),
        "status": prop.get("status"),
        "basis": basis,
        "pro_forma": pro_forma,
        "actual": actual,
        "current_value": float(current_value) if current_value is not None else None,
        "total_debt": round(total_debt, 2),
        "equity": equity,
        "equity_pct": (
            round(equity / float(current_value) * 100.0, 2)
            if current_value and equity is not None else None
        ),
        "ltv": ltv,
        "cltv": cltv,
        "cap_rate": cap_rate,
        "cash_on_cash": cash_on_cash,
        "cash_invested": round(cash_invested, 2) if cash_invested else None,
        "dscr": dscr,
        "loan_count": len(loans),
        "ytd_principal_paid": round(sum(
            loan_current_split(loan, as_of).get("cumulative_principal_paid") or 0.0
            for loan in loans
        ), 2),
    }
    economics["performance"] = classify_property_performance(economics)
    return economics


# ---------------------------------------------------------------------------
# Performance classification
# ---------------------------------------------------------------------------

def classify_property_performance(econ: Dict[str, Any]) -> Dict[str, Any]:
    """Rate a property strong / watch / underperforming, with reasons.

    Exists to make "keep every property unless it's performing poorly"
    operational. Deliberately conservative and always accompanied by
    quantified reasons: this flags candidates for a human decision, it does
    NOT recommend selling. Cap-rate comparisons across a handful of
    properties aren't statistically meaningful, so cap rate alone never
    triggers a downgrade.
    """
    reasons: List[str] = []
    rating = "strong"

    def _downgrade(level: str, reason: str) -> None:
        nonlocal rating
        reasons.append(reason)
        if level == "underperforming" or rating == "underperforming":
            rating = "underperforming"
        else:
            rating = "watch"

    if (econ.get("status") or "rental") != "rental":
        return {
            "rating": "not_rated",
            "reasons": ["Not held as a rental, so rental metrics don't apply."],
        }

    actual = econ.get("actual") or {}
    pro_forma = econ.get("pro_forma") or {}

    negative_months = sum(
        1 for month in (actual.get("by_month") or {}).values()
        if month.get("inflow", 0.0) - month.get("outflow", 0.0) < 0
    )
    if negative_months >= _NEGATIVE_MONTHS_UNDERPERFORMING:
        _downgrade(
            "underperforming",
            f"Cash flow was negative in {negative_months} of the last "
            f"{actual.get('months_of_data', 0)} months.",
        )

    cash_flow = pro_forma.get("cash_flow")
    if cash_flow is not None and cash_flow < 0:
        _downgrade(
            "underperforming",
            f"Projected cash flow is ${cash_flow:,.0f}/mo — the property "
            f"costs money to hold.",
        )

    dscr = econ.get("dscr")
    if dscr is not None:
        if dscr < _DSCR_UNDERPERFORMING:
            _downgrade(
                "underperforming",
                f"DSCR is {dscr:.2f} — net operating income doesn't cover "
                f"debt service.",
            )
        elif dscr < _DSCR_WATCH:
            _downgrade(
                "watch",
                f"DSCR is {dscr:.2f}, under the {_DSCR_WATCH:.2f} most lenders "
                f"want to see.",
            )

    expense_ratio = pro_forma.get("expense_ratio")
    if expense_ratio is not None and expense_ratio > _EXPENSE_RATIO_WATCH:
        _downgrade(
            "watch",
            f"Operating expenses are {expense_ratio * 100:.0f}% of effective "
            f"gross income.",
        )

    # No rent arriving on a property that is supposed to be rented.
    if actual.get("months_of_data", 0) >= 2 and actual.get("total_inflow", 0.0) == 0:
        _downgrade(
            "underperforming",
            "No rent recorded in the tagged transactions — possible vacancy.",
        )

    notes: List[str] = []
    equity_pct = econ.get("equity_pct")
    cash_on_cash = econ.get("cash_on_cash")
    if equity_pct is not None and equity_pct >= _HIGH_EQUITY_PCT:
        notes.append(
            f"{equity_pct:.0f}% equity — a candidate for a cash-out refinance "
            f"or HELOC if you want to redeploy it."
        )
    if cash_on_cash is not None and cash_on_cash < 0:
        notes.append(
            f"Cash-on-cash return is {cash_on_cash:.1f}%; compare against what "
            f"the same capital would earn invested."
        )

    if not reasons:
        reasons.append("Covering its costs with no warning signals.")

    return {"rating": rating, "reasons": reasons, "notes": notes}


# ---------------------------------------------------------------------------
# Portfolio rollup
# ---------------------------------------------------------------------------

def compute_portfolio(as_of: Optional[date] = None) -> Dict[str, Any]:
    """Totals across every property — the Properties page header, and the
    ``properties`` block in the advisor's grounding snapshot."""
    repo = properties_repo.get_repo()
    properties = repo.list_properties()

    rows: List[Dict[str, Any]] = []
    for prop in properties:
        econ = compute_property_economics(prop["id"], as_of=as_of)
        if econ is not None:
            rows.append(econ)

    total_value = sum(r["current_value"] or 0.0 for r in rows)
    total_debt = sum(r["total_debt"] for r in rows)
    monthly_cash_flow = sum(r["pro_forma"]["cash_flow"] for r in rows)
    monthly_noi = sum(r["pro_forma"]["noi"] for r in rows)

    underperforming = [
        {"property_id": r["property_id"], "name": r["name"],
         "reasons": r["performance"]["reasons"]}
        for r in rows if r["performance"]["rating"] == "underperforming"
    ]
    watch = [
        {"property_id": r["property_id"], "name": r["name"],
         "reasons": r["performance"]["reasons"]}
        for r in rows if r["performance"]["rating"] == "watch"
    ]

    return {
        "count": len(rows),
        "total_value": round(total_value, 2),
        "total_debt": round(total_debt, 2),
        "total_equity": round(total_value - total_debt, 2),
        "monthly_noi": round(monthly_noi, 2),
        "monthly_cash_flow": round(monthly_cash_flow, 2),
        "annual_cash_flow": round(monthly_cash_flow * 12, 2),
        "ytd_principal_paid": round(sum(r["ytd_principal_paid"] for r in rows), 2),
        "portfolio_ltv": (
            round(total_debt / total_value * 100.0, 2) if total_value > 0 else None
        ),
        "underperforming": underperforming,
        "watch": watch,
        "properties": rows,
    }
