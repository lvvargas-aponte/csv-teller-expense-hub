"""Balances routes: summary and manual account management.

Aggregation lives in ``balances_service`` — this module is the HTTP surface
over it, plus the manual-account CRUD that only reaches the store.
"""
import logging
import uuid
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query

import balances_service
import state
from balances_service import to_account_balance, write_simplefin_cache
from models import (
    AccountBalance,
    BalancesSummary,
    ManualAccountIn,
    ManualAccountUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/balances/summary", response_model=BalancesSummary)
async def get_balances_summary(force: bool = Query(False)) -> BalancesSummary:
    """Aggregate balances across all accounts and compute net worth.

    SimpleFIN data is served exclusively from the DB-backed cache — page loads
    and tab switches never hit SimpleFIN. Only ``?force=true`` (wired to the
    Refresh button in the UI) issues a live SimpleFIN call.
    """
    return await balances_service.build_summary(force)


@router.post("/balances/manual", response_model=AccountBalance, status_code=201)
async def add_manual_account(req: ManualAccountIn) -> AccountBalance:
    """Persist a user-added account balance (for banks not connected via SimpleFIN)."""
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

    return to_account_balance(record, "manual", manual=True)


@router.put("/balances/manual/{account_id}", response_model=AccountBalance)
async def update_manual_account(account_id: str, req: ManualAccountUpdate) -> AccountBalance:
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

    return to_account_balance(record, "manual", manual=True)


@router.put("/balances/{account_id}", response_model=AccountBalance)
async def update_account_balance(account_id: str, req: ManualAccountUpdate) -> AccountBalance:
    """Edit available/ledger for any account — manual, csv-synth, or
    SimpleFIN-cached.

    For SimpleFIN accounts the override is written into the cached
    balances payload; the next ``?force=true`` refresh (or sync) will
    overwrite it with whatever SimpleFIN reports. A
    balance_snapshots row is appended either way so the edit shows up on
    net-worth history. Also how a SimpleFIN account's guessed type (see
    ``simplefin.infer_account_bucket``) gets corrected if it flips the
    cash/debt sign wrong — editing the balance here doesn't change ``type``,
    but it does let the number itself be fixed immediately.
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

    cached_accounts = state._balances_cache.get("simplefin_accounts") or []
    target = next((a for a in cached_accounts if a.get("id") == account_id), None)
    if target is not None:
        if req.available is not None:
            target["available"] = float(req.available)
        if req.ledger is not None:
            target["ledger"] = float(req.ledger)

        write_simplefin_cache(cached_accounts)

        get_repo().insert_balance_snapshot(
            account_id=account_id,
            source="override",
            available=target.get("available"),
            ledger=target.get("ledger"),
            raw={"available": target.get("available"), "ledger": target.get("ledger")},
        )

        return to_account_balance(target, "simplefin")

    raise HTTPException(status_code=404, detail="Account not found")


@router.post("/balances/snapshots/refresh")
async def refresh_balance_snapshots() -> Dict[str, Any]:
    """Write a fresh ``balance_snapshots`` row for every account currently in
    ``/balances/summary``.

    Use when the net-worth timeseries on the dashboard has drifted from the
    live KPI — typically because a manual balance was edited via a path that
    didn't append a snapshot (older endpoint, direct edit). Idempotent: safe
    to call repeatedly. Source on each new row reflects where the account is
    sourced from (``simplefin`` / ``manual`` / ``snaptrade``)."""
    from db.accounts_repo import get_repo

    repo = get_repo()
    summary = await balances_service.build_summary(force=False)
    snaptrade_ids = {
        a.get("id")
        for a in (state._balances_cache.get("snaptrade_accounts", []) or [])
    }
    written = 0
    for acct in summary.accounts:
        if acct.manual:
            src = "manual"
        elif acct.id in snaptrade_ids:
            src = "snaptrade"
        else:
            src = "simplefin"
        repo.insert_balance_snapshot(
            account_id=acct.id,
            source=src,
            available=acct.available,
            ledger=acct.ledger,
            raw={"available": acct.available, "ledger": acct.ledger, "refreshed": True},
        )
        written += 1
    return {"refreshed": written}


@router.delete("/balances/manual/{account_id}", status_code=204)
async def delete_manual_account(account_id: str) -> None:
    """Remove a manually-added account."""
    from db.accounts_repo import get_repo

    if account_id not in state._manual_accounts:
        raise HTTPException(status_code=404, detail="Manual account not found")
    del state._manual_accounts[account_id]
    state._manual_accounts_store.save()
    # Cascade drops any balance_snapshots / account_details for this id.
    get_repo().delete_manual_account(account_id)
