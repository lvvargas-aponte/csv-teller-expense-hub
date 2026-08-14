"""SnapTrade routes: config, user registration, brokerage connect, and holdings sync.

Models the SimpleFIN router pattern. SnapTrade aggregates brokerage + crypto
accounts; this router owns the *integration* surface (connect + sync) while
``routers/investments.py`` owns the read/display surface.

Auth model: one household-level ``(user_id, user_secret)`` pair, registered
once and persisted in the ``snaptrade_creds`` PgStore.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

import state

logger = logging.getLogger(__name__)
router = APIRouter()

# Single-key store: the app tracks one household SnapTrade user.
_HOUSEHOLD = "household"


def _require_configured() -> None:
    if not state.snaptrade.configured:
        raise HTTPException(
            status_code=503,
            detail="SnapTrade is not configured on the server "
            "(set SNAPTRADE_CLIENT_ID and SNAPTRADE_CONSUMER_KEY).",
        )


def _stored_creds() -> Dict[str, str] | None:
    """Return the persisted SnapTrade (user_id, user_secret), or None."""
    creds = state.snaptrade_creds.get(_HOUSEHOLD)
    if creds and creds.get("user_id") and creds.get("user_secret"):
        return creds
    return None


async def _ensure_user() -> Dict[str, str]:
    """Return the household SnapTrade user, registering it on first use."""
    creds = _stored_creds()
    if creds:
        return creds
    user_id = f"expense-hub-{uuid.uuid4().hex[:12]}"
    try:
        creds = await state.snaptrade.register_user(user_id)
    except Exception as e:
        logger.warning(f"[SnapTrade] register_user failed: {e}")
        raise HTTPException(status_code=502, detail="SnapTrade user registration failed.")
    if not creds.get("user_secret"):
        raise HTTPException(status_code=502, detail="SnapTrade did not return a user secret.")
    state.snaptrade_creds[_HOUSEHOLD] = creds
    state._snaptrade_creds_store.save()
    logger.info("[SnapTrade] Registered household user")
    return creds


def _account_subtype(holdings: List[Dict[str, Any]]) -> str:
    """Label an account 'crypto' when every position is crypto, else 'brokerage'."""
    if holdings and all(h.get("asset_type") == "crypto" for h in holdings):
        return "crypto"
    return "brokerage"


@router.get("/config/snaptrade")
async def get_snaptrade_config() -> Dict[str, Any]:
    """Expose SnapTrade availability to the frontend."""
    return {
        "configured": state.snaptrade.configured,
        "connected": _stored_creds() is not None,
    }


@router.post("/snaptrade/register", status_code=201)
async def register_snaptrade_user() -> Dict[str, Any]:
    """Register the household SnapTrade user (idempotent)."""
    _require_configured()
    await _ensure_user()
    return {"registered": True}


@router.post("/snaptrade/connect")
async def connect_snaptrade() -> Dict[str, str]:
    """Return a SnapTrade connection-portal URL the UI opens in a popup.

    Registers the household user on first call so the frontend only needs
    this one endpoint to start a brokerage connection.
    """
    _require_configured()
    creds = await _ensure_user()
    try:
        url = await state.snaptrade.login_url(creds["user_id"], creds["user_secret"])
    except Exception as e:
        logger.warning(f"[SnapTrade] login_url failed: {e}")
        raise HTTPException(status_code=502, detail="Could not start the SnapTrade connection.")
    if not url:
        raise HTTPException(status_code=502, detail="SnapTrade returned no connection URL.")
    return {"redirect_uri": url}


@router.get("/snaptrade/connections")
async def list_snaptrade_connections() -> Dict[str, Any]:
    """List the household's connected brokerages."""
    _require_configured()
    creds = _stored_creds()
    if not creds:
        return {"connections": []}
    connections = await state.snaptrade.list_connections(
        creds["user_id"], creds["user_secret"]
    )
    return {"connections": connections}


@router.delete("/snaptrade/connections/{authorization_id}", status_code=204)
async def remove_snaptrade_connection(authorization_id: str):
    """Disconnect one brokerage."""
    _require_configured()
    creds = _stored_creds()
    if not creds:
        raise HTTPException(status_code=409, detail="SnapTrade is not connected.")
    ok = await state.snaptrade.remove_connection(
        creds["user_id"], creds["user_secret"], authorization_id
    )
    if not ok:
        raise HTTPException(status_code=502, detail="Could not remove the connection.")


