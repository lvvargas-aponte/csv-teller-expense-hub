"""Account routes: list accounts, fetch transactions/balance, delete account,
and per-account user-supplied details (APR, due day, etc.)."""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote, unquote

from fastapi import APIRouter, HTTPException, Query

import state
from csv_parser import Transaction as CsvTransaction, BankType
from models import AccountDetails, AccountDetailsIn

logger = logging.getLogger(__name__)
router = APIRouter()


async def _fetch_simplefin_accounts_normalized() -> List[Dict[str, Any]]:
    """GET all SimpleFIN accounts, normalized into the Teller-shaped dict the
    frontend (AccountsModal/SyncModal) already knows how to render.

    Hidden accounts (see ``_promote_simplefin_account_to_manual_shadow``) are
    dropped, and a failed access URL becomes one ``_connection_error`` row —
    SimpleFIN reports errors per access URL, not per account, so there is no
    finer-grained placeholder to build.
    """
    from simplefin import infer_account_bucket

    url_batches, url_errors = await state.simplefin.list_accounts_by_url()
    out: List[Dict[str, Any]] = []

    for _url, accounts in url_batches:
        for acct in accounts:
            acct_id = acct.get("id")
            if not acct_id:
                continue
            shadow = state._manual_accounts.get(acct_id)
            if shadow and shadow.get("disconnected_from") == "simplefin":
                continue
            org_name = (acct.get("org") or {}).get("name") or "Bank"
            name = acct.get("name") or acct_id
            acct_type, acct_subtype = infer_account_bucket(name, org_name)
            out.append({
                "id": acct_id,
                "name": name,
                "type": acct_type,
                "subtype": acct_subtype,
                "institution": {"name": org_name},
                "balance": {},
                "_source": "simplefin",
            })

    for err in url_errors:
        masked = err.get("url", "")
        out.append({
            "id": f"_sferror_{quote(masked, safe='')}",
            "name": "Unknown account",
            "type": "", "subtype": "",
            "institution": {"name": "SimpleFIN"},
            "balance": {},
            "_connection_error": True,
            "_source": "simplefin",
        })

    return out


@router.get("/accounts")
async def get_accounts():
    """Fetch bank accounts across all stored Teller tokens and SimpleFIN access URLs."""
    accounts: List[Dict[str, Any]] = []
    if state.TELLER_ACCESS_TOKENS:
        accounts.extend(await state.teller.list_accounts())
    if state.SIMPLEFIN_ACCESS_URLS:
        accounts.extend(await _fetch_simplefin_accounts_normalized())
    _fill_error_institution_from_cache(accounts)
    return accounts


def _fill_error_institution_from_cache(accounts: List[Dict[str, Any]]) -> None:
    """Infer institution name on error placeholders from the balances cache.

    Teller's failing `/accounts` call gives us no institution name, so
    ``_error_entry`` defaults to "—". The frontend chip in the Accounts header
    already infers the bank by elimination (cached accounts whose ids no
    longer appear in the live list belong to the broken token). We do the
    same here so the Linked Bank Accounts modal shows the institution too.
    Heuristic: if only one institution's cached accounts disappeared, every
    error row gets that name; otherwise we round-robin through the
    disconnected institutions in cache order.
    """
    # Only Teller rows lack a `_source` tag (SimpleFIN rows already carry
    # their own institution name and must not be overwritten below).
    error_rows = [a for a in accounts if a.get("_connection_error") and not a.get("_source")]
    if not error_rows:
        return

    live_ids = {a.get("id") for a in accounts if not a.get("_connection_error")}
    cached = state._balances_cache.get("teller_accounts") or []

    disconnected_institutions: List[str] = []
    seen: set = set()
    for cached_acct in cached:
        if cached_acct.get("id") in live_ids:
            continue
        inst = cached_acct.get("institution")
        name = inst.get("name") if isinstance(inst, dict) else inst
        if not name or name == "—" or name in seen:
            continue
        seen.add(name)
        disconnected_institutions.append(name)

    if not disconnected_institutions:
        return

    for i, row in enumerate(error_rows):
        name = disconnected_institutions[min(i, len(disconnected_institutions) - 1)]
        row["institution"] = {"name": name}


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


