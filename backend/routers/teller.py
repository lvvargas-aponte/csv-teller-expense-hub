"""Teller routes: config, token registration/replacement, and sync."""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

import state
from csv_parser import Transaction as CsvTransaction, BankType
from helpers import (
    _env_add_token,
    _env_remove_token,
    _log_token_event,
    _previous_month_range,
    infer_txn_type,
)
from models import RegisterTokenRequest, ReplaceTokenRequest, TellerSyncRequest
from routers.balances import persist_teller_balances
from teller import _mask_token
from config import TELLER_APP_ID, TELLER_ENVIRONMENT

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/config/teller")
async def get_teller_config() -> Dict[str, str]:
    """Expose Teller public configuration to the frontend."""
    if not TELLER_APP_ID:
        raise HTTPException(status_code=503, detail="TELLER_APP_ID is not configured on the server.")
    return {"application_id": TELLER_APP_ID, "environment": TELLER_ENVIRONMENT}


def _remove_broken_token_via_error_id(old_account_id: Optional[str]) -> Optional[str]:
    """If the caller is reconnecting from an _error_ row, clean the dead token out.

    Returns the removed token for logging, or None if no cleanup was needed.
    Silent when the id doesn't start with _error_ or isn't in the map — the
    caller just wants a best-effort cleanup alongside their real work.
    """
    if not old_account_id or not old_account_id.startswith("_error_"):
        return None
    broken = state.teller.pop_error_token(old_account_id)
    if not broken:
        return None
    if broken in state.TELLER_ACCESS_TOKENS:
        state.TELLER_ACCESS_TOKENS.remove(broken)
    enrollment_id = state.teller.get_enrollment_id(broken)
    if enrollment_id:
        state.teller._enrollment_map.pop(enrollment_id, None)
    _env_remove_token(broken)
    logger.info(
        f"[Teller] Removed broken token {_mask_token(broken)} "
        f"as part of reconnect from {old_account_id}."
    )
    return broken


@router.post("/teller/register-token", status_code=201)
async def register_teller_token(req: RegisterTokenRequest):
    """
    Persist a new Teller access token received from the frontend after enrollment.
    Adds to the in-memory token list (effective immediately), persists to .env,
    and appends an audit entry to teller-tokens.log.
    """
    token = req.access_token.strip()
    if not token:
        raise HTTPException(status_code=422, detail="access_token must not be empty.")

    # Opportunistic cleanup: if the user is reconnecting from a "Connection
    # Error" row, strip the dead token first so it doesn't linger next to the
    # freshly-registered one.
    _remove_broken_token_via_error_id(req.old_account_id)

    if token in state.TELLER_ACCESS_TOKENS:
        logger.info(f"[Teller] Token {_mask_token(token)} already registered — skipping.")
        return {"registered": False, "reason": "duplicate", "total_tokens": len(state.TELLER_ACCESS_TOKENS)}

    state.TELLER_ACCESS_TOKENS.append(token)
    state.teller._enrollment_map[req.enrollment_id] = token
    logger.info(f"[Teller] New token {_mask_token(token)} added ({len(state.TELLER_ACCESS_TOKENS)} total).")

    _env_add_token(token)
    _log_token_event(token=token, enrollment_id=req.enrollment_id, institution=req.institution)

    return {"registered": True, "total_tokens": len(state.TELLER_ACCESS_TOKENS)}


@router.post("/teller/replace-token", status_code=200)
async def replace_teller_token(req: ReplaceTokenRequest):
    """
    Replace a broken token with a fresh one obtained via Teller Connect re-auth.
    Looks up the old token by enrollment_id, removes it, then registers the new one.
    """
    new_token = req.new_access_token.strip()
    if not new_token:
        raise HTTPException(status_code=422, detail="new_access_token must not be empty.")

    # 1. Find and remove the old token
    old_token = state.teller._enrollment_map.get(req.old_enrollment_id)
    if old_token and old_token in state.TELLER_ACCESS_TOKENS:
        state.TELLER_ACCESS_TOKENS.remove(old_token)
        logger.info(
            f"[Teller] Removed stale token {_mask_token(old_token)} "
            f"for enrollment {req.old_enrollment_id}."
        )
        _env_remove_token(old_token)
    else:
        # Enrollment map didn't know about this enrollment (common after a
        # backend restart, which resets the in-memory map).  Fall back to the
        # error-row id so the dead token is still cleaned up.
        _remove_broken_token_via_error_id(req.old_account_id)

    # 2. Register the new token (skip if already present — same token returned by Teller)
    if new_token not in state.TELLER_ACCESS_TOKENS:
        state.TELLER_ACCESS_TOKENS.append(new_token)

    # Update enrollment map; clean up old entry if the id changed
    state.teller._enrollment_map[req.new_enrollment_id] = new_token
    if req.old_enrollment_id != req.new_enrollment_id:
        state.teller._enrollment_map.pop(req.old_enrollment_id, None)

    _env_add_token(new_token)
    _log_token_event(
        token=new_token,
        enrollment_id=req.new_enrollment_id,
        institution=req.institution,
        note=f"replaced: {req.old_enrollment_id}",
    )
    logger.info(
        f"[Teller] Token replaced for enrollment {req.old_enrollment_id} → {req.new_enrollment_id}."
    )

    return {"replaced": True, "total_tokens": len(state.TELLER_ACCESS_TOKENS)}


