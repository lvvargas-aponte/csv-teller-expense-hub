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
        + float(prop.get("landscaping_monthly") or 0)
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
# Equity capacity
# ---------------------------------------------------------------------------
#
# Lenders cap what you can borrow against a property as a percentage of its
# value. Cash-out refinances typically stop at 75% LTV on an investment
# property; a HELOC sitting behind a first mortgage typically reaches 85%
# CLTV. Both are conventions, not laws, so both are parameters.
#
# The important thing this module does is refuse to show the extractable
# figure alone. Pulling equity out raises the payment, and on a property
# with thin margins that can flip cash flow negative — turning an asset that
# pays you into one you subsidize. The new payment and the resulting cash
# flow are computed alongside the proceeds, and the UI is expected to show
# them together.

_DEFAULT_CASH_OUT_LTV = 75.0
_DEFAULT_HELOC_CLTV = 85.0
# Refinance closing costs as a share of the new loan. Surfaced in the payload
# rather than silently netted off, so the figure can be argued with.
_REFI_COST_PCT = 2.0
# Used when the caller doesn't supply a rate for the new money.
_ASSUMED_REFI_RATE_PCT = 7.0
_ASSUMED_HELOC_RATE_PCT = 8.5


def compute_usable_equity(
    property_id: str,
    *,
    max_ltv_pct: float = _DEFAULT_CASH_OUT_LTV,
    max_cltv_pct: float = _DEFAULT_HELOC_CLTV,
    refi_rate_pct: float = _ASSUMED_REFI_RATE_PCT,
    heloc_rate_pct: float = _ASSUMED_HELOC_RATE_PCT,
    refi_term_months: int = 360,
    as_of: Optional[date] = None,
) -> Dict[str, Any]:
    """What could be borrowed against one property, and what it would cost.

    Returns two scenarios. Neither is a recommendation: both report the
    payment increase and the cash flow that survives it, because the
    extractable number on its own is the most misleading figure in real
    estate.
    """
    repo = properties_repo.get_repo()
    prop = repo.get_property(property_id)
    if prop is None:
        return {"available": False, "reason": "not_found"}

    value = prop.get("current_value")
    if not value:
        return {
            "available": False,
            "reason": "no_valuation",
            "property_id": property_id,
            "name": prop.get("name"),
            "detail": (
                "Record a current value for this property and its borrowing "
                "capacity can be calculated."
            ),
        }

    value = float(value)
    loans = repo.list_loans(property_id)
    total_debt = sum(resolve_loan_balance(loan, as_of) or 0.0 for loan in loans)
    existing_payment = sum(loan_payment(loan) for loan in loans)

    econ = compute_property_economics(property_id, as_of=as_of) or {}
    noi = (econ.get("pro_forma") or {}).get("noi", 0.0)
    current_cash_flow = (econ.get("pro_forma") or {}).get("cash_flow", 0.0)

    # --- cash-out refinance: the whole balance is replaced -------------------
    refi_ceiling = value * max_ltv_pct / 100.0
    gross_proceeds = max(0.0, refi_ceiling - total_debt)
    closing_costs = refi_ceiling * _REFI_COST_PCT / 100.0 if gross_proceeds > 0 else 0.0
    net_proceeds = max(0.0, gross_proceeds - closing_costs)

    if gross_proceeds > 0:
        new_payment = float(amortization.pmt(refi_ceiling, refi_rate_pct, refi_term_months))
    else:
        new_payment = existing_payment
    payment_delta = new_payment - existing_payment
    cash_flow_after = current_cash_flow - payment_delta
    dscr_after = (
        round(noi * 12 / (new_payment * 12), 2) if new_payment > 0 else None
    )

    # --- HELOC: sits behind the existing debt, drawn interest-only ----------
    heloc_ceiling = value * max_cltv_pct / 100.0
    heloc_line = max(0.0, heloc_ceiling - total_debt)
    heloc_interest_only = heloc_line * heloc_rate_pct / 100.0 / 12.0
    heloc_cash_flow_after = current_cash_flow - heloc_interest_only

    return {
        "available": True,
        "property_id": property_id,
        "name": prop.get("name"),
        "current_value": round(value, 2),
        "total_debt": round(total_debt, 2),
        "equity": round(value - total_debt, 2),
        "current_ltv": round(total_debt / value * 100.0, 2),
        "current_cash_flow": round(current_cash_flow, 2),
        "cash_out_refi": {
            "max_ltv_pct": max_ltv_pct,
            "rate_pct": refi_rate_pct,
            "term_months": refi_term_months,
            "new_loan_amount": round(refi_ceiling, 2),
            "gross_proceeds": round(gross_proceeds, 2),
            "estimated_closing_costs": round(closing_costs, 2),
            "closing_cost_pct": _REFI_COST_PCT,
            "net_proceeds": round(net_proceeds, 2),
            "current_payment": round(existing_payment, 2),
            "new_payment": round(new_payment, 2),
            "payment_delta": round(payment_delta, 2),
            "cash_flow_after": round(cash_flow_after, 2),
            "dscr_after": dscr_after,
            "kills_cash_flow": cash_flow_after < 0 <= current_cash_flow,
        },
        "heloc": {
            "max_cltv_pct": max_cltv_pct,
            "rate_pct": heloc_rate_pct,
            "max_line": round(heloc_line, 2),
            "interest_only_payment": round(heloc_interest_only, 2),
            "cash_flow_after_full_draw": round(heloc_cash_flow_after, 2),
            "kills_cash_flow": heloc_cash_flow_after < 0 <= current_cash_flow,
            "rate_type": "variable",
            "note": (
                "HELOC rates float. The payment shown is interest-only on a "
                "full draw at today's rate; both can rise."
            ),
        },
    }


