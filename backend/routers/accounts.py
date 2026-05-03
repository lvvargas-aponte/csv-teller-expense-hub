"""Account routes: list accounts, fetch transactions/balance, delete account,
and per-account user-supplied details (APR, due day, etc.)."""
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException

import state
from csv_parser import Transaction as CsvTransaction, BankType
from models import AccountDetails, AccountDetailsIn

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/accounts")
async def get_accounts():
    """Fetch bank accounts across all stored access tokens."""
    if not state.TELLER_ACCESS_TOKENS:
        return []
    return await state.teller.list_accounts()


@router.get("/accounts/{account_id}/transactions", response_model=List[Dict])
async def get_transactions(
    account_id: str,
    count: int = 100,
    access_token: Optional[str] = None,
):
    """Fetch transactions for a specific account."""
    tokens_to_try = ([access_token] if access_token else []) + state.TELLER_ACCESS_TOKENS
    if not tokens_to_try:
        raise HTTPException(status_code=500, detail="No Teller access token available.")

    teller_transactions = await state.teller.list_transactions(account_id, count, tokens_to_try)
    for t in teller_transactions:
        transaction = CsvTransaction(
            date=t.get("date", ""),
            description=t.get("description", ""),
            amount=float(t.get("amount", 0)),
            source=BankType.TELLER,
            transaction_id=t.get("id"),
            category=t.get("details", {}).get("category"),
        )
        state.stored_transactions[transaction.transaction_id] = transaction.to_dict()
    # Persist so these transactions survive a backend restart — the other mutation
    # endpoints (/upload-csv, /transactions/{id}, /teller/sync) all save; without
    # this call, clicking an account to view its transactions was in-memory only.
    if teller_transactions:
        state._transactions_store.save()
    return teller_transactions


@router.get("/accounts/{account_id}/balance")
async def get_balance(account_id: str, access_token: Optional[str] = None):
    """Get account balance."""
    tokens_to_try = ([access_token] if access_token else []) + state.TELLER_ACCESS_TOKENS
    if not tokens_to_try:
        raise HTTPException(status_code=500, detail="No Teller access token available.")
    return await state.teller.get_balance(account_id, tokens_to_try)


@router.delete("/accounts/{account_id}")
async def delete_account(account_id: str):
    """Disconnect a specific Teller account from its enrollment."""
    if not state.TELLER_ACCESS_TOKENS:
        raise HTTPException(status_code=500, detail="No Teller access tokens configured.")

    # Error-placeholder accounts (id starts with "_error_") have no real Teller account to
    # call; just remove the broken token from memory and .env directly.
    if account_id.startswith("_error_"):
        from helpers import _env_remove_token

        # The client hands us back the exact id it was rendered with, so a
        # map lookup is unambiguous (no token[:8]+token[-4:] mask collisions).
        token_to_remove = state.teller.pop_error_token(account_id)
        if not token_to_remove or token_to_remove not in state.TELLER_ACCESS_TOKENS:
            raise HTTPException(status_code=404, detail="No matching token found for this error account.")
        state.TELLER_ACCESS_TOKENS.remove(token_to_remove)
        enrollment_id = state.teller.get_enrollment_id(token_to_remove)
        if enrollment_id:
            state.teller._enrollment_map.pop(enrollment_id, None)
        _env_remove_token(token_to_remove)
        logger.info(f"[Teller] Removed broken token {token_to_remove[:8]}... (error account deleted).")
        return {"deleted": account_id}

    if not await state.teller.delete_account(account_id):
        raise HTTPException(
            status_code=404,
            detail="Account not found or no valid token could disconnect it.",
        )
    # Drop the side-car details too so reconnecting a fresh enrollment doesn't
    # inherit stale APR / due-day data belonging to the disconnected account.
    if account_id in state.account_details:
        del state.account_details[account_id]
        state._account_details_store.save()
    return {"deleted": account_id}


# ---------------------------------------------------------------------------
# Per-account details (APR, due day, credit limit, …)
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _validate_day(label: str, value: Optional[int]) -> None:
    if value is None:
        return
    if not (1 <= int(value) <= 31):
        raise HTTPException(status_code=422, detail=f"{label} must be between 1 and 31")


@router.get("/accounts/details", response_model=Dict[str, Optional[AccountDetails]])
async def get_all_account_details():
    """Return details for every known account in one call.

    Keys are the union of account ids across ``state.account_details``,
    manual/csv accounts, and cached Teller accounts. Value is the record
    if the user has configured details, otherwise ``null``. Replaces the
    per-account GET pattern that spammed 404s on every page load.
    """
    known_ids: set[str] = set()
    known_ids.update(state.account_details.keys())
    known_ids.update(state._manual_accounts.keys())
    for acct in state._balances_cache.get("teller_accounts", []) or []:
        if isinstance(acct, dict) and acct.get("id"):
            known_ids.add(acct["id"])

    return {
        aid: AccountDetails(**state.account_details[aid])
        if aid in state.account_details
        else None
        for aid in known_ids
    }


@router.get("/accounts/{account_id}/details", response_model=AccountDetails)
async def get_account_details(account_id: str):
    """Return the side-car details for an account, 404 if none set."""
    record = state.account_details.get(account_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No details set for this account")
    return AccountDetails(**record)


@router.put("/accounts/{account_id}/details", response_model=AccountDetails)
async def upsert_account_details(account_id: str, req: AccountDetailsIn):
    """Create or replace the side-car details for an account."""
    _validate_day("statement_day", req.statement_day)
    _validate_day("due_day", req.due_day)
    if req.apr is not None and req.apr < 0:
        raise HTTPException(status_code=422, detail="apr must be >= 0")

    existing = state.account_details.get(account_id)
    record: Dict = {
        "account_id":      account_id,
        "apr":             req.apr,
        "credit_limit":    req.credit_limit,
        "minimum_payment": req.minimum_payment,
        "statement_day":   req.statement_day,
        "due_day":         req.due_day,
        "notes":           req.notes,
        "created":         existing.get("created", _now_iso()) if existing else _now_iso(),
        "updated":         _now_iso(),
    }
    state.account_details[account_id] = record
    state._account_details_store.save()
    return AccountDetails(**record)


@router.delete("/accounts/{account_id}/details", status_code=204)
async def delete_account_details(account_id: str):
    """Remove the side-car details for an account."""
    if account_id not in state.account_details:
        raise HTTPException(status_code=404, detail="No details set for this account")
    del state.account_details[account_id]
    state._account_details_store.save()
