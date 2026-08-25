"""Balance aggregation: the one place net worth is assembled.

Lives outside ``routers/`` because more than one router needs it — the
Investments page filters the same account list this builds, the scheduler and
the advisor's action tools read it, and ``/simplefin/sync`` shares its cache
writer. A router calling another router's handler to get at this was the
alternative, which coupled those callers to ``/balances/summary``'s signature
and made them untestable on their own.

Accounts arrive from three places and are merged here:

* **SimpleFIN** — from the DB-backed cache, refreshed only on an explicit sync
  or ``force=True``. Balance and credit-debt totals are cached alongside.
* **manual** — live from ``state._manual_accounts``; the stored figure is a
  *starting* balance that linked transactions move.
* **SnapTrade** — from its own cache key, so a SimpleFIN refresh can't clobber
  brokerage rows.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import connection_health
import state
from helpers import txn_direction
from institution_normalizer import normalize as normalize_institution
from models import AccountBalance, BalancesSummary

logger = logging.getLogger(__name__)


def to_account_balance(raw: Dict[str, Any], source: str, **overrides: Any) -> AccountBalance:
    """Build an ``AccountBalance`` from a raw account dict.

    Every construction site goes through here so institution normalization and
    the ``source`` stamp can never be forgotten on one of them — the reason two
    spellings of the same bank used to render as two institutions.
    """
    return AccountBalance(**{
        **raw,
        "institution": normalize_institution(raw.get("institution")),
        "source": source,
        **overrides,
    })


def is_simplefin_account_hidden(account_id: str) -> bool:
    """True when a SimpleFIN account has been locally "disconnected".

    SimpleFIN has no per-account revoke, so hiding one writes a manual
    shadow record (see ``routers/accounts.py``). Every listing and sync path
    consults this so a hidden account can't reappear through one of them.
    """
    shadow = state._manual_accounts.get(account_id)
    return bool(shadow and shadow.get("disconnected_from") == "simplefin")


def write_simplefin_cache(accounts: List[Dict[str, Any]]) -> None:
    """Persist the SimpleFIN account list and re-derive its cash/debt totals.

    The totals are always recomputed from the list itself, so callers that
    mutate it (a balance override, hiding an account) can't leave the
    scalars disagreeing with the rows.
    """
    total_cash = sum(
        float(a.get("available") or 0.0)
        for a in accounts if a.get("type") == "depository"
    )
    total_credit = sum(
        float(a.get("ledger") or 0.0)
        for a in accounts if a.get("type") == "credit"
    )
    state._balances_cache_store.data["simplefin_accounts"] = accounts
    state._balances_cache_store.data["simplefin_cash"] = round(total_cash, 2)
    state._balances_cache_store.data["simplefin_credit_debt"] = round(total_credit, 2)
    state._balances_cache_store.save()


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
            if txn_direction(txn) == "inflow":
                credits += amt
            else:
                debits += amt
            continue
        if txn.get("transfer_to_account_id") == account_id:
            # Source-side outflow = destination-side inflow, and vice-versa.
            if txn_direction(txn) == "inflow":
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


def _valuation_date(account_id: str) -> Optional[str]:
    """ISO date the user last set a real asset's value, or None."""
    raw = (state.account_details.get(account_id) or {}).get("valuation_updated_on")
    return str(raw) if raw else None


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
    net debits. Investment and real-asset manuals (no clear sign convention,
    and a car payment is not a change in the car's worth) keep the starting
    value as-is.
    """
    from analytics import classify_account_bucket

    for acct in state._manual_accounts.values():
        starting_available = float(acct.get("available", 0.0))
        starting_ledger = float(acct.get("ledger", 0.0))
        acct_type = acct.get("type", "depository")
        bucket = classify_account_bucket(acct_type, acct.get("subtype", ""))

        delta = _manual_account_txn_delta(acct["id"])
        if bucket in _CASH_BUCKETS:
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
            # Investments / real assets: leave the stored value untouched. The
            # value is revalued only by an explicit user edit, never by the
            # transactions that happen to be linked to it.
            available = starting_available
            ledger = starting_ledger
            starting = starting_available or starting_ledger
            delta = 0.0

        if bucket == "real_asset":
            linked_count, linked_last = 0, None
        else:
            linked_count, linked_last = _manual_account_linkage_meta(acct["id"])
        accounts_out.append(to_account_balance(
            acct,
            "manual",
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
            valuation_updated_on=_valuation_date(acct["id"]) if bucket == "real_asset" else None,
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
            accounts_out.append(to_account_balance(a, "snaptrade"))
        except Exception as e:
            logger.warning(f"[SnapTrade] skipping malformed cached account: {e}")
    return accounts_out


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
            accounts_out.append(to_account_balance(a, "simplefin"))
        except Exception as e:
            logger.warning(f"[SimpleFIN] skipping malformed cached account: {e}")
    total_cash += state._balances_cache.get("simplefin_cash", 0.0) or 0.0
    total_credit_debt += state._balances_cache.get("simplefin_credit_debt", 0.0) or 0.0
    return accounts_out, total_cash, total_credit_debt


def _compute_investments(accounts: List[AccountBalance]) -> float:
    """Sum the value of every investment / retirement account in ``accounts``.

    Uses ``analytics.classify_account_bucket`` so the Accounts modal,
    advisor snapshot, and balances summary all agree on what counts as
    an investment.
    """
    from analytics import classify_account_bucket

    total = 0.0
    for a in accounts:
        if classify_account_bucket(a.type, a.subtype) != "investment":
            continue
        value = float(a.available or 0.0) or float(a.ledger or 0.0)
        total += value
    return round(total, 2)


def _compute_real_assets(accounts: List[AccountBalance]) -> float:
    """Sum the value of every home / vehicle / other real asset.

    Kept separate from both cash and investments: a house is not spendable,
    and it is not a tradeable holding either — folding it into either would
    corrupt the emergency-fund runway or the portfolio allocation.
    """
    from analytics import classify_account_bucket

    total = 0.0
    for a in accounts:
        if classify_account_bucket(a.type, a.subtype) != "real_asset":
            continue
        total += float(a.available or 0.0) or float(a.ledger or 0.0)
    return round(total, 2)


# Buckets whose balance is spendable money. ``other`` is here because
# unclassified rows are still the household's money. ``investment`` and
# ``real_asset`` are deliberately excluded — each is summed separately
# (``_compute_investments`` / ``_compute_real_assets``) and counting one here
# too would both double it in net worth and, worse for real assets, present a
# house as emergency cash.
_CASH_BUCKETS = ("cash", "other")


async def persist_simplefin_balances(
    url_batches: List[Tuple[str, List[Dict[str, Any]]]],
    url_errors: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[List[AccountBalance], float, float]:
    """Walk already-fetched SimpleFIN account data, write the cache, and
    return (accounts, simplefin_cash, simplefin_credit_debt).

    SimpleFIN bundles balance + transactions in the same ``/accounts``
    response, so there is no separate per-account balance fetch here. Shared
    by ``/simplefin/sync`` and a forced ``/balances/summary`` refresh so
    both code paths write the same cache shape.

    ``url_errors`` is the failure half of ``list_accounts_by_url``. Recording
    it here is what lets the Accounts page report connection health without
    calling the provider itself — see ``connection_health``.
    """
    from analytics import classify_account_bucket
    from simplefin import iter_normalized_accounts

    accounts_out: List[AccountBalance] = []
    total_cash = 0.0
    total_credit_debt = 0.0

    for acct in iter_normalized_accounts(url_batches, is_simplefin_account_hidden):
        raw_balance = acct["raw_balance"]
        bucket = classify_account_bucket(acct["type"], acct["subtype"])
        if bucket == "credit":
            # SimpleFIN reports credit-card/loan balances as negative
            # (money owed); this app's convention stores debt positive.
            available = ledger = round(abs(raw_balance), 2)
            total_credit_debt += ledger
        else:
            available = ledger = round(raw_balance, 2)
            # Investment value is summed separately by ``_compute_investments``;
            # counting a brokerage here too would double it in net worth.
            if bucket in _CASH_BUCKETS:
                total_cash += available

        accounts_out.append(to_account_balance(
            acct,
            "simplefin",
            name=acct["name"],
            type=acct["type"],
            subtype=acct["subtype"],
            available=available,
            ledger=ledger,
        ))

    # Balances first, health second: a failure between the two leaves health
    # describing an older sync than the balances, which reads as "stale", not
    # as balances that never happened.
    state._balances_cache_store.data.update({
        "simplefin_fetched_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        "simplefin_accounts": [a.model_dump() for a in accounts_out],
        "simplefin_cash": round(total_cash, 2),
        "simplefin_credit_debt": round(total_credit_debt, 2),
    })
    state._balances_cache_store.save()

    connection_health.record_simplefin_sync(url_batches, url_errors or [])

    return accounts_out, total_cash, total_credit_debt


def _summary(
    accounts: List[AccountBalance],
    total_cash: float,
    total_credit_debt: float,
    *,
    from_cache: bool,
) -> BalancesSummary:
    total_investments = _compute_investments(accounts)
    total_real_assets = _compute_real_assets(accounts)
    return BalancesSummary(
        net_worth=round(
            total_cash + total_investments + total_real_assets - total_credit_debt, 2
        ),
        total_cash=round(total_cash, 2),
        total_credit_debt=round(total_credit_debt, 2),
        total_investments=total_investments,
        total_real_assets=total_real_assets,
        accounts=accounts,
        connections=connection_health.build(accounts),
        from_cache=from_cache,
        cache_fetched_at=state._balances_cache.get("simplefin_fetched_at"),
    )


async def build_summary(force: bool = False) -> BalancesSummary:
    """Aggregate balances across all accounts and compute net worth.

    SimpleFIN data is served exclusively from the DB-backed cache — page loads
    and tab switches never hit SimpleFIN. Only ``force=True`` (wired to the
    Refresh button in the UI) bypasses the cache and issues a live SimpleFIN
    call. Manual/CSV accounts are always merged in live from the DB.
    """
    accounts_out: List[AccountBalance] = []
    total_cash = 0.0
    total_credit_debt = 0.0

    if force and state.SIMPLEFIN_ACCESS_URLS:
        url_batches, url_errors = await state.simplefin.list_accounts_by_url()
        accounts_out, total_cash, total_credit_debt = await persist_simplefin_balances(
            url_batches, url_errors
        )
    else:
        # Not forced, or forced with no live connection — either way, serve
        # whatever the last sync cached rather than dropping those accounts.
        accounts_out, total_cash, total_credit_debt = _append_simplefin_accounts(
            accounts_out, total_cash, total_credit_debt
        )

    accounts_out, total_cash, total_credit_debt = _append_manual_accounts(
        accounts_out, total_cash, total_credit_debt
    )
    accounts_out = _append_snaptrade_accounts(accounts_out)

    from_cache = not force and state._balances_cache.get("simplefin_fetched_at") is not None
    return _summary(accounts_out, total_cash, total_credit_debt, from_cache=from_cache)