@router.post("/teller/sync")
async def sync_teller_transactions(req: TellerSyncRequest = None):
    """Pull transactions from ALL stored access tokens, filtered by date range."""
    if req is None:
        req = TellerSyncRequest()

    if not state.TELLER_ACCESS_TOKENS:
        raise HTTPException(
            status_code=500,
            detail="No Teller access tokens configured. Set TELLER_API_KEY in your .env file.",
        )

    from_date, to_date = _previous_month_range()
    if req.from_date:
        from_date = req.from_date
    if req.to_date:
        to_date = req.to_date

    total_fetched = 0
    total_added = 0

    token_batches, token_errors = await state.teller.list_accounts_by_token()
    results: List[Dict[str, Any]] = list(token_errors)

    # Refresh the balances cache using the same account data we just fetched —
    # otherwise the Finances page keeps showing stale balances after a sync.
    try:
        await persist_teller_balances(token_batches)
    except Exception as e:
        logger.warning(f"[Teller] Could not refresh balances cache during sync: {e}")

    for token, accounts in token_batches:
        for account in accounts:
            if req.account_ids is not None and account["id"] not in req.account_ids:
                continue
            acct_name = (
                f"{account.get('institution', {}).get('name', 'Bank')} "
                f"– {account.get('name', account['id'])}"
            )
            try:
                all_txns = await state.teller.fetch_account_transactions(
                    account["id"], token, req.count
                )

                filtered = [
                    t for t in all_txns
                    if from_date <= t.get("date", "") <= to_date
                ]

                added = 0
                acct_institution = account.get("institution", {}).get("name", "")
                acct_type = account.get("subtype", "") or account.get("type", "")
                acct_category = account.get("type", "")   # broad: "depository" | "credit"

                # Build running_balance sequence so we can infer CR/DR for depository accounts.
                # IMPORTANT: Do NOT sort by date here. Teller's running_balance is only
                # valid in Teller's native sequence. Reversing gives oldest-first,
                # which preserves the running_balance chain correctly.
                all_txns_sorted = list(reversed(all_txns))
                balance_seq = [
                    (t["id"], float(t["running_balance"]))
                    for t in all_txns_sorted
                    if t.get("running_balance") is not None
                ]
                balance_index = {tid: i for i, (tid, _) in enumerate(balance_seq)}

                for t in filtered:
                    amt = float(t.get("amount", 0))
                    txn = CsvTransaction(
                        date=t.get("date", ""),
                        description=t.get("description", ""),
                        amount=abs(amt),
                        source=BankType.TELLER,
                        transaction_id=t.get("id"),
                        account_id=account["id"],
                        category=t.get("details", {}).get("category"),
                        institution=acct_institution,
                        transaction_type=infer_txn_type(
                            t, amt,
                            acct_category=acct_category,
                            balance_seq=balance_seq,
                            balance_index=balance_index,
                        ),
                        account_type=acct_type,
                    )
                    if txn.transaction_id not in state.stored_transactions:
                        state.stored_transactions[txn.transaction_id] = txn.to_dict()
                        added += 1
                    else:
                        existing = state.stored_transactions[txn.transaction_id]
                        for field in ("transaction_type", "account_type", "category",
                                      "institution", "description", "amount", "date"):
                            existing[field] = getattr(txn, field)
                        # PgStore returns a fresh dict snapshot; write back to persist.
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
                enrollment_status = ""
                if hasattr(e, "response") and e.response is not None:
                    enrollment_status = e.response.headers.get(
                        "teller-enrollment-status", ""
                    )
                results.append({
                    "account": acct_name,
                    "error": str(e),
                    "enrollment_status": enrollment_status or None,
                })

    return {
        "message": f"Teller sync complete. {total_added} new transactions added ({from_date} → {to_date}).",
        "from_date": from_date,
        "to_date": to_date,
        "total_fetched": total_fetched,
        "total_new": total_added,
        "details": results,
    }
