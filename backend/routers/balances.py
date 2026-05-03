"""Balances routes: summary and manual account management."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, HTTPException, Query

import state
from models import (
    AccountBalance,
    BalancesSummary,
    ManualAccountIn,
    ManualAccountUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _append_manual_accounts(
    accounts_out: List[AccountBalance],
    total_cash: float,
    total_credit_debt: float,
) -> Tuple[List[AccountBalance], float, float]:
    """Merge manually-added accounts into the running totals.

    Investment accounts are not summed here — ``_compute_investments``
    walks the final accounts list separately so the same classification
    rules (subtype-aware) apply uniformly to Teller and manual rows.
    """
    from analytics import _classify_account_bucket

    for acct in state._manual_accounts.values():
        available = float(acct.get("available", 0.0))
        ledger = float(acct.get("ledger", 0.0))
        acct_type = acct.get("type", "depository")
        bucket = _classify_account_bucket(acct_type, acct.get("subtype", ""))
        if bucket == "cash":
            total_cash += available
        elif bucket == "credit":
            total_credit_debt += ledger
        accounts_out.append(AccountBalance(
            id=acct["id"],
            institution=acct.get("institution", ""),
            name=acct.get("name", ""),
            type=acct_type,
            subtype=acct.get("subtype", ""),
            available=available,
            ledger=ledger,
            manual=True,
        ))
    return accounts_out, total_cash, total_credit_debt


def _compute_investments(accounts: List[AccountBalance]) -> float:
    """Sum the value of every investment / retirement account in ``accounts``.

    Uses ``analytics._classify_account_bucket`` so the Accounts modal,
    advisor snapshot, and balances summary all agree on what counts as
    an investment.
    """
    from analytics import _classify_account_bucket

    total = 0.0
    for a in accounts:
        if _classify_account_bucket(a.type, a.subtype) != "investment":
            continue
        value = float(a.available or 0.0) or float(a.ledger or 0.0)
        total += value
    return round(total, 2)


async def persist_teller_balances(
    token_batches: List[Tuple[str, List[Dict[str, Any]]]],
) -> Tuple[List[AccountBalance], float, float]:
    """Walk already-fetched Teller account data, pull live per-account balances,
    write the cache, and return (accounts, teller_cash, teller_credit_debt).

    Per the Teller API, ``GET /accounts`` returns only metadata (no balance) —
    we must call ``GET /accounts/{id}/balances`` for each account.  Shared by
    ``/balances/summary?force=true`` and ``/teller/sync`` so that syncing also
    refreshes the balances panel instead of leaving it stale.
    """
    from db.accounts_repo import get_repo

    repo = get_repo()
    accounts_out: List[AccountBalance] = []
    total_cash = 0.0
    total_credit_debt = 0.0
    seen_ids: set[str] = set()

    for token, accounts in token_batches:
        for acct in accounts:
            if acct["id"] in seen_ids:
                continue
            seen_ids.add(acct["id"])
            # Keep the structured `accounts` table in sync with whatever
            # Teller just returned. Phase 4: Teller sync / balance refresh
            # is the only writer for source='teller' rows.
            repo.upsert_teller_account(acct)

            # Some test fixtures (and older code paths) set `balance` inline on
            # the account dict; prefer that when present, otherwise call Teller.
            bal = acct.get("balance")
            if not bal:
                bal = await state.teller.fetch_balance_safe(acct["id"], token) or {}

            # Teller returns numeric balances as strings ("28575.02") — coerce.
            try:
                available = float(bal.get("available") or 0.0)
            except (TypeError, ValueError):
                available = 0.0
            try:
                ledger = float(bal.get("ledger") or 0.0)
            except (TypeError, ValueError):
                ledger = 0.0

            acct_type = acct.get("type", "")
            if acct_type == "depository":
                total_cash += available
            elif acct_type == "credit":
                total_credit_debt += ledger

            accounts_out.append(AccountBalance(
                id=acct["id"],
                institution=acct.get("institution", {}).get("name", ""),
                name=acct.get("name", ""),
                type=acct_type,
                subtype=acct.get("subtype", ""),
                available=available,
                ledger=ledger,
            ))

            # Phase 5: append a timeseries row for this account/refresh.
            repo.insert_balance_snapshot(
                account_id=acct["id"],
                source="teller",
                available=available,
                ledger=ledger,
                raw=bal if isinstance(bal, dict) else None,
            )

    state._balances_cache_store.data.update({
        "fetched_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        "teller_accounts": [a.model_dump() for a in accounts_out],
        "teller_cash": round(total_cash, 2),
        "teller_credit_debt": round(total_credit_debt, 2),
    })
    state._balances_cache_store.save()

    return accounts_out, total_cash, total_credit_debt


@router.get("/balances/summary", response_model=BalancesSummary)
async def get_balances_summary(force: bool = Query(False)):
    """Aggregate balances across all accounts and compute net worth.

    Teller data is served exclusively from the DB-backed cache — page loads
    and tab switches never hit Teller. Only ``?force=true`` (wired to the
    Refresh button in the UI) bypasses the cache and issues live Teller
    calls. Manual/CSV accounts are always merged in live from the DB.
    """
    if not force:
        cached_accounts = [
            AccountBalance(**a)
            for a in state._balances_cache.get("teller_accounts", [])
        ]
        teller_cash = state._balances_cache.get("teller_cash", 0.0)
        teller_credit = state._balances_cache.get("teller_credit_debt", 0.0)
        cached_accounts, total_cash, total_credit_debt = _append_manual_accounts(
            cached_accounts, teller_cash, teller_credit
        )
        fetched_at = state._balances_cache.get("fetched_at")
        total_investments = _compute_investments(cached_accounts)
        return BalancesSummary(
            net_worth=round(total_cash + total_investments - total_credit_debt, 2),
            total_cash=round(total_cash, 2),
            total_credit_debt=round(total_credit_debt, 2),
            total_investments=total_investments,
            accounts=cached_accounts,
            from_cache=fetched_at is not None,
            cache_fetched_at=fetched_at,
        )

    # ── force=true: fetch live from Teller ───────────────────────────────────
    if not state.TELLER_ACCESS_TOKENS:
        accounts_out, total_cash, total_credit_debt = _append_manual_accounts([], 0.0, 0.0)
        total_investments = _compute_investments(accounts_out)
        return BalancesSummary(
            net_worth=round(total_cash + total_investments - total_credit_debt, 2),
            total_cash=round(total_cash, 2),
            total_credit_debt=round(total_credit_debt, 2),
            total_investments=total_investments,
            accounts=accounts_out,
        )

    token_batches, _ = await state.teller.list_accounts_by_token()
    accounts_out, total_cash, total_credit_debt = await persist_teller_balances(token_batches)

    accounts_out, total_cash, total_credit_debt = _append_manual_accounts(
        accounts_out, total_cash, total_credit_debt
    )
    total_investments = _compute_investments(accounts_out)
    return BalancesSummary(
        net_worth=round(total_cash + total_investments - total_credit_debt, 2),
        total_cash=round(total_cash, 2),
        total_credit_debt=round(total_credit_debt, 2),
        total_investments=total_investments,
        accounts=accounts_out,
        from_cache=False,
        cache_fetched_at=state._balances_cache.get("fetched_at"),
    )


@router.post("/balances/manual", response_model=AccountBalance, status_code=201)
async def add_manual_account(req: ManualAccountIn):
    """Persist a user-added account balance (for banks not connected via Teller)."""
    from db.accounts_repo import get_repo

    repo = get_repo()
    acct_id = f"manual_{uuid.uuid4().hex[:12]}"
    record: Dict[str, Any] = {
        "id":          acct_id,
        "institution": req.institution,
        "name":        req.name,
        "type":        req.type,
        "subtype":     req.subtype,
        "available":   req.available,
        "ledger":      req.ledger,
    }
    state._manual_accounts[acct_id] = record
    state._manual_accounts_store.save()

    # Phase 5: mirror into structured tables so the account can anchor
    # a balance_snapshots timeseries (FK target).
    repo.upsert_manual_account(
        account_id=acct_id,
        institution=req.institution,
        name=req.name,
        type_=req.type,
        subtype=req.subtype,
    )
    repo.insert_balance_snapshot(
        account_id=acct_id,
        source="manual",
        available=req.available,
        ledger=req.ledger,
        raw={"available": req.available, "ledger": req.ledger},
    )

    return AccountBalance(**record, manual=True)


@router.put("/balances/manual/{account_id}", response_model=AccountBalance)
async def update_manual_account(account_id: str, req: ManualAccountUpdate):
    """Edit the available/ledger balance on a manual or csv-synth account.

    Appends a fresh ``balance_snapshots`` row (``source='manual'``) so the
    edit shows up on timeseries dashboards. Either field may be omitted to
    leave its current value untouched.
    """
    from db.accounts_repo import get_repo

    record = state._manual_accounts.get(account_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Manual account not found")

    if req.available is None and req.ledger is None:
        raise HTTPException(
            status_code=422,
            detail="At least one of available or ledger must be provided",
        )

    if req.available is not None:
        record["available"] = float(req.available)
    if req.ledger is not None:
        record["ledger"] = float(req.ledger)

    state._manual_accounts[account_id] = record
    state._manual_accounts_store.save()

    get_repo().insert_balance_snapshot(
        account_id=account_id,
        source="manual",
        available=record.get("available"),
        ledger=record.get("ledger"),
        raw={"available": record.get("available"), "ledger": record.get("ledger")},
    )

    return AccountBalance(**record, manual=True)


@router.put("/balances/{account_id}", response_model=AccountBalance)
async def update_account_balance(account_id: str, req: ManualAccountUpdate):
    """Edit available/ledger for any account — manual, csv-synth, or Teller-cached.

    For Teller accounts the override is written into the cached balances
    payload; the next ``?force=true`` refresh will overwrite it with whatever
    Teller reports. A balance_snapshots row is appended either way so the
    edit shows up on net-worth history.
    """
    from db.accounts_repo import get_repo

    if req.available is None and req.ledger is None:
        raise HTTPException(
            status_code=422,
            detail="At least one of available or ledger must be provided",
        )

    # Manual / csv-synth — delegate to the existing path so behavior matches.
    if account_id in state._manual_accounts:
        return await update_manual_account(account_id, req)

    # Teller-cached account — mutate the cache in place.
    teller_accounts = state._balances_cache.get("teller_accounts") or []
    target = next((a for a in teller_accounts if a.get("id") == account_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="Account not found")

    if req.available is not None:
        target["available"] = float(req.available)
    if req.ledger is not None:
        target["ledger"] = float(req.ledger)

    # Recompute cached totals from the (possibly mutated) account list so
    # the summary endpoint reflects the override on the very next call.
    total_cash = sum(
        float(a.get("available") or 0.0)
        for a in teller_accounts if a.get("type") == "depository"
    )
    total_credit = sum(
        float(a.get("ledger") or 0.0)
        for a in teller_accounts if a.get("type") == "credit"
    )
    state._balances_cache_store.data["teller_accounts"] = teller_accounts
    state._balances_cache_store.data["teller_cash"] = round(total_cash, 2)
    state._balances_cache_store.data["teller_credit_debt"] = round(total_credit, 2)
    state._balances_cache_store.save()

    get_repo().insert_balance_snapshot(
        account_id=account_id,
        source="override",
        available=target.get("available"),
        ledger=target.get("ledger"),
        raw={"available": target.get("available"), "ledger": target.get("ledger")},
    )

    return AccountBalance(**target)


@router.delete("/balances/manual/{account_id}", status_code=204)
async def delete_manual_account(account_id: str):
    """Remove a manually-added account."""
    from db.accounts_repo import get_repo

    if account_id not in state._manual_accounts:
        raise HTTPException(status_code=404, detail="Manual account not found")
    del state._manual_accounts[account_id]
    state._manual_accounts_store.save()
    # Cascade drops any balance_snapshots / account_details for this id.
    get_repo().delete_manual_account(account_id)
