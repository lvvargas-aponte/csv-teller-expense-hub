"""Investments routes: holdings list and portfolio aggregation (read-only).

The display surface for SnapTrade-synced positions. The integration surface
(connect + sync) lives in ``routers/snaptrade.py``; aggregation logic lives in
``analytics.summarize_holdings`` so this router and the advisor snapshot agree.
"""
import logging
from typing import Any, Dict

from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter()


def _synced_snaptrade_accounts() -> list:
    """Every SnapTrade-synced account (with or without positions).

    Pulled from the balances cache key written by ``/snaptrade/sync`` so
    accounts that returned 0 positions still surface in the UI (e.g. when a
    brokerage authorization is fresh and positions haven't propagated yet).
    """
    import state
    return state._balances_cache_store.data.get("snaptrade_accounts", []) or []


@router.get("/investments/holdings")
async def list_holdings() -> Dict[str, Any]:
    """All investment holdings, grouped by account. Includes synced accounts
    with zero positions so the UI can surface 'awaiting positions' state."""
    from db.accounts_repo import get_repo

    holdings = get_repo().get_holdings()
    accounts: Dict[str, Dict[str, Any]] = {}
    for snap in _synced_snaptrade_accounts():
        accounts[snap["id"]] = {
            "account_id": snap["id"],
            "account_name": snap["name"],
            "institution": snap["institution"],
            "holdings": [],
        }
    for h in holdings:
        acc = accounts.setdefault(
            h["account_id"],
            {
                "account_id": h["account_id"],
                "account_name": h["account_name"],
                "institution": h["institution"],
                "holdings": [],
            },
        )
        acc["holdings"].append(h)
    return {"accounts": list(accounts.values()), "holding_count": len(holdings)}


@router.get("/investments/portfolio")
async def get_portfolio() -> Dict[str, Any]:
    """Aggregate portfolio: total value, cost basis, unrealized gain/loss,
    allocation by asset type, concentration, and a per-account breakdown.

    The per-account breakdown includes accounts with 0 positions so the UI
    can render an 'awaiting positions' row instead of silently hiding them."""
    from analytics import summarize_holdings
    from db.accounts_repo import get_repo

    holdings = get_repo().get_holdings()
    summary = summarize_holdings(holdings)

    by_account: Dict[str, Dict[str, Any]] = {}
    for snap in _synced_snaptrade_accounts():
        by_account[snap["id"]] = {
            "account_id": snap["id"],
            "account_name": snap["name"],
            "institution": snap["institution"],
            "value": 0.0,
            "holding_count": 0,
        }
    for h in summary["holdings"]:
        acc = by_account.setdefault(
            h["account_id"],
            {
                "account_id": h["account_id"],
                "account_name": h["account_name"],
                "institution": h["institution"],
                "value": 0.0,
                "holding_count": 0,
            },
        )
        acc["value"] = round(acc["value"] + float(h.get("market_value") or 0.0), 2)
        acc["holding_count"] += 1
    summary["by_account"] = sorted(
        by_account.values(), key=lambda a: a["value"], reverse=True
    )
    return summary
