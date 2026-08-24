"""Credit utilization composition — per-card balance vs. configured limit.

One composition, three readers: the Credit Health card, the alert feed, and
the health score. It reads balances from ``balances_service.build_summary``
rather than walking the account stores itself — a manual account's stored
``ledger`` is only its *starting* balance, so a hand-rolled walk reports a
figure the Accounts page contradicts.
"""
from typing import Any, Dict, List, Optional

import balances_service
import state
from analytics import classify_account_bucket

# Installment debt (mortgage, auto, student). ``simplefin.infer_account_bucket``
# tags these ``subtype="loan"``. A revolving-utilization ratio says nothing
# useful about them, so they are listed but not rated.
_INSTALLMENT_SUBTYPES = frozenset({"loan", "mortgage", "student", "auto"})


def _status_for(pct: float) -> str:
    if pct >= 50:
        return "high"
    if pct >= 30:
        return "warn"
    return "good"


def _limit_for(account_id: str) -> Optional[float]:
    raw = (state.account_details.get(account_id) or {}).get("credit_limit")
    try:
        return float(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


async def build() -> Dict[str, Any]:
    """Per-card utilization plus the household totals.

    Cards without a configured limit are still returned so the UI can prompt
    the user to fill one in; they contribute nothing to the overall figure,
    and neither do installment loans.
    """
    summary = await balances_service.build_summary()

    out: List[Dict[str, Any]] = []
    total_balance = 0.0
    total_limit = 0.0

    for acct in summary.accounts:
        if classify_account_bucket(acct.type, acct.subtype) != "credit":
            continue

        balance = float(acct.ledger or 0.0)
        limit = _limit_for(acct.id)
        installment = (acct.subtype or "").lower().strip() in _INSTALLMENT_SUBTYPES

        if installment:
            pct = None
            status = "not_applicable"
        elif limit and limit > 0:
            pct = round(balance / limit * 100.0, 1)
            status = _status_for(pct)
            total_balance += balance
            total_limit += limit
        else:
            pct = None
            status = "unknown"

        out.append({
            "account_id": acct.id,
            "institution": acct.institution,
            "name": acct.name,
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