def _promote_teller_account_to_manual_shadow(account_id: str) -> Optional[Dict[str, Any]]:
    """Convert a disconnected Teller account into a manual shadow record.

    Preserves the cached institution/name/type and last-known balance so the
    UI keeps rendering it (transactions stay linked via the same id, and the
    user can keep updating it manually). If the same id reappears via a
    later Teller reconnect, ``upsert_teller_account`` clears the shadow.

    Returns the manual record that was created, or None if the account isn't
    in the teller cache (e.g. it was already manual, or never cached).
    """
    cached = state._balances_cache.get("teller_accounts") or []
    target = next((a for a in cached if a.get("id") == account_id), None)
    if target is None:
        return None

    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    institution_name = ""
    inst = target.get("institution")
    if isinstance(inst, dict):
        institution_name = inst.get("name", "") or ""
    elif isinstance(inst, str):
        institution_name = inst

    shadow: Dict[str, Any] = {
        "id":               account_id,
        "institution":      institution_name,
        "name":             target.get("name", "") or "",
        "type":             target.get("type", "") or "",
        "subtype":          target.get("subtype", "") or "",
        "available":        float(target.get("available") or 0.0),
        "ledger":           float(target.get("ledger") or 0.0),
        "disconnected_from": "teller",
        "disconnected_at":  now,
    }
    state._manual_accounts[account_id] = shadow
    state._manual_accounts_store.save()

    remaining = [a for a in cached if a.get("id") != account_id]
    total_cash = sum(
        float(a.get("available") or 0.0)
        for a in remaining if a.get("type") == "depository"
    )
    total_credit = sum(
        float(a.get("ledger") or 0.0)
        for a in remaining if a.get("type") == "credit"
    )
    state._balances_cache_store.data["teller_accounts"] = remaining
    state._balances_cache_store.data["teller_cash"] = round(total_cash, 2)
    state._balances_cache_store.data["teller_credit_debt"] = round(total_credit, 2)
    state._balances_cache_store.save()

    from db.accounts_repo import get_repo
    get_repo().upsert_manual_account(
        account_id=account_id,
        institution=shadow["institution"],
        name=shadow["name"],
        type_=shadow["type"],
        subtype=shadow["subtype"],
    )
    return shadow


def _promote_simplefin_account_to_manual_shadow(account_id: str) -> Optional[Dict[str, Any]]:
    """Convert a hidden SimpleFIN account into a manual shadow record.

    SimpleFIN has no per-account revoke endpoint — the access URL stays
    active for every other account behind it. This purely local hide keeps
    the id out of ``/accounts`` and every future sync (both check for the
    ``disconnected_from == "simplefin"`` shadow). To "reconnect", the user
    deletes this shadow permanently (the modal's "Delete permanently" flow)
    and the account reappears on the next fetch/sync.
    """
    cached = state._balances_cache.get("simplefin_accounts") or []
    target = next((a for a in cached if a.get("id") == account_id), None)
    if target is None:
        return None

    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    shadow: Dict[str, Any] = {
        "id":               account_id,
        "institution":      target.get("institution", "") or "",
        "name":             target.get("name", "") or "",
        "type":             target.get("type", "") or "",
        "subtype":          target.get("subtype", "") or "",
        "available":        float(target.get("available") or 0.0),
        "ledger":           float(target.get("ledger") or 0.0),
        "disconnected_from": "simplefin",
        "disconnected_at":  now,
    }
    state._manual_accounts[account_id] = shadow
    state._manual_accounts_store.save()

    remaining = [a for a in cached if a.get("id") != account_id]
    total_cash = sum(
        float(a.get("available") or 0.0)
        for a in remaining if a.get("type") == "depository"
    )
    total_credit = sum(
        float(a.get("ledger") or 0.0)
        for a in remaining if a.get("type") == "credit"
    )
    state._balances_cache_store.data["simplefin_accounts"] = remaining
    state._balances_cache_store.data["simplefin_cash"] = round(total_cash, 2)
    state._balances_cache_store.data["simplefin_credit_debt"] = round(total_credit, 2)
    state._balances_cache_store.save()

    from db.accounts_repo import get_repo
    get_repo().upsert_manual_account(
        account_id=account_id,
        institution=shadow["institution"],
        name=shadow["name"],
        type_=shadow["type"],
        subtype=shadow["subtype"],
    )
    return shadow


