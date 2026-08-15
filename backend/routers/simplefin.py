"""SimpleFIN routes: setup-token claim and sync.

SimpleFIN bundles transactions inline on each account object, so there is
no separate per-account transactions call — one ``/accounts`` fetch
(``state.simplefin.list_accounts_by_url``) returns everything needed for a
sync.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

import state
from category_normalizer import normalize as normalize_category
from csv_parser import Transaction as CsvTransaction, BankType, dedupe_key
from helpers import _env_add_simplefin_url, _env_remove_simplefin_url, _previous_month_range
from models import SimplefinClaimRequest, SimplefinSyncRequest
from routers.balances import persist_simplefin_balances
from simplefin import _mask_url

logger = logging.getLogger(__name__)
router = APIRouter()


def _to_unix(date_str: str) -> int:
    """YYYY-MM-DD -> Unix timestamp (UTC midnight), per the SimpleFIN protocol."""
    return int(datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())


@router.post("/simplefin/claim", status_code=201)
async def claim_simplefin_token(req: SimplefinClaimRequest):
    """Exchange a one-time Setup Token (pasted from the SimpleFIN Bridge) for
    a durable Access URL, then persist it to .env and the in-memory client.
    """
    access_url = await state.simplefin.claim_setup_token(req.setup_token)

    if access_url in state.SIMPLEFIN_ACCESS_URLS:
        logger.info(f"[SimpleFIN] Access URL {_mask_url(access_url)} already registered — skipping.")
        return {"claimed": False, "reason": "duplicate", "total_connections": len(state.SIMPLEFIN_ACCESS_URLS)}

    state.SIMPLEFIN_ACCESS_URLS.append(access_url)
    _env_add_simplefin_url(access_url)
    logger.info(
        f"[SimpleFIN] New access URL {_mask_url(access_url)} added "
        f"({len(state.SIMPLEFIN_ACCESS_URLS)} total)."
    )

    return {"claimed": True, "total_connections": len(state.SIMPLEFIN_ACCESS_URLS)}


@router.delete("/simplefin/connections", status_code=200)
async def remove_simplefin_connection(access_url_masked: str):
    """Drop a stored access URL entirely (all accounts behind it disappear).

    SimpleFIN has no API to revoke just this URL server-side — it's simply
    removed from local storage. Matched by masked form since the frontend
    never holds the raw URL after claiming it.
    """
    match = state.simplefin.remove_by_masked(access_url_masked)
    if not match:
        raise HTTPException(status_code=404, detail="No matching SimpleFIN connection found.")
    _env_remove_simplefin_url(match)
    logger.info(f"[SimpleFIN] Removed access URL {access_url_masked}.")
    return {"removed": access_url_masked, "total_connections": len(state.SIMPLEFIN_ACCESS_URLS)}


@router.post("/simplefin/sync")
async def sync_simplefin_transactions(req: Optional[SimplefinSyncRequest] = None):
    """Pull accounts + bundled transactions from every stored access URL,
    filtered by date range."""
    if req is None:
        req = SimplefinSyncRequest()

    if not state.SIMPLEFIN_ACCESS_URLS:
        raise HTTPException(
            status_code=500,
            detail="No SimpleFIN access URLs configured. Connect a bank via SimpleFIN first.",
        )

    from_date, to_date = _previous_month_range()
    if req.from_date:
        from_date = req.from_date
    if req.to_date:
        to_date = req.to_date

    # SimpleFIN's own window is capped at 90 days server-side; ask for a
    # 5-day-wider window than we display (mirrors SimpleFIN's own overlap
    # recommendation) and let the client-side filter below trim it back.
    start_ts = _to_unix(from_date) - 5 * 86400
    end_ts = _to_unix(to_date) + 5 * 86400

    total_fetched = 0
    total_added = 0

    existing_keys = {
        dedupe_key(
            t.get("date"), t.get("amount"),
            t.get("description"), t.get("transaction_type"),
        )
        for t in state.stored_transactions.values()
    }

    url_batches, url_errors = await state.simplefin.list_accounts_by_url(start_ts, end_ts)
    results: List[Dict[str, Any]] = list(url_errors)

    # Refresh the balances cache using the same account data we just fetched —
    # otherwise the Finances page keeps showing stale balances after a sync.
    try:
        await persist_simplefin_balances(url_batches)
    except Exception as e:
        logger.warning(f"[SimpleFIN] Could not refresh balances cache during sync: {e}")

    for _url, accounts in url_batches:
        for account in accounts:
            acct_id = account.get("id")
            if not acct_id:
                continue
            if req.account_ids is not None and acct_id not in req.account_ids:
                continue
            # Locally hidden ("disconnected") accounts stay out of sync too.
            shadow = state._manual_accounts.get(acct_id)
            if shadow and shadow.get("disconnected_from") == "simplefin":
                continue

            org_name = account.get("_org_name") or "Bank"
            acct_name = f"{org_name} – {account.get('name', acct_id)}"

            try:
                all_txns = account.get("transactions", []) or []
                filtered = []
                for t in all_txns:
                    posted = t.get("posted") or t.get("transacted_at")
                    if posted is None:
                        continue
                    txn_date = datetime.fromtimestamp(int(posted), tz=timezone.utc).strftime("%Y-%m-%d")
                    if from_date <= txn_date <= to_date:
                        filtered.append((t, txn_date))

                added = 0
                for t, txn_date in filtered:
                    amt = float(t.get("amount", 0))
                    txn = CsvTransaction(
                        date=txn_date,
                        description=t.get("description", ""),
                        amount=abs(amt),
                        source=BankType.SIMPLEFIN,
                        transaction_id=t.get("id"),
                        account_id=acct_id,
                        category=normalize_category((t.get("extra") or {}).get("category")),
                        institution=org_name,
                        # SimpleFIN's amount sign is always balance-effect based
                        # (positive = money in) — no CR/DR heuristic needed.
                        transaction_type="credit" if amt > 0 else "debit",
                        account_type=account.get("name", ""),
                    )
                    key = dedupe_key(
                        txn.date, txn.amount, txn.description, txn.transaction_type,
                    )
                    if (
                        txn.transaction_id not in state.stored_transactions
                        and key not in existing_keys
                    ):
                        state.stored_transactions[txn.transaction_id] = txn.to_dict()
                        existing_keys.add(key)
                        added += 1
                    elif txn.transaction_id in state.stored_transactions:
                        existing = state.stored_transactions[txn.transaction_id]
                        for field in ("transaction_type", "account_type", "category",
                                      "institution", "description", "amount", "date"):
                            existing[field] = getattr(txn, field)
                        state.stored_transactions[txn.transaction_id] = existing

                total_fetched += len(filtered)
                total_added += added
                results.append({
                    "account": acct_name,
                    "fetched": len(filtered),
                    "new": added,
                    "date_range": f"{from_date} → {to_date}",
                })
                state._transactions_store.save()

            except Exception as e:
                results.append({"account": acct_name, "error": str(e)})

    return {
        "message": f"SimpleFIN sync complete. {total_added} new transactions added ({from_date} → {to_date}).",
        "from_date": from_date,
        "to_date": to_date,
        "total_fetched": total_fetched,
        "total_new": total_added,
        "details": results,
    }