def compute_portfolio_equity(
    *, max_ltv_pct: float = _DEFAULT_CASH_OUT_LTV,
    max_cltv_pct: float = _DEFAULT_HELOC_CLTV,
    as_of: Optional[date] = None,
) -> Dict[str, Any]:
    """Borrowing capacity across every property."""
    repo = properties_repo.get_repo()
    rows: List[Dict[str, Any]] = []
    unavailable: List[Dict[str, Any]] = []

    for prop in repo.list_properties():
        capacity = compute_usable_equity(
            prop["id"], max_ltv_pct=max_ltv_pct,
            max_cltv_pct=max_cltv_pct, as_of=as_of,
        )
        if capacity.get("available"):
            rows.append(capacity)
        else:
            unavailable.append({
                "property_id": prop["id"],
                "name": prop.get("name"),
                "reason": capacity.get("reason"),
            })

    return {
        "count": len(rows),
        "total_equity": round(sum(r["equity"] for r in rows), 2),
        "total_cash_out_available": round(
            sum(r["cash_out_refi"]["net_proceeds"] for r in rows), 2
        ),
        "total_heloc_available": round(
            sum(r["heloc"]["max_line"] for r in rows), 2
        ),
        "properties": rows,
        # Named rather than silently dropped — a property missing a valuation
        # would otherwise just reduce the total with no explanation.
        "needs_valuation": unavailable,
    }


# ---------------------------------------------------------------------------
# Deal analyzer
# ---------------------------------------------------------------------------

