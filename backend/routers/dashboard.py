"""Dashboard route — chart-friendly aggregations for the Dashboard tab.

Reuses helpers in :mod:`analytics` so this stays a thin serializer over
data the advisor already computes.
"""
import logging
from typing import Any, Dict, List

from fastapi import APIRouter

import analytics
import state

logger = logging.getLogger(__name__)
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
        "recurring_charges": analytics.detect_recurring_charges()[:10],
        "balance_trend": analytics.compute_balance_trend(),
    }


@router.get("/dashboard/income-vs-expenses")
async def income_vs_expenses(months: int = 6) -> Dict[str, Any]:
    """Per-month income (credits) vs. expenses (debits) with surplus/deficit.

    Income is an inverse of the expense filter in ``analytics.group_debit_spending``:
    Discover credit-purchases stay classified as expenses; everything else
    that's a positive credit on a non-credit account counts as income.
    """
    months = max(3, min(24, int(months)))

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
        txn_type = txn.get("transaction_type")
        source = txn.get("source", "")

        is_expense = (
            txn_type == "debit"
            or (source == "discover" and txn_type == "credit" and amount > 0)
            or (txn_type is None and amount > 0)
        )
        if is_expense:
            expense_by_month[month_key] = expense_by_month.get(month_key, 0.0) + amount
            continue

        if txn_type == "credit" and source != "discover" and amount > 0:
            acct_type = (txn.get("account_type") or "").lower()
            if "credit" in acct_type:
                # Credit-card payments / refunds aren't household income.
                continue
            income_by_month[month_key] = income_by_month.get(month_key, 0.0) + amount

    all_months = sorted(set(income_by_month) | set(expense_by_month))[-months:]
    rows: List[Dict[str, Any]] = []
    for m in all_months:
        income = round(income_by_month.get(m, 0.0), 2)
        expense = round(expense_by_month.get(m, 0.0), 2)
        rows.append({
            "month": m,
            "income": income,
            "expenses": expense,
            "net": round(income - expense, 2),
        })

    return {"months": all_months, "rows": rows}
