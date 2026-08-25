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
from typing import Any, Dict, List, Optional

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
