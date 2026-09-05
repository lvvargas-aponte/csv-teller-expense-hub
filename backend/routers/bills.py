"""Upcoming bills — projects the next due date for each credit account
that has a ``due_day`` configured in ``account_details``, and merges in
transaction-derived recurring charges (utilities, subscriptions, etc.) so
non-credit bills also appear on the Bills page.
"""
from datetime import date, timedelta
from typing import Any, Dict, List

from fastapi import APIRouter

import state
from analytics import _next_due_date

router = APIRouter()


def _account_lookup(account_id: str) -> Dict[str, Any]:
    """Find account metadata (name, institution) across cache + manual."""
    _cached = state._balances_cache.get("simplefin_accounts", []) or []
    for acct in _cached:
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
        # What is due on a card is its minimum, not its whole ledger — the
        # balance stays as context, but it is not a commitment for this month.
        minimum = details.get("minimum_payment")
        try:
            amount_due = float(minimum) if minimum is not None else None
        except (TypeError, ValueError):
            amount_due = None

        bills.append({
            "account_id": account_id,
            "name": meta.get("name", ""),
            "institution": meta.get("institution", ""),
            "type": meta.get("type", ""),
            "due_day": int(due_day),
            "due_date": next_due.isoformat(),
            "days_until": (next_due - today).days,
            "balance": round(meta.get("ledger", 0.0), 2),
            "minimum_payment": minimum,
            "amount_due": amount_due,
        })

    # Merge in transaction-derived bills — obligatory commitments only. The
    # detector already bucketed each merchant; subscriptions and everything
    # else that merely repeats (groceries, parking, hair, therapy) carry a
    # different ``commitment_type`` and belong to their own sections.
    from analytics import detect_recurring_charges

    for r in detect_recurring_charges():
        if r.get("commitment_type") != "bill":
            continue
        # A bill that stopped arriving has no next due date worth projecting.
        if r.get("status") == "dormant":
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
            # A recurring charge is due for its typical amount in full.
            "amount_due": r["average_amount"],
            "category": r.get("category"),
            "merchant_key": r.get("merchant_key"),
        })

    bills.sort(key=lambda b: b["due_date"])

    # "What is due in the next 30 days, in total" — the question the page
    # exists to answer, and the one no screen answered before.
    by_kind = {"credit": 0.0, "recurring": 0.0}
    for bill in bills:
        due = bill.get("amount_due")
        if due is None:
            continue
        kind = "recurring" if bill["type"] == "recurring" else "credit"
        by_kind[kind] += float(due)

    return {
        "today": today.isoformat(),
        "window_days": window_days,
        "bills": bills,
        "total_due": round(sum(by_kind.values()), 2),
        "total_due_by_kind": {k: round(v, 2) for k, v in by_kind.items()},
    }
