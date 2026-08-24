"""Account routes: list accounts, delete account, and per-account
user-supplied details (APR, due day, etc.)."""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query

import analytics
import state
from institution_normalizer import normalize as normalize_institution
from models import AccountDetails, AccountDetailsIn

logger = logging.getLogger(__name__)
router = APIRouter()

# Synthetic account id standing in for a whole failed access URL — SimpleFIN
# reports errors per connection, not per account. The suffix is a
# ``simplefin.connection_id``.
_SF_ERROR_PREFIX = "_sferror_"


async def _fetch_simplefin_accounts_normalized() -> List[Dict[str, Any]]:
    """GET all SimpleFIN accounts, normalized into the dict shape the
    frontend (AccountsModal/SyncModal) knows how to render.

    Hidden accounts (see ``_promote_simplefin_account_to_manual_shadow``) are
    dropped, and a failed access URL becomes one ``_connection_error`` row —
    SimpleFIN reports errors per access URL, not per account, so there is no
    finer-grained placeholder to build.
    """
    from balances_service import is_simplefin_account_hidden
    from simplefin import iter_normalized_accounts

    url_batches, url_errors = await state.simplefin.list_accounts_by_url()
    out: List[Dict[str, Any]] = [
        {
            "id": acct["id"],
            "name": acct["name"],
            "type": acct["type"],
            "subtype": acct["subtype"],
            # Normalized here for the same reason the balances summary
            # normalizes: consumers match the two lists by institution name,
            # and a raw "Chase Bank" against a canonical "Chase" reads as a
            # missing — therefore broken — connection.
            "institution": {"name": normalize_institution(acct["institution"])},
            "balance": {},
            "_source": "simplefin",
        }
        for acct in iter_normalized_accounts(url_batches, is_simplefin_account_hidden)
    ]

    for err in url_errors:
        out.append({
            "id": f"{_SF_ERROR_PREFIX}{err.get('id', '')}",
            "name": "Unknown account",
            "type": "", "subtype": "",
            "institution": {"name": "SimpleFIN"},
            "balance": {},
            "_connection_error": True,
            "_connection_label": err.get("label", ""),
            "_source": "simplefin",
        })

    return out


def _manual_accounts_normalized() -> List[Dict[str, Any]]:
    """User-added accounts in the same shape as the SimpleFIN rows.

    SimpleFIN shadows (``disconnected_from`` set) are excluded — a shadow
    exists precisely to keep a hidden account out of this list.
    """
    return [
        {
            "id": acct["id"],
            "name": acct.get("name", ""),
            "type": acct.get("type", ""),
            "subtype": acct.get("subtype", ""),
            "institution": {"name": normalize_institution(acct.get("institution", ""))},
            "balance": {},
            "_source": "manual",
        }
        for acct in state._manual_accounts.values()
        if not acct.get("disconnected_from")
    ]


@router.get("/accounts/metadata")
async def get_accounts_metadata() -> Dict[str, Any]:
    """Classification vocabulary the frontend needs to bucket accounts.

    The subtype list exists in Python and again in JS; served from here it has
    one owner, and the JS copy is only a fallback for an offline load.
    """
    return {"investment_subtypes": sorted(analytics._INVESTMENT_SUBTYPES)}


@router.get("/accounts")
async def get_accounts() -> List[Dict[str, Any]]:
    """Fetch every account the user can manage — SimpleFIN-synced and manual."""
    accounts: List[Dict[str, Any]] = []
    if state.SIMPLEFIN_ACCESS_URLS:
        accounts.extend(await _fetch_simplefin_accounts_normalized())
    accounts.extend(_manual_accounts_normalized())
    return accounts


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

    from balances_service import write_simplefin_cache
    write_simplefin_cache([a for a in cached if a.get("id") != account_id])

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
            "Default (false) hides the SimpleFIN account locally but keeps the "
            "local record so transactions, balances, and APR/limit details "
            "survive — deleting the connection's access URL later or "
            "reconnecting will pick it back up. "
            "Pass true to also remove the local record permanently."
        ),
    ),
):
    """Disconnect (and optionally purge) a SimpleFIN account.

    Default behavior preserves the account locally as a manual shadow so the
    user can keep updating the balance and the history doesn't vanish. The
    ``?purge=true`` variant removes the local record entirely — the frontend
    gates this behind a "type 'delete' to confirm" prompt.
    """
    if (
        not state.SIMPLEFIN_ACCESS_URLS
        and not account_id.startswith(_SF_ERROR_PREFIX)
    ):
        if not (purge and account_id in state._manual_accounts):
            raise HTTPException(status_code=500, detail="No SimpleFIN connections configured.")

    # SimpleFIN error placeholder — SimpleFIN reports errors per access URL,
    # not per account, so removing it drops the whole connection (every
    # account behind that URL disappears too). Delegated to the SimpleFIN
    # router, which owns access-URL lifecycle.
    if account_id.startswith(_SF_ERROR_PREFIX):
        from routers.simplefin import remove_simplefin_connection

        await remove_simplefin_connection(account_id[len(_SF_ERROR_PREFIX):])
        return {"deleted": account_id, "purged": True}

    is_simplefin_account = any(
        a.get("id") == account_id
        for a in (state._balances_cache.get("simplefin_accounts") or [])
    )

    if purge:
        # Hard delete: drop the local manual shadow + details. SimpleFIN
        # accounts have no per-account revoke endpoint, so purging one just
        # drops local state (the access URL itself is untouched; see
        # /simplefin/connections).
        existed = False
        if account_id in state._manual_accounts:
            del state._manual_accounts[account_id]
            state._manual_accounts_store.save()
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

    raise HTTPException(status_code=404, detail="Account not found.")


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
    manual/csv accounts, and cached SimpleFIN accounts. Value is the record
    if the user has configured details, otherwise ``null``. Replaces the
    per-account GET pattern that spammed 404s on every page load.
    """
    known_ids: set[str] = set()
    known_ids.update(state.account_details.keys())
    known_ids.update(state._manual_accounts.keys())
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