def analyze_deal(inputs: Dict[str, Any], as_of: Optional[date] = None) -> Dict[str, Any]:
    """Model a hypothetical purchase.

    The headline figure is ``net_effect.portfolio_cash_flow_delta``, not the
    deal's own cash flow. When the down payment comes from a HELOC or
    cash-out refinance on a property you already own, that borrowing has a
    carrying cost — and a deal that looks positive standalone can still
    reduce total monthly income. Portfolio-level is the honest frame for a
    leverage question.
    """
    price = float(inputs.get("purchase_price") or 0)
    if price <= 0:
        return {"available": False, "reason": "purchase_price_required"}

    down_pct = float(inputs.get("down_pct") or 25.0)
    rate = float(inputs.get("rate_pct") or _ASSUMED_REFI_RATE_PCT)
    term = int(inputs.get("term_months") or 360)
    rent = float(inputs.get("monthly_rent") or 0)
    vacancy_pct = float(inputs.get("vacancy_pct") or 5.0)
    opex_pct = float(inputs.get("opex_pct") or 35.0)
    closing_pct = float(inputs.get("closing_pct") or 3.0)
    rehab = float(inputs.get("rehab") or 0)

    down = price * down_pct / 100.0
    financed = price - down
    closing = price * closing_pct / 100.0
    cash_needed = down + closing + rehab

    payment = float(amortization.pmt(financed, rate, term)) if financed > 0 else 0.0

    egi = rent * (1 - vacancy_pct / 100.0)
    opex = egi * opex_pct / 100.0
    noi = egi - opex
    cash_flow = noi - payment

    cap_rate = round(noi * 12 / price * 100.0, 2) if price > 0 else None
    coc = round(cash_flow * 12 / cash_needed * 100.0, 2) if cash_needed > 0 else None
    dscr = round(noi * 12 / (payment * 12), 2) if payment > 0 else None

    # Rent at which the deal exactly covers itself.
    denominator = (1 - vacancy_pct / 100.0) * (1 - opex_pct / 100.0)
    break_even_rent = round(payment / denominator, 2) if denominator > 0 else None

    # --- funding, and what it costs elsewhere -------------------------------
    funded_from = (inputs.get("funded_from") or "cash").lower()
    source_property_id = inputs.get("source_property_id")
    borrowing_cost = 0.0
    funding_note = "Assumes the cash is already on hand."

    if funded_from in ("heloc", "cash_out_refi") and source_property_id:
        capacity = compute_usable_equity(source_property_id, as_of=as_of)
        if capacity.get("available"):
            if funded_from == "heloc":
                line_rate = capacity["heloc"]["rate_pct"]
                borrowing_cost = cash_needed * line_rate / 100.0 / 12.0
                funding_note = (
                    f"Drawing ${cash_needed:,.0f} on the HELOC against "
                    f"{capacity['name']} costs about ${borrowing_cost:,.0f}/mo "
                    f"in interest at {line_rate:.2f}%."
                )
            else:
                borrowing_cost = capacity["cash_out_refi"]["payment_delta"]
                funding_note = (
                    f"Refinancing {capacity['name']} raises its payment by "
                    f"${borrowing_cost:,.0f}/mo."
                )

    portfolio_delta = cash_flow - borrowing_cost

    # --- sensitivity: three deterministic knocks ----------------------------
    def _cash_flow_with(rent_v, vacancy_v, rate_v) -> float:
        egi_v = rent_v * (1 - vacancy_v / 100.0)
        noi_v = egi_v - egi_v * opex_pct / 100.0
        pay_v = float(amortization.pmt(financed, rate_v, term)) if financed > 0 else 0.0
        return round(noi_v - pay_v, 2)

    sensitivity = [
        {
            "label": "Rent 10% below plan",
            "cash_flow": _cash_flow_with(rent * 0.9, vacancy_pct, rate),
        },
        {
            "label": "Vacancy 5 points worse",
            "cash_flow": _cash_flow_with(rent, vacancy_pct + 5, rate),
        },
        {
            "label": "Rate 1 point higher",
            "cash_flow": _cash_flow_with(rent, vacancy_pct, rate + 1),
        },
    ]

    # --- guardrails, rendered above the attractive numbers ------------------
    warnings: List[str] = []
    if cash_flow < 0:
        warnings.append(
            f"This property loses ${abs(cash_flow):,.0f} a month on its own."
        )
    if portfolio_delta < 0 <= cash_flow:
        warnings.append(
            f"The deal is positive standalone, but the borrowing behind it "
            f"costs more than it earns — portfolio cash flow drops "
            f"${abs(portfolio_delta):,.0f} a month."
        )
    if dscr is not None and dscr < 1.25:
        warnings.append(
            f"DSCR of {dscr:.2f} is under the 1.25 most lenders want to see."
        )
    if any(s["cash_flow"] < 0 for s in sensitivity):
        broken = [s["label"].lower() for s in sensitivity if s["cash_flow"] < 0]
        warnings.append(
            f"Cash flow turns negative if {', or '.join(broken)}."
        )

    return {
        "available": True,
        "inputs": {
            "purchase_price": price, "down_pct": down_pct, "rate_pct": rate,
            "term_months": term, "monthly_rent": rent, "vacancy_pct": vacancy_pct,
            "opex_pct": opex_pct, "closing_pct": closing_pct, "rehab": rehab,
            "funded_from": funded_from, "source_property_id": source_property_id,
        },
        "financing": {
            "down_payment": round(down, 2),
            "financed": round(financed, 2),
            "closing_costs": round(closing, 2),
            "rehab": round(rehab, 2),
            "total_cash_needed": round(cash_needed, 2),
            "monthly_payment": round(payment, 2),
        },
        "economics": {
            "effective_gross_income": round(egi, 2),
            "operating_expenses": round(opex, 2),
            "noi": round(noi, 2),
            "cash_flow": round(cash_flow, 2),
        },
        "returns": {
            "cap_rate": cap_rate,
            "cash_on_cash": coc,
            "dscr": dscr,
            "break_even_rent": break_even_rent,
        },
        "net_effect": {
            "deal_cash_flow": round(cash_flow, 2),
            "borrowing_cost": round(borrowing_cost, 2),
            "portfolio_cash_flow_delta": round(portfolio_delta, 2),
            "funding_note": funding_note,
        },
        "sensitivity": sensitivity,
        "warnings": warnings,
        "assumptions": {
            "opex_pct_of_egi": opex_pct,
            "note": (
                "Operating expenses are modeled as a share of collected rent. "
                "Once you own it, the property's own expense model replaces "
                "this estimate."
            ),
        },
    }


