"""Upcoming-bill assembly, shared by the Bills page and the coach.

Extracted from ``routers/bills.py`` because the coach needs to reason about
what's due. A coach that projected due dates differently from the Bills page
would be a trust bug — the user would see two answers to "when is that
due?" and have no way to tell which one to believe.

The router keeps the HTTP surface; the projection logic lives here.
"""
import calendar
from datetime import date, timedelta
from typing import Any, Dict, List

import state

# Only true monthly obligations. Credit cards arrive via the ``due_day`` path;
# subscriptions, insurance and the like surface on the Dashboard's Recurring
# Charges card instead, which is a different question ("what repeats?") from
# the one this answers ("what must I pay?").
BILL_CATEGORIES = {"utilities", "mortgage", "rent"}


def next_due_date(today: date, due_day: int) -> date:
    """Next calendar date matching ``due_day`` on or after ``today``.

    Clamps to the last day of short months, so a 31st due-day lands on
    Feb 28 rather than raising.
    """
    due_day = max(1, min(31, int(due_day)))
    year, month = today.year, today.month
    last = calendar.monthrange(year, month)[1]
    candidate = date(year, month, min(due_day, last))
    if candidate < today:
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
        last = calendar.monthrange(year, month)[1]
        candidate = date(year, month, min(due_day, last))
    return candidate


def account_lookup(account_id: str) -> Dict[str, Any]:
    """Account metadata across the balances cache and manual accounts."""
    for acct in state._balances_cache.get("simplefin_accounts", []) or []:
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


def upcoming_bills(window_days: int = 30, today: date = None) -> Dict[str, Any]:
    """Bills due within ``window_days``, newest first.

    Two sources: credit accounts with a configured ``due_day``, and
    transaction-derived recurring charges in :data:`BILL_CATEGORIES`.
    """
    from analytics import detect_recurring_charges

    window_days = max(7, min(90, int(window_days)))
    today = today or date.today()
    horizon = today + timedelta(days=window_days)

    bills: List[Dict[str, Any]] = []
    for account_id, details in state.account_details.items():
        due_day = (details or {}).get("due_day")
        if due_day is None:
            continue
        meta = account_lookup(account_id)
        if not meta:
            continue
        due = next_due_date(today, int(due_day))
        if due > horizon:
            continue
        bills.append({
            "account_id": account_id,
            "name": meta.get("name", ""),
            "institution": meta.get("institution", ""),
            "type": meta.get("type", ""),
            "due_day": int(due_day),
            "due_date": due.isoformat(),
            "days_until": (due - today).days,
            "balance": round(meta.get("ledger", 0.0), 2),
            "minimum_payment": details.get("minimum_payment"),
        })

    for r in detect_recurring_charges():
        if (r.get("category") or "").strip().lower() not in BILL_CATEGORIES:
            continue
        typical_day = r.get("typical_day")
        if not typical_day:
            continue
        projected = next_due_date(today, int(typical_day))
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