@router.delete("/accounts/{account_id}")
async def delete_account(
    account_id: str,
    purge: bool = Query(
        False,
        description=(
            "Default (false) disconnects the account at Teller but keeps the "
            "local record so transactions, balances, and APR/limit details "
            "survive — reconnecting the same account will pick it back up. "
            "Pass true to also remove the local record permanently."
        ),
    ),
):
    """Disconnect (and optionally purge) a Teller account.

    Default behavior preserves the account locally as a manual shadow so the
    user can keep updating the balance and the history doesn't vanish. The
    ``?purge=true`` variant removes the local record entirely — the frontend
    gates this behind a "type 'delete' to confirm" prompt.
    """
    if (
        not state.TELLER_ACCESS_TOKENS
        and not state.SIMPLEFIN_ACCESS_URLS
        and not account_id.startswith(("_error_", "_sferror_"))
    ):
        if not (purge and account_id in state._manual_accounts):
            raise HTTPException(status_code=500, detail="No Teller or SimpleFIN connections configured.")

    # SimpleFIN error placeholder (id starts with "_sferror_") — SimpleFIN
    # reports errors per access URL, not per account, so removing it drops
    # the whole connection (every account behind that URL disappears too).
    if account_id.startswith("_sferror_"):
        from helpers import _env_remove_simplefin_url

        masked = unquote(account_id[len("_sferror_"):])
        removed = state.simplefin.remove_by_masked(masked)
        if not removed:
            raise HTTPException(status_code=404, detail="No matching SimpleFIN connection found.")
        _env_remove_simplefin_url(removed)
        logger.info("[SimpleFIN] Removed broken access URL (error account deleted).")
        return {"deleted": account_id, "purged": True}

    # Error-placeholder accounts (id starts with "_error_") have no real Teller account to
    # call; just remove the broken token from memory and .env directly. There is no
    # local record to preserve, so ?purge is ignored here.
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
        return {"deleted": account_id, "purged": True}

    is_simplefin_account = any(
        a.get("id") == account_id
        for a in (state._balances_cache.get("simplefin_accounts") or [])
    )

    if purge:
        # Hard delete: revoke at Teller if we still hold a token for it, then
        # drop the local manual shadow + details. Tolerate the Teller call
        # failing (token already gone) — the user explicitly asked to wipe.
        # SimpleFIN accounts skip the revoke call entirely — there is no
        # per-account revoke endpoint, so purging one just drops local state
        # (the access URL itself is untouched; see /simplefin/connections).
        if state.TELLER_ACCESS_TOKENS and not is_simplefin_account:
            try:
                await state.teller.delete_account(account_id)
            except Exception as e:
                logger.warning(f"[Teller] purge: revoke at Teller failed for {account_id}: {e}")

        existed = False
        if account_id in state._manual_accounts:
            del state._manual_accounts[account_id]
            state._manual_accounts_store.save()
            existed = True

        cached = state._balances_cache.get("teller_accounts") or []
        if any(a.get("id") == account_id for a in cached):
            state._balances_cache_store.data["teller_accounts"] = [
                a for a in cached if a.get("id") != account_id
            ]
            state._balances_cache_store.save()
            existed = True

        sf_cached = state._balances_cache.get("simplefin_accounts") or []
        if any(a.get("id") == account_id for a in sf_cached):
            state._balances_cache_store.data["simplefin_accounts"] = [
                a for a in sf_cached if a.get("id") != account_id
            ]
            state._balances_cache_store.save()
            existed = True

        if account_id in state.account_details:
            del state.account_details[account_id]
            state._account_details_store.save()

        from db.accounts_repo import get_repo
        if get_repo().delete_manual_account(account_id):
            existed = True

        if not existed:
            raise HTTPException(status_code=404, detail="Account not found.")
        return {"deleted": account_id, "purged": True}

    # SimpleFIN: no per-account revoke — hide locally, leave the access URL
    # (and every other account behind it) untouched.
    if is_simplefin_account:
        if not _promote_simplefin_account_to_manual_shadow(account_id):
            raise HTTPException(status_code=404, detail="Account not found.")
        return {"deleted": account_id, "purged": False}

    # Default: disconnect at Teller, keep the record locally as a manual shadow.
    if not await state.teller.delete_account(account_id):
        raise HTTPException(
            status_code=404,
            detail="Account not found or no valid token could disconnect it.",
        )

    _promote_teller_account_to_manual_shadow(account_id)
    return {"deleted": account_id, "purged": False}


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
    for acct in state._balances_cache.get("simplefin_accounts", []) or []:
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