def _persist_portfolio(repo: Any, portfolio: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Upsert account row, replace holdings, write a balance snapshot, and
    return the ``AccountBalance``-shaped cache dict (or ``None`` if the
    portfolio has no usable account id)."""
    account = portfolio["account"]
    account_id = account.get("id")
    if not account_id:
        return None
    holdings = portfolio["holdings"]
    subtype = _account_subtype(holdings)
    total_value = round(float(portfolio.get("total_value") or 0.0), 2)

    repo.upsert_synced_account(
        {
            "id": account_id,
            "name": account["name"],
            "type": "investment",
            "subtype": subtype,
            "institution": {"name": account["institution"]},
        },
        source="snaptrade",
    )
    repo.replace_holdings(account_id, holdings)
    repo.insert_balance_snapshot(
        account_id=account_id,
        source="snaptrade",
        available=total_value,
        ledger=total_value,
        raw={"total_value": total_value, "holding_count": len(holdings)},
    )
    return {
        "id": account_id,
        "institution": account["institution"],
        "name": account["name"],
        "type": "investment",
        "subtype": subtype,
        "available": total_value,
        "ledger": total_value,
        "manual": False,
    }


def _update_snaptrade_cache(synced_accounts: List[Dict[str, Any]]) -> None:
    """Merge per-account sync results into the snaptrade_accounts cache key.

    Single-account syncs replace just that one entry; bulk sync replaces the
    full list. Caller decides which shape to pass (full list = replace all).
    """
    state._balances_cache_store.data["snaptrade_accounts"] = synced_accounts
    state._balances_cache_store.data["snaptrade_fetched_at"] = (
        datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    )
    state._balances_cache_store.save()


@router.post("/snaptrade/sync")
async def sync_snaptrade() -> Dict[str, Any]:
    """Pull every connected account's holdings + total value and persist them.

    For each account: upsert the ``accounts`` row (source='snaptrade',
    type='investment'), replace the ``holdings`` rows, append a
    ``balance_snapshots`` row for the net-worth timeseries, and cache an
    ``AccountBalance``-shaped dict so ``/balances/summary`` includes it.
    """
    _require_configured()
    creds = _stored_creds()
    if not creds:
        raise HTTPException(status_code=409, detail="Connect a brokerage first.")

    from db.accounts_repo import get_repo

    repo = get_repo()
    try:
        portfolios = await state.snaptrade.get_all_holdings(
            creds["user_id"], creds["user_secret"]
        )
    except Exception as e:
        logger.warning(f"[SnapTrade] holdings fetch failed: {e}")
        raise HTTPException(status_code=502, detail="Could not fetch holdings from SnapTrade.")

    synced_accounts: List[Dict[str, Any]] = []
    results: List[Dict[str, Any]] = []
    for portfolio in portfolios:
        cached = _persist_portfolio(repo, portfolio)
        if cached is None:
            continue
        synced_accounts.append(cached)
        results.append({
            "account": cached["name"],
            "holdings": len(portfolio["holdings"]),
            "value": cached["available"],
        })

    _update_snaptrade_cache(synced_accounts)

    return {
        "message": (
            f"SnapTrade sync complete. {len(synced_accounts)} account(s), "
            f"{sum(r['holdings'] for r in results)} holdings."
        ),
        "accounts": len(synced_accounts),
        "details": results,
    }


@router.post("/snaptrade/sync/{account_id}")
async def sync_snaptrade_account(account_id: str) -> Dict[str, Any]:
    """Sync a single connected SnapTrade account.

    Same persistence as the bulk sync, but only one account is hit (one
    ``list_user_accounts`` call + per-account positions + balance). Use when
    you want to refresh one brokerage without paying for the others to
    re-pull, or when one account has been stale and you want a targeted
    retry without disturbing the rest of the snaptrade_accounts cache.
    """
    _require_configured()
    creds = _stored_creds()
    if not creds:
        raise HTTPException(status_code=409, detail="Connect a brokerage first.")

    from db.accounts_repo import get_repo

    repo = get_repo()
    try:
        portfolio = await state.snaptrade.get_account_holdings(
            creds["user_id"], creds["user_secret"], account_id
        )
    except Exception as e:
        logger.warning(f"[SnapTrade] single-account fetch failed for {account_id}: {e}")
        raise HTTPException(status_code=502, detail="Could not fetch holdings from SnapTrade.")

    if portfolio is None:
        raise HTTPException(status_code=404, detail="Account not found in SnapTrade.")

    cached = _persist_portfolio(repo, portfolio)
    if cached is None:
        raise HTTPException(status_code=502, detail="SnapTrade returned an account without an id.")

    # Merge into the cache without disturbing the other synced accounts.
    existing = state._balances_cache_store.data.get("snaptrade_accounts", []) or []
    merged = [a for a in existing if a.get("id") != account_id] + [cached]
    _update_snaptrade_cache(merged)

    return {
        "message": (
            f"Synced {cached['name']}: {len(portfolio['holdings'])} position(s), "
            f"value {cached['available']}."
        ),
        "account": cached["name"],
        "holdings": len(portfolio["holdings"]),
        "value": cached["available"],
    }
