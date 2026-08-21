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
    """Every SnapTrade-synced account worth showing (with or without positions).

    Pulled from the balances cache key written by ``/snaptrade/sync`` so
    accounts that returned 0 positions still surface in the UI (e.g. when a
    brokerage authorization is fresh and positions haven't propagated yet).
    Accounts reporting no value at all are dropped — see
    ``analytics.is_empty_synced_account``.
    """
    import state
    from analytics import is_empty_synced_account

    cached = state._balances_cache_store.data.get("snaptrade_accounts", []) or []
    return [a for a in cached if not is_empty_synced_account(a)]


def _external_investment_accounts() -> list:
    """Investment accounts held outside SnapTrade, as ``by_account`` rows.

    A 401(k) typed into the Accounts modal or a crypto balance from an
    exchange SnapTrade can't reach is still part of the portfolio, so this
    page shows it rather than only what SnapTrade happens to link. These
    carry a balance but no ticker-level positions, so they contribute value
    without touching cost basis or allocation.

    Sources mirror the ones ``routers.balances`` merges — manual entries and
    any SimpleFIN account that classifies as an investment — using the same
    ``_classify_account_bucket`` rules, so this page's total matches the
    ``total_investments`` figure on the dashboard. SnapTrade accounts live
    under their own cache key and are never in either source, so nothing
    double-counts.
    """
    import state
    from analytics import _classify_account_bucket

    sources = (
        ("manual", list(state._manual_accounts.values())),
        ("simplefin", list(state._balances_cache.get("simplefin_accounts", []) or [])),
    )
    out = []
    for source, accounts in sources:
        for a in accounts:
            if _classify_account_bucket(a.get("type", ""), a.get("subtype", "")) != "investment":
                continue
            value = float(a.get("available") or 0.0) or float(a.get("ledger") or 0.0)
            out.append({
                "account_id": a.get("id", ""),
                "account_name": a.get("name", ""),
                "institution": a.get("institution", ""),
                "value": round(value, 2),
                "holding_count": 0,
                "source": source,
            })
    return out


@router.get("/investments/holdings")
async def list_holdings() -> Dict[str, Any]:
    """All investment holdings, grouped by account. Includes synced accounts
    with zero positions so the UI can surface 'awaiting positions' state, plus
    balance-only investment accounts tracked outside SnapTrade."""
    from db.accounts_repo import get_repo

    holdings = get_repo().get_holdings()
    accounts: Dict[str, Dict[str, Any]] = {}
    for snap in _synced_snaptrade_accounts():
        accounts[snap["id"]] = {
            "account_id": snap["id"],
            "account_name": snap["name"],
            "institution": snap["institution"],
            "source": "snaptrade",
            "holdings": [],
        }
    for ext in _external_investment_accounts():
        accounts[ext["account_id"]] = {
            "account_id": ext["account_id"],
            "account_name": ext["account_name"],
            "institution": ext["institution"],
            "source": ext["source"],
            "holdings": [],
        }
    for h in holdings:
        acc = accounts.setdefault(
            h["account_id"],
            {
                "account_id": h["account_id"],
                "account_name": h["account_name"],
                "institution": h["institution"],
                "source": "snaptrade",
                "holdings": [],
            },
        )
        acc["holdings"].append(h)
    return {"accounts": list(accounts.values()), "holding_count": len(holdings)}


@router.get("/investments/portfolio")
async def get_portfolio() -> Dict[str, Any]:
    """Aggregate portfolio: total value, cost basis, unrealized gain/loss,
    allocation by asset type, concentration, and a per-account breakdown.

    Covers every investment account the app knows about — SnapTrade-synced
    brokerages plus balance-only accounts like a manually-tracked 401(k) — so
    the total here agrees with ``total_investments`` on the dashboard. The
    per-account breakdown includes accounts with 0 positions so the UI can
    render an 'awaiting positions' row instead of silently hiding them."""
    from analytics import summarize_holdings
    from db.accounts_repo import get_repo

    holdings = get_repo().get_holdings()
    summary = summarize_holdings(holdings)
    holdings_accounts = {h["account_id"] for h in summary["holdings"]}

    # Accounts on some SnapTrade plan tiers (e.g. Personal API keys) never
    # get ticker-level positions — only an account-level total from the sync.
    # Use that as the account's value instead of leaving it at $0, and fold it
    # into the portfolio total. Cost basis/gain/allocation stay holdings-only
    # since there's no per-position data to attribute them to. Investment
    # accounts held outside SnapTrade are balance-only for the same reason.
    balance_only_total = 0.0
    by_account: Dict[str, Dict[str, Any]] = {}
    for snap in _synced_snaptrade_accounts():
        has_holdings = snap["id"] in holdings_accounts
        value = 0.0 if has_holdings else round(float(snap.get("available") or 0.0), 2)
        if not has_holdings:
            balance_only_total += value
        by_account[snap["id"]] = {
            "account_id": snap["id"],
            "account_name": snap["name"],
            "institution": snap["institution"],
            "value": value,
            "holding_count": 0,
            "source": "snaptrade",
        }
    for ext in _external_investment_accounts():
        balance_only_total += ext["value"]
        by_account[ext["account_id"]] = ext
    for h in summary["holdings"]:
        acc = by_account.setdefault(
            h["account_id"],
            {
                "account_id": h["account_id"],
                "account_name": h["account_name"],
                "institution": h["institution"],
                "value": 0.0,
                "holding_count": 0,
                "source": "snaptrade",
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
