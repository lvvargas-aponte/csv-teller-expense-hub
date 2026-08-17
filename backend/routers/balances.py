"""Balances routes: summary and manual account management."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

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


def _manual_account_txn_delta(account_id: str) -> float:
    """Signed delta of linked transactions for a manual account.

    Two sources of linkage:
      1. ``account_id == <this>`` — a transaction posted directly to the
         manual account (e.g. CSV upload, manual entry).
      2. ``transfer_to_account_id == <this>`` — a transaction on a *different*
         account that the user tagged as a transfer INTO this manual account
         (e.g. an outbound ACH from checking to a HYSA). The sign is inverted
         for these: a debit on the source = an inflow to the destination, so
         it reduces the destination's net-outflow delta.

    ``delta`` is the net outflow: positive when more left than came in
    (debits > credits). For cash accounts the caller computes
    ``available = starting - delta`` (an inflow lowers the delta, raising
    available); for credit accounts ``ledger = starting + delta``.
    """
    debits = 0.0
    credits = 0.0
    for txn in state.stored_transactions.values():
        amt = float(txn.get("amount") or 0.0)
        if txn.get("account_id") == account_id:
            if txn.get("transaction_type") == "credit":
                credits += amt
            else:
                debits += amt
            continue
        if txn.get("transfer_to_account_id") == account_id:
            # Source-side debit = destination-side credit, and vice-versa.
            if txn.get("transaction_type") == "credit":
                debits += amt
            else:
                credits += amt
    return round(debits - credits, 2)


def _manual_account_linkage_meta(account_id: str) -> Tuple[int, Optional[str]]:
    """Return ``(count, most_recent_date)`` of transactions linked to a manual
    account — either by direct ``account_id`` or by ``transfer_to_account_id``.

    The dashboard "Last updated · N linked transactions" badge reads this so
    the user can see how much of the displayed balance is computed vs typed.
    """
    count = 0
    latest: Optional[str] = None
    for txn in state.stored_transactions.values():
        if (
            txn.get("account_id") != account_id
            and txn.get("transfer_to_account_id") != account_id
        ):
            continue
        count += 1
        d = txn.get("date") or ""
        if d and (latest is None or d > latest):
            latest = d
    return count, latest


def _append_manual_accounts(
    accounts_out: List[AccountBalance],
    total_cash: float,
    total_credit_debt: float,
) -> Tuple[List[AccountBalance], float, float]:
    """Merge manually-added accounts into the running totals.

    Investment accounts are not summed here — ``_compute_investments``
    walks the final accounts list separately so the same classification
    rules (subtype-aware) apply uniformly to SimpleFIN and manual rows.

    For manual accounts, the user-edited ``available``/``ledger`` value is
    the *starting* balance; the live balance returned here is starting
    plus the signed delta of linked transactions. Depository accounts
    decrease with net debits; credit accounts increase what's owed with
    net debits. Investment manuals (no clear sign convention) keep the
    starting value as-is.
    """
    from analytics import _classify_account_bucket

    for acct in state._manual_accounts.values():
        starting_available = float(acct.get("available", 0.0))
        starting_ledger = float(acct.get("ledger", 0.0))
        acct_type = acct.get("type", "depository")
        bucket = _classify_account_bucket(acct_type, acct.get("subtype", ""))

        delta = _manual_account_txn_delta(acct["id"])
        if bucket == "cash":
            available = round(starting_available - delta, 2)
            ledger = available
            starting = starting_available
            total_cash += available
        elif bucket == "credit":
            ledger = round(starting_ledger + delta, 2)
            available = ledger
            starting = starting_ledger
            total_credit_debt += ledger
        else:
            # Investments / other: leave starting balance untouched.
            available = starting_available
            ledger = starting_ledger
            starting = starting_available or starting_ledger
            delta = 0.0

        linked_count, linked_last = _manual_account_linkage_meta(acct["id"])
        accounts_out.append(AccountBalance(
            id=acct["id"],
            institution=acct.get("institution", ""),
            name=acct.get("name", ""),
            type=acct_type,
            subtype=acct.get("subtype", ""),
            available=available,
            ledger=ledger,
            manual=True,
            starting_balance=starting,
            txn_delta=delta,
            linked_txn_count=linked_count,
            linked_last_date=linked_last,
            disconnected_from=acct.get("disconnected_from"),
            disconnected_at=acct.get("disconnected_at"),
        ))
    return accounts_out, total_cash, total_credit_debt


def _append_snaptrade_accounts(
    accounts_out: List[AccountBalance],
) -> List[AccountBalance]:
    """Merge SnapTrade-synced investment accounts from the cache.

    ``/snaptrade/sync`` writes these under their own ``snaptrade_accounts``
    cache key, so a SimpleFIN refresh (which rewrites ``simplefin_accounts``)
    never clobbers them. They are investment-typed, so ``_compute_investments``
    picks up their value into net worth.
    """
    for a in state._balances_cache.get("snaptrade_accounts", []) or []:
        try:
            accounts_out.append(AccountBalance(**a))
        except Exception as e:
            logger.warning(f"[SnapTrade] skipping malformed cached account: {e}")
    return accounts_out


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


async def persist_simplefin_balances(
    url_batches: List[Tuple[str, List[Dict[str, Any]]]],
) -> Tuple[List[AccountBalance], float, float]:
    """Walk already-fetched SimpleFIN account data, write the cache, and
    return (accounts, simplefin_cash, simplefin_credit_debt).

    SimpleFIN bundles balance + transactions in the same ``/accounts``
    response, so there is no separate per-account balance fetch here. Shared
    by ``/simplefin/sync`` and a forced ``/balances/summary`` refresh so
    both code paths write the same cache shape.
    """
    from simplefin import infer_account_bucket

    accounts_out: List[AccountBalance] = []
    total_cash = 0.0
    total_credit_debt = 0.0
    seen_ids: set[str] = set()

    for _url, accounts in url_batches:
        for acct in accounts:
            acct_id = acct.get("id")
            if not acct_id or acct_id in seen_ids:
                continue
            # SimpleFIN has no per-account revoke — "disconnecting" one
            # account (routers/simplefin.py) just hides it locally via a
            # manual shadow. Skip it here so it doesn't reappear on sync.
            shadow = state._manual_accounts.get(acct_id)
            if shadow and shadow.get("disconnected_from") == "simplefin":
                continue
            seen_ids.add(acct_id)

            org_name = acct.get("_org_name") or "Bank"
            name = acct.get("name") or acct_id

            try:
                raw_balance = float(acct.get("balance") or 0.0)
            except (TypeError, ValueError):
                raw_balance = 0.0

            acct_type, acct_subtype = infer_account_bucket(name, org_name, raw_balance)

            if acct_type == "credit":
                # SimpleFIN reports credit-card/loan balances as negative
                # (money owed); this app's convention stores debt positive.
                available = ledger = round(abs(raw_balance), 2)
                total_credit_debt += ledger
            else:
                available = ledger = round(raw_balance, 2)
                total_cash += available

            accounts_out.append(AccountBalance(
                id=acct_id,
                institution=org_name,
                name=name,
                type=acct_type,
                subtype=acct_subtype,
                available=available,
                ledger=ledger,
            ))

    state._balances_cache_store.data.update({
        "simplefin_fetched_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        "simplefin_accounts": [a.model_dump() for a in accounts_out],
        "simplefin_cash": round(total_cash, 2),
        "simplefin_credit_debt": round(total_credit_debt, 2),
    })
    state._balances_cache_store.save()

    return accounts_out, total_cash, total_credit_debt


def _append_simplefin_accounts(
    accounts_out: List[AccountBalance],
    total_cash: float,
    total_credit_debt: float,
) -> Tuple[List[AccountBalance], float, float]:
    """Merge cached SimpleFIN accounts (and their cash/debt totals) into the
    running summary.
    """
    for a in state._balances_cache.get("simplefin_accounts", []) or []:
        try:
            accounts_out.append(AccountBalance(**a))
        except Exception as e:
            logger.warning(f"[SimpleFIN] skipping malformed cached account: {e}")
    total_cash += state._balances_cache.get("simplefin_cash", 0.0) or 0.0
    total_credit_debt += state._balances_cache.get("simplefin_credit_debt", 0.0) or 0.0
    return accounts_out, total_cash, total_credit_debt


def _build_summary(
    accounts: List[AccountBalance],
    total_cash: float,
    total_credit_debt: float,
    *,
    from_cache: bool,
) -> BalancesSummary:
    """Assemble the summary, real estate included.

    Property value is added from the properties tables; the mortgage securing
    it is already in ``total_credit_debt`` whenever the loan is linked to a
    synced account, so only ``unlinked_debt`` — hand-entered loans backed by
    no account — is subtracted here. See
    ``properties.compute_real_estate_position`` for why the split exists.

    Both the cached and the live path go through this so the two can't drift.
    """
    import properties as properties_domain

    total_investments = _compute_investments(accounts)
    real_estate = properties_domain.compute_real_estate_position(
        counted_account_ids={a.id for a in accounts if a.type == "credit"}
    )
    net_worth = (
        total_cash
        + total_investments
        - total_credit_debt
        + real_estate["total_value"]
        - real_estate["unlinked_debt"]
    )
    return BalancesSummary(
        net_worth=round(net_worth, 2),
        total_cash=round(total_cash, 2),
        total_credit_debt=round(total_credit_debt, 2),
        total_investments=total_investments,
        total_property_value=real_estate["total_value"],
        total_property_debt=real_estate["total_debt"],
        total_property_equity=real_estate["total_equity"],
        unvalued_properties=real_estate["unvalued_properties"],
        accounts=accounts,
        from_cache=from_cache,
        cache_fetched_at=state._balances_cache.get("simplefin_fetched_at"),
    )


@router.get("/balances/summary", response_model=BalancesSummary)
async def get_balances_summary(force: bool = Query(False)):
    """Aggregate balances across all accounts and compute net worth.

    SimpleFIN data is served exclusively from the DB-backed cache — page loads
    and tab switches never hit SimpleFIN. Only ``?force=true`` (wired to the
    Refresh button in the UI) bypasses the cache and issues a live SimpleFIN
    call. Manual/CSV accounts are always merged in live from the DB.
    """
    if not force:
        cached_accounts, total_cash, total_credit_debt = _append_simplefin_accounts(
            [], 0.0, 0.0
        )
        cached_accounts, total_cash, total_credit_debt = _append_manual_accounts(
            cached_accounts, total_cash, total_credit_debt
        )
        cached_accounts = _append_snaptrade_accounts(cached_accounts)
        fetched_at = state._balances_cache.get("simplefin_fetched_at")
        return _build_summary(
            cached_accounts, total_cash, total_credit_debt,
            from_cache=fetched_at is not None,
        )

    # ── force=true: fetch live from SimpleFIN ─────────────────────────────
    accounts_out: List[AccountBalance] = []
    total_cash = 0.0
    total_credit_debt = 0.0

    if state.SIMPLEFIN_ACCESS_URLS:
        url_batches, _ = await state.simplefin.list_accounts_by_url()
        sf_accounts, sf_cash, sf_credit = await persist_simplefin_balances(url_batches)
        accounts_out += sf_accounts
        total_cash += sf_cash
        total_credit_debt += sf_credit
    else:
        # No live SimpleFIN connection — still surface whatever the last sync
        # cached rather than silently dropping those accounts from the summary.
        accounts_out, total_cash, total_credit_debt = _append_simplefin_accounts(
            accounts_out, total_cash, total_credit_debt
        )

    accounts_out, total_cash, total_credit_debt = _append_manual_accounts(
        accounts_out, total_cash, total_credit_debt
    )
    accounts_out = _append_snaptrade_accounts(accounts_out)
    return _build_summary(
        accounts_out, total_cash, total_credit_debt, from_cache=False
    )


@router.post("/balances/manual", response_model=AccountBalance, status_code=201)
async def add_manual_account(req: ManualAccountIn):
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

        # Recompute cached totals from the (possibly mutated) account list so
        # the summary endpoint reflects the override on the very next call.
        total_cash = sum(
            float(a.get("available") or 0.0)
            for a in cached_accounts if a.get("type") == "depository"
        )
        total_credit = sum(
            float(a.get("ledger") or 0.0)
            for a in cached_accounts if a.get("type") == "credit"
        )
        state._balances_cache_store.data["simplefin_accounts"] = cached_accounts
        state._balances_cache_store.data["simplefin_cash"] = round(total_cash, 2)
        state._balances_cache_store.data["simplefin_credit_debt"] = round(total_credit, 2)
        state._balances_cache_store.save()

        get_repo().insert_balance_snapshot(
            account_id=account_id,
            source="override",
            available=target.get("available"),
            ledger=target.get("ledger"),
            raw={"available": target.get("available"), "ledger": target.get("ledger")},
        )

        return AccountBalance(**target)

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
    summary = await get_balances_summary(force=False)
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
async def delete_manual_account(account_id: str):
    """Remove a manually-added account."""
    from db.accounts_repo import get_repo

    if account_id not in state._manual_accounts:
        raise HTTPException(status_code=404, detail="Manual account not found")
    del state._manual_accounts[account_id]
    state._manual_accounts_store.save()
    # Cascade drops any balance_snapshots / account_details for this id.
    get_repo().delete_manual_account(account_id)
