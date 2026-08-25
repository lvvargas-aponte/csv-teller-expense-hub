"""Investments routes: holdings list and portfolio aggregation (read-only).

The display surface for SnapTrade-synced positions. The integration surface
(connect + sync) lives in ``routers/snaptrade.py``; aggregation logic lives in
``analytics.summarize_holdings`` so this router and the advisor snapshot agree.
"""
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter()


class CostBasisUpdate(BaseModel):
    """The user's average purchase price for one position."""

    average_purchase_price: float = Field(gt=0)


async def _investment_accounts() -> List[Dict[str, Any]]:
    """Every investment account the app knows about, whatever synced it.

    Read off the balances summary (cached, no provider call) and filtered
    with the same ``classify_account_bucket`` the summary itself uses, so an
    account counted as an investment in net worth is the same set shown here.
    That matters for brokerages reached through a bank aggregator: SimpleFIN
    reports a balance for them but never ticker-level positions, so before
    this they were investments everywhere except on the Investments page.

    Returns dicts shaped like the SnapTrade cache entries, plus ``source``.
    """
    from analytics import classify_account_bucket
    from balances_service import build_summary

    summary = await build_summary(force=False)
    return [
        {
            "id": a.id,
            "name": a.name,
            "institution": a.institution,
            "available": a.available,
            "ledger": a.ledger,
            "source": a.source,
        }
        for a in summary.accounts
        if classify_account_bucket(a.type, a.subtype) == "investment"
    ]


@router.get("/investments/holdings")
async def list_holdings() -> Dict[str, Any]:
    """All investment holdings, grouped by account. Includes synced accounts
    with zero positions so the UI can surface 'awaiting positions' state."""
    from db.accounts_repo import get_repo

    holdings = get_repo().get_holdings()
    accounts: Dict[str, Dict[str, Any]] = {}
    for acct in await _investment_accounts():
        accounts[acct["id"]] = {
            "account_id": acct["id"],
            "account_name": acct["name"],
            "institution": acct["institution"],
            "source": acct["source"],
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
    holdings_accounts = {h["account_id"] for h in summary["holdings"]}

    # Two kinds of account arrive without positions: SnapTrade tiers that only
    # return an account-level total, and brokerages synced through a bank
    # aggregator, which never report positions at all. Both use their balance
    # as the account's value and fold it into the portfolio total. Cost basis,
    # gain and allocation stay holdings-only — there's no per-position data to
    # attribute them to — so ``balance_only_value`` is reported alongside for
    # the UI to say which part of the total the allocation covers.
    balance_only_total = 0.0
    by_account: Dict[str, Dict[str, Any]] = {}
    for acct in await _investment_accounts():
        has_holdings = acct["id"] in holdings_accounts
        value = 0.0 if has_holdings else round(float(acct.get("available") or 0.0), 2)
        if not has_holdings:
            balance_only_total += value
        by_account[acct["id"]] = {
            "account_id": acct["id"],
            "account_name": acct["name"],
            "institution": acct["institution"],
            "source": acct["source"],
            "value": value,
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
    summary["balance_only_value"] = round(balance_only_total, 2)
    if balance_only_total:
        summary["total_value"] = round(summary["total_value"] + balance_only_total, 2)
    return summary


@router.put("/investments/holdings/{account_id}/{symbol}/cost-basis")
async def set_cost_basis(
    account_id: str, symbol: str, body: CostBasisUpdate
) -> Dict[str, Any]:
    """Record the user's average purchase price for one position.

    Stored apart from ``holdings`` so the next SnapTrade sync — which
    replaces that account's rows wholesale — cannot destroy it.
    """
    from db.accounts_repo import get_repo

    repo = get_repo()
    if not any(
        h["symbol"] == symbol for h in repo.get_holdings_for_account(account_id)
    ):
        raise HTTPException(status_code=404, detail="No such holding.")
    repo.set_cost_override(account_id, symbol, body.average_purchase_price)
    return {
        "account_id": account_id,
        "symbol": symbol,
        "average_purchase_price": body.average_purchase_price,
        "cost_basis_source": "user",
    }


@router.delete("/investments/holdings/{account_id}/{symbol}/cost-basis")
async def clear_cost_basis(account_id: str, symbol: str) -> Dict[str, Any]:
    """Drop the user's override so the provider's value (if any) applies again."""
    from db.accounts_repo import get_repo

    removed = get_repo().delete_cost_override(account_id, symbol)
    return {"account_id": account_id, "symbol": symbol, "removed": removed}