# ---------------------------------------------------------------------------
# Transaction attribution
# ---------------------------------------------------------------------------

def suggest_property_for_transactions(
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """Propose property tags for untagged transactions.

    Three matchers, in precedence order:

      1. ``operating_account_id`` — everything on a property's dedicated
         account belongs to it.
      2. ``rules[]`` with ``match: "merchant_key"`` — compared through
         ``analytics._normalize_merchant``, which is what collapses
         ``ZELLE FROM TENANT J SMITH 0421`` into one stable key across
         months. Reusing that pipeline rather than writing a second matcher
         means tenant payments group the same way recurring charges do.
      3. ``rules[]`` with ``match: "description_contains"`` — a plain
         case-insensitive substring, for the cases the normalizer can't
         generalize.

    Returns suggestions only. Nothing here writes ``property_id``: a
    mis-attributed rent payment silently distorts NOI, cash flow and
    ultimately the retirement projection, so a human confirms each one.
    """
    from analytics import _normalize_merchant

    repo = properties_repo.get_repo()
    properties = repo.list_properties()
    if not properties:
        return []

    by_account: Dict[str, str] = {}
    merchant_rules: List[tuple] = []
    substring_rules: List[tuple] = []
    for prop in properties:
        if prop.get("operating_account_id"):
            by_account[prop["operating_account_id"]] = prop["id"]
        for rule in prop.get("rules") or []:
            match_type = (rule.get("match") or "").strip()
            value = (rule.get("value") or "").strip()
            if not value:
                continue
            if match_type == "merchant_key":
                merchant_rules.append((_normalize_merchant(value), prop["id"], value))
            elif match_type == "description_contains":
                substring_rules.append((value.lower(), prop["id"], value))
            elif match_type == "account_id":
                by_account[value] = prop["id"]

    names = {p["id"]: p.get("name") for p in properties}
    suggestions: List[Dict[str, Any]] = []

    for txn in state.stored_transactions.values():
        if txn.get("property_id"):
            continue

        description = txn.get("description", "") or ""
        matched: Optional[tuple] = None

        account_id = txn.get("account_id")
        if account_id and account_id in by_account:
            matched = (by_account[account_id], "operating account")
        if matched is None and merchant_rules:
            key = _normalize_merchant(description)
            for rule_key, prop_id, original in merchant_rules:
                if key and key == rule_key:
                    matched = (prop_id, f"merchant matches '{original}'")
                    break
        if matched is None and substring_rules:
            lowered = description.lower()
            for needle, prop_id, original in substring_rules:
                if needle in lowered:
                    matched = (prop_id, f"description contains '{original}'")
                    break

        if matched is None:
            continue

        prop_id, reason = matched
        suggestions.append({
            "transaction_id": txn.get("id") or txn.get("transaction_id"),
            "date": txn.get("date"),
            "description": description,
            "amount": txn.get("amount"),
            "property_id": prop_id,
            "property_name": names.get(prop_id),
            "reason": reason,
        })
        if len(suggestions) >= limit:
            break

    return suggestions


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
