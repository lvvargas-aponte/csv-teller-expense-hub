"""Upcoming bills — projects the next due date for each credit account
that has a ``due_day`` configured in ``account_details``, and merges in
transaction-derived recurring charges (utilities, subscriptions, etc.) so
non-credit bills also appear on the Bills page.
"""
import calendar
from datetime import date, datetime, timedelta
from typing import Any, Dict, List

from fastapi import APIRouter

import state

router = APIRouter()


def _next_due_date(today: date, due_day: int) -> date:
    """Return the next calendar date matching ``due_day`` on or after ``today``.

    Caps day at the last day of the month for shorter months (Feb 30 → Feb 28/29).
    """
    due_day = max(1, min(31, int(due_day)))
    year, month = today.year, today.month
    last = calendar.monthrange(year, month)[1]
    candidate = date(year, month, min(due_day, last))
    if candidate < today:
        # Roll into next month.
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
        last = calendar.monthrange(year, month)[1]
        candidate = date(year, month, min(due_day, last))
    return candidate


def _account_lookup(account_id: str) -> Dict[str, Any]:
    """Find account metadata (name, institution) across cache + manual."""
    for acct in state._balances_cache.get("teller_accounts", []) or []:
        if acct.get("id") == account_id:
            inst = acct.get("institution")
            inst_name = inst if isinstance(inst, str) else (inst or {}).get("name", "")
            return {
                "name": acct.get("name", ""),
                "institution": inst_name,
                "type": acct.get("type", ""),
                "ledger": float(acct.get("ledger") or 0.0),
            }
    acct = state._manual_accounts.get(account_id)
    if acct is not None:
        return {
            "name": acct.get("name", ""),
            "institution": acct.get("institution", ""),
            "type": acct.get("type", ""),
            "ledger": float(acct.get("ledger") or 0.0),
        }
    return {}


@router.get("/bills/upcoming")
async def upcoming_bills(window_days: int = 30) -> Dict[str, Any]:
    window_days = max(7, min(90, int(window_days)))
    today = date.today()
    horizon = today + timedelta(days=window_days)

    bills: List[Dict[str, Any]] = []
    for account_id, details in state.account_details.items():
        due_day = details.get("due_day")
        if due_day is None:
            continue
        meta = _account_lookup(account_id)
        if not meta:
            continue
        next_due = _next_due_date(today, int(due_day))
        if next_due > horizon:
            continue
        bills.append({
            "account_id": account_id,
            "name": meta.get("name", ""),
            "institution": meta.get("institution", ""),
            "type": meta.get("type", ""),
            "due_day": int(due_day),
            "due_date": next_due.isoformat(),
            "days_until": (next_due - today).days,
            "balance": round(meta.get("ledger", 0.0), 2),
            "minimum_payment": details.get("minimum_payment"),
        })

    # Merge in transaction-derived bills — obligatory monthly commitments only
    # (utilities, insurance, mortgage/rent, phone/internet, subscriptions). The
    # Dashboard's Recurring Charges card surfaces everything else that repeats
    # (groceries, parking, hair, therapy, etc.); those don't belong here.
    from analytics import detect_recurring_charges

    # Only true monthly obligations belong here. Credit cards are surfaced via
    # the due_day path above; subscriptions / insurance / phone etc. live in
    # the Dashboard's Recurring Charges card.
    BILL_CATEGORIES = {"utilities", "mortgage", "rent"}
    for r in detect_recurring_charges():
        cat = (r.get("category") or "").strip().lower()
        if cat not in BILL_CATEGORIES:
            continue
        typical_day = r.get("typical_day")
        if not typical_day:
            continue
        # Project next occurrence of the merchant's typical day-of-month. If
        # we already passed it this month, ``_next_due_date`` rolls forward.
        projected = _next_due_date(today, int(typical_day))
        if projected > horizon:
            continue
        bills.append({
            "account_id": None,
            "name": r["sample_description"],
            "institution": r.get("category") or "Recurring",
            "type": "recurring",
            "due_day": int(typical_day),
            "due_date": projected.isoformat(),
            "days_until": (projected - today).days,
            "balance": r["average_amount"],
            "minimum_payment": None,
            "category": r.get("category"),
            "merchant_key": r.get("merchant_key"),
        })

    bills.sort(key=lambda b: b["due_date"])
    return {"today": today.isoformat(), "window_days": window_days, "bills": bills}
