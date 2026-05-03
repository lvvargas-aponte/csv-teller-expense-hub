"""Credit utilization endpoint — per-card balance vs. credit_limit.

Pulls live balances from the cached Teller accounts and manual accounts,
joins against the user-edited ``account_details`` side-car for credit
limits.  Cards without a configured limit are still returned so the UI
can prompt the user to fill it in.
"""
from typing import Any, Dict, List

from fastapi import APIRouter

import state

router = APIRouter()


def _status_for(pct: float) -> str:
    if pct >= 50:
        return "high"
    if pct >= 30:
        return "warn"
    return "good"


@router.get("/accounts/credit-health")
async def credit_health() -> Dict[str, Any]:
    teller_accounts = state._balances_cache.get("teller_accounts", []) or []
    manual_accounts = list(state._manual_accounts.values())

    out: List[Dict[str, Any]] = []
    total_balance = 0.0
    total_limit = 0.0

    for acct in list(teller_accounts) + manual_accounts:
        if (acct.get("type") or "").lower() != "credit":
            continue
        acct_id = acct.get("id") or ""
        details = state.account_details.get(acct_id) or {}
        try:
            balance = float(acct.get("ledger") or 0.0)
        except (TypeError, ValueError):
            balance = 0.0
        raw_limit = details.get("credit_limit")
        try:
            limit = float(raw_limit) if raw_limit is not None else None
        except (TypeError, ValueError):
            limit = None

        if limit and limit > 0:
            pct = round(balance / limit * 100.0, 1)
            status = _status_for(pct)
            total_balance += balance
            total_limit += limit
        else:
            pct = None
            status = "unknown"

        out.append({
            "account_id": acct_id,
            "institution": acct.get("institution") if isinstance(acct.get("institution"), str)
                           else (acct.get("institution") or {}).get("name", ""),
            "name": acct.get("name", ""),
            "balance": round(balance, 2),
            "credit_limit": round(limit, 2) if limit is not None else None,
            "utilization_pct": pct,
            "status": status,
        })

    overall_pct = (
        round(total_balance / total_limit * 100.0, 1) if total_limit > 0 else None
    )
    return {
        "accounts": out,
        "total_balance": round(total_balance, 2),
        "total_limit": round(total_limit, 2),
        "overall_utilization_pct": overall_pct,
        "overall_status": _status_for(overall_pct) if overall_pct is not None else "unknown",
    }
