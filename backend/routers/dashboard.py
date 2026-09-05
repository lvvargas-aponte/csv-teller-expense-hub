"""Dashboard route — chart-friendly aggregations for the Dashboard tab.

Reuses helpers in :mod:`analytics` so this stays a thin serializer over
data the advisor already computes.
"""
from datetime import date
from typing import Any, Dict, List

from fastapi import APIRouter

import analytics
import state

router = APIRouter()


@router.get("/dashboard")
async def dashboard(months: int = 6) -> Dict[str, Any]:
    months = max(3, min(12, int(months)))

    spending = analytics.group_debit_spending()
    sorted_months = sorted(spending.keys())[-months:]
    trimmed = {m: spending[m] for m in sorted_months}

    monthly_totals = [
        {"month": m, "total": round(sum(trimmed[m].values()), 2)}
        for m in sorted_months
    ]

    return {
        "months": sorted_months,
        "spending_by_month": trimmed,
        "monthly_totals": monthly_totals,
        "net_worth_timeseries": analytics.compute_net_worth_timeseries(months),
        # Bills and subscriptions have their own sections on Commitments; this
        # card is the third bucket — what repeats without being an obligation.
        "recurring_charges": [
            r for r in analytics.detect_recurring_charges()
            if r.get("commitment_type") == "recurring_spend"
            and r.get("status") != "dormant"
        ][:10],
        "balance_trend": analytics.compute_balance_trend(),
        "spend_comparison": analytics.compute_month_to_date_comparison(),
    }


@router.get("/dashboard/income-vs-expenses")
async def income_vs_expenses(months: int = 6) -> Dict[str, Any]:
    """Per-month income (inflows) vs. expenses (outflows) with surplus/deficit.

    Both sides go through the shared filters — ``analytics._is_expense`` and
    ``analytics._is_income_candidate`` — rather than a second definition here.
    The hand-rolled income test this replaced tested ``"credit" in
    account_type``, and SimpleFIN puts the account's *display name* in that
    field, so every card payment landing on a card counted as household
    income. August reported $15,148 against a real payroll of $8,238.
    """
    months = max(3, min(24, int(months)))

    credit_ids = analytics._credit_account_ids()
    income_by_month: Dict[str, float] = {}
    expense_by_month: Dict[str, float] = {}

    for txn in state.stored_transactions.values():
        date_str = txn.get("date", "")
        if not date_str:
            continue
        month_key = analytics._parse_month_key(date_str)
        if not month_key or len(month_key) < 7:
            continue

        try:
            amount = float(txn.get("amount", 0))
        except (TypeError, ValueError):
            continue

        if analytics._is_expense(txn):
            expense_by_month[month_key] = expense_by_month.get(month_key, 0.0) + amount
            continue

        # Income side: the same test paycheck detection uses, so a card
        # payment, a Zelle split and a P2P transfer are excluded here exactly
        # as they are there.
        if txn.get("transfer_to_account_id"):
            continue
        if amount > 0 and analytics._is_income_candidate(txn, credit_ids):
            income_by_month[month_key] = income_by_month.get(month_key, 0.0) + amount

    all_months = sorted(set(income_by_month) | set(expense_by_month))[-months:]
    today = date.today()
    current_month = f"{today.year:04d}-{today.month:02d}"
    current_is_partial = today.day < analytics._last_day_of_month(today)

    rows: List[Dict[str, Any]] = []
    for m in all_months:
        income = round(income_by_month.get(m, 0.0), 2)
        expense = round(expense_by_month.get(m, 0.0), 2)
        rows.append({
            "month": m,
            "income": income,
            "expenses": expense,
            "net": round(income - expense, 2),
            "is_partial": m == current_month and current_is_partial,
        })

    return {"months": all_months, "rows": rows}
