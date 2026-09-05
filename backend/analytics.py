"""Analytics helpers — shared aggregations used by insights and advisor routers.

Keeps the advisor lightweight: reads from in-memory stores and the balances
cache (never triggers a live SimpleFIN fetch) so chat turns stay fast.
"""
from __future__ import annotations

import calendar
import logging
import re
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

import categories_service
import state
from helpers import txn_direction
# Re-exported under the private names this module has always used, so the
# merchant key stays one implementation now that category rules key on it too.
from merchant_key import aliases as _merchant_aliases, normalize as _normalize_merchant

logger = logging.getLogger(__name__)

# Forecast weights for a simple 3-month weighted average
# (most-recent month = highest weight).
FORECAST_WEIGHTS = (0.5, 0.3, 0.2)

# 30 days / typical paycheck cadence:
#   weekly   → 7d   → ×4.286
#   biweekly → 14d  → ×2.143
#   semi-mo  → 15d  → ×2.000
#   monthly  → 30d  → ×1.000
_DAYS_PER_MONTH = 30.0


def _parse_month_key(date_str: str) -> str:
    """Return a YYYY-MM string from either YYYY-MM-DD or MM/DD/YYYY input."""
    if len(date_str) == 10 and date_str[2] == "/":
        parts = date_str.split("/")
        return f"{parts[2]}-{parts[0]}"
    return date_str[:7]


def _parse_date_obj(date_str: str) -> Optional[date]:
    """Parse a transaction date string into a ``date`` object.

    Accepts YYYY-MM-DD or MM/DD/YYYY (the two formats CSV imports + SimpleFIN
    sync produce). Returns ``None`` on anything we don't recognize so
    callers can simply skip the row instead of catching exceptions.
    """
    if not date_str:
        return None
    try:
        if "/" in date_str:
            return datetime.strptime(date_str, "%m/%d/%Y").date()
        return datetime.strptime(date_str[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def group_debit_spending() -> Dict[str, Dict[str, float]]:
    """Aggregate expense transactions into {month_key: {category: total}}.

    What counts as spending is decided by ``_is_expense`` (canonical
    money-flow ``direction``), so every caller agrees.
    """
    spending: Dict[str, Dict[str, float]] = {}
    for txn in state.stored_transactions.values():
        if not _is_expense(txn):
            continue
        amount = float(txn.get("amount", 0))

        date_str = txn.get("date", "")
        month_key = _parse_month_key(date_str) if date_str else ""
        if not month_key or len(month_key) < 7:
            continue

        category = txn.get("category") or "Uncategorized"
        spending.setdefault(month_key, {})
        spending[month_key][category] = spending[month_key].get(category, 0.0) + amount
    return spending


def _last_day_of_month(any_day: date) -> int:
    """Number of days in the calendar month containing ``any_day``."""
    first_next = date(
        any_day.year + (1 if any_day.month == 12 else 0),
        1 if any_day.month == 12 else any_day.month + 1,
        1,
    )
    return (first_next - timedelta(days=1)).day


def compute_month_to_date_comparison(today: Optional[date] = None) -> Dict[str, Any]:
    """Spending so far this month against the same stretch of the prior month.

    The dashboard used to hold a partial current month against a complete
    prior one, so every early-month delta read as a large drop. Both sides
    are bounded by the same day number here. ``today`` is a parameter so
    callers and tests never have to patch a clock.

    What counts as spending is ``_is_expense`` — the same gate
    ``group_debit_spending`` uses.
    """
    today = today or date.today()
    as_of_day = today.day
    current_month = f"{today.year:04d}-{today.month:02d}"

    prior_last_day = date(today.year, today.month, 1) - timedelta(days=1)
    prior_month = f"{prior_last_day.year:04d}-{prior_last_day.month:02d}"
    # A 31st has no counterpart in a 30-day month: clamp so the comparison
    # covers the whole prior month rather than silently dropping its last day.
    prior_cutoff_day = min(as_of_day, prior_last_day.day)

    current_month_to_date = 0.0
    prior_month_same_period = 0.0
    prior_month_full = 0.0

    for txn in state.stored_transactions.values():
        if not _is_expense(txn):
            continue
        txn_date = _parse_date_obj(txn.get("date", ""))
        if txn_date is None:
            continue
        amount = float(txn.get("amount", 0))
        month_key = f"{txn_date.year:04d}-{txn_date.month:02d}"
        if month_key == current_month:
            if txn_date.day <= as_of_day:
                current_month_to_date += amount
        elif month_key == prior_month:
            prior_month_full += amount
            if txn_date.day <= prior_cutoff_day:
                prior_month_same_period += amount

    delta = current_month_to_date - prior_month_same_period
    pct_change = (
        round(delta / prior_month_same_period * 100.0, 2)
        if prior_month_same_period
        else None
    )

    return {
        "as_of_day": as_of_day,
        "current_month": current_month,
        "current_month_to_date": round(current_month_to_date, 2),
        "prior_month": prior_month,
        "prior_month_same_period": round(prior_month_same_period, 2),
        "prior_month_full": round(prior_month_full, 2),
        "delta": round(delta, 2),
        "pct_change": pct_change,
        "current_month_is_partial": as_of_day < _last_day_of_month(today),
    }


def _shared_split_totals(recent_months: int = 2) -> Dict[str, Any]:
    """Sum per-person shared contributions across the N most recent months."""
    spending = group_debit_spending()
    months_ordered = sorted(spending.keys())[-recent_months:]

    per_person: Dict[str, float] = defaultdict(float)
    shared_total = 0.0
    shared_count = 0

    for txn in state.stored_transactions.values():
        if not txn.get("is_shared"):
            continue
        date_str = txn.get("date", "")
        month_key = _parse_month_key(date_str) if date_str else ""
        if month_key not in months_ordered:
            continue

        amount = float(txn.get("amount", 0))
        who = (txn.get("who") or "unknown").strip() or "unknown"
        per_person[who] += amount
        shared_total += amount
        shared_count += 1

    return {
        "months": months_ordered,
        "shared_total": round(shared_total, 2),
        "shared_count": shared_count,
        "per_person": {k: round(v, 2) for k, v in per_person.items()},
    }


# Subtypes that should be classified as investments rather than spendable cash.
# SimpleFIN's account-type inference doesn't reliably surface
# ``type='investment'``, and subtype labels vary across institutions — match
# case-insensitively against the user's free-text input from the Accounts
# modal too.
_INVESTMENT_SUBTYPES = frozenset({
    "401k", "401(k)", "403b", "403(b)", "ira", "roth_ira", "roth ira",
    "brokerage", "hsa", "investment", "retirement", "rollover_ira",
    "sep_ira", "simple_ira", "529",
})

# Credit accounts that are installment debt rather than a revolving line: a
# fixed principal on a fixed schedule. They have no credit limit to be a
# percentage of, so they are excluded from utilization, and the payoff planner's
# avalanche/snowball ordering does not apply to them either.
#
# Lived in credit_health_service and credit_factors as two separate copies;
# it is served to the frontend from /accounts/metadata so the JS side does not
# become a third.
_INSTALLMENT_SUBTYPES = frozenset({"loan", "mortgage", "student", "auto"})


def is_installment(acct_type: str, subtype: str) -> bool:
    """True for a credit account that is a loan rather than a revolving line."""
    if classify_account_bucket(acct_type, subtype) != "credit":
        return False
    return (subtype or "").lower().strip() in _INSTALLMENT_SUBTYPES


def classify_account_bucket(acct_type: str, subtype: str) -> str:
    """Return ``'cash'`` / ``'credit'`` / ``'investment'`` / ``'real_asset'`` /
    ``'other'``.

    Investment matching is intentionally permissive — both ``type='investment'``
    and any recognized retirement/brokerage ``subtype`` qualify so the user
    can flag a 401(k) as a manual depository account with the right subtype
    and have it accounted for correctly.

    ``real_asset`` is checked before the permissive investment arm: a home or
    vehicle is neither spendable cash nor a tradeable holding, and letting it
    fall through to either would inflate the emergency-fund runway or the
    portfolio allocation by the price of a house.
    """
    t = (acct_type or "").lower()
    s = (subtype or "").lower().strip()
    if t == "asset":
        return "real_asset"
    if t == "investment" or s in _INVESTMENT_SUBTYPES:
        return "investment"
    if t == "depository":
        return "cash"
    if t == "credit":
        return "credit"
    return "other"


# Was private until several modules outside analytics needed it; the old name
# is kept so nothing that imported it breaks.
_classify_account_bucket = classify_account_bucket


def _cost_overrides() -> Dict[Any, float]:
    """User-entered average costs, keyed (account_id, symbol).

    Degrades to no overrides rather than failing the whole portfolio if the
    table cannot be read.
    """
    try:
        from db.accounts_repo import get_repo

        return get_repo().get_cost_overrides()
    except Exception:  # pragma: no cover - store unavailable
        logger.warning("Could not read holding cost overrides", exc_info=True)
        return {}


def summarize_holdings(holdings: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate a flat list of holdings into a portfolio summary.

    Single source of truth for both ``GET /investments/portfolio`` and the
    advisor's ``investments`` snapshot block. Each input holding is the dict
    shape ``accounts_repo.get_holdings()`` returns. Output: per-holding rows
    enriched with ``cost_basis`` / ``unrealized_gain`` / ``gain_pct`` /
    ``cost_basis_source`` plus portfolio totals, allocation by asset type,
    and concentration ranking.

    A user-entered cost basis is joined in here rather than stored on the
    holding, because every sync rewrites that table. It wins over the
    provider's value, and ``cost_basis_source`` says which one was used.
    """
    overrides = _cost_overrides()
    enriched: List[Dict[str, Any]] = []
    total_value = 0.0
    total_cost = 0.0
    for h in holdings:
        mv = h.get("market_value")
        qty = float(h.get("quantity") or 0.0)
        override = overrides.get((h.get("account_id"), h.get("symbol")))
        avg = override if override is not None else h.get("average_purchase_price")
        source = (
            "user" if override is not None
            else "provider" if avg is not None
            else None
        )
        cost = round(qty * float(avg), 2) if avg is not None else None
        gain = round(mv - cost, 2) if (mv is not None and cost is not None) else None
        gain_pct = (
            round((gain / cost) * 100, 2)
            if (gain is not None and cost not in (None, 0))
            else None
        )
        if mv is not None:
            total_value += mv
        if cost is not None:
            total_cost += cost
        enriched.append({
            **h,
            "average_purchase_price": avg,
            "cost_basis": cost,
            "unrealized_gain": gain,
            "gain_pct": gain_pct,
            "cost_basis_source": source,
        })

    total_value = round(total_value, 2)
    total_cost = round(total_cost, 2)
    total_gain = round(total_value - total_cost, 2)
    total_gain_pct = round((total_gain / total_cost) * 100, 2) if total_cost else None

    by_type: Dict[str, float] = {}
    for h in enriched:
        mv = float(h.get("market_value") or 0.0)
        by_type[h["asset_type"]] = round(by_type.get(h["asset_type"], 0.0) + mv, 2)
    allocation = [
        {
            "asset_type": k,
            "value": v,
            "pct": round(v / total_value * 100, 1) if total_value else 0.0,
        }
        for k, v in sorted(by_type.items(), key=lambda kv: kv[1], reverse=True)
    ]

    ranked = sorted(
        enriched, key=lambda h: float(h.get("market_value") or 0.0), reverse=True
    )
    concentration = [
        {
            "symbol": h["symbol"],
            "value": float(h.get("market_value") or 0.0),
            "pct": round(float(h.get("market_value") or 0.0) / total_value * 100, 1)
            if total_value
            else 0.0,
        }
        for h in ranked[:5]
    ]

    return {
        "total_value": total_value,
        "total_cost": total_cost,
        "total_gain": total_gain,
        "total_gain_pct": total_gain_pct,
        "holding_count": len(enriched),
        "allocation": allocation,
        "concentration": concentration,
        "holdings": enriched,
    }


def _balances_snapshot() -> Dict[str, Any]:
    """Read cached SimpleFIN balances + live manual accounts without calling SimpleFIN.

    Walks the raw account list and reclassifies each one through
    ``classify_account_bucket`` so investment / retirement accounts surface
    as their own bucket — the pre-summed ``simplefin_cash`` /
    ``simplefin_credit_debt`` scalars in the cache only cover depository +
    credit and would otherwise silently drop investment value from net worth.
    SnapTrade-synced investment accounts live under their own
    ``snaptrade_accounts`` cache key.
    """
    cache = state._balances_cache or {}
    linked_accounts = list(cache.get("simplefin_accounts", []) or [])
    snaptrade_accounts = cache.get("snaptrade_accounts", []) or []

    manual_accounts: List[Dict[str, Any]] = []
    for acct in state._manual_accounts.values():
        manual_accounts.append({
            "id": acct.get("id", ""),
            "institution": acct.get("institution", ""),
            "name": acct.get("name", ""),
            "type": acct.get("type", "depository"),
            "subtype": acct.get("subtype", ""),
            "available": float(acct.get("available", 0.0)),
            "ledger": float(acct.get("ledger", 0.0)),
            "manual": True,
        })

    total_cash = 0.0
    total_credit = 0.0
    total_investments = 0.0
    total_real_assets = 0.0
    for acct in list(linked_accounts) + list(snaptrade_accounts) + manual_accounts:
        bucket = classify_account_bucket(acct.get("type", ""), acct.get("subtype", ""))
        if bucket == "real_asset":
            # A home or vehicle: part of net worth, never part of cash.
            total_real_assets += float(acct.get("available", 0.0) or 0.0) or float(
                acct.get("ledger", 0.0) or 0.0
            )
        elif bucket == "cash":
            total_cash += float(acct.get("available", 0.0) or 0.0)
        elif bucket == "credit":
            total_credit += float(acct.get("ledger", 0.0) or 0.0)
        elif bucket == "investment":
            # Investments report value via ``available`` (the convention for
            # non-depository accounts is to put the position value there);
            # fall back to ``ledger`` if available is empty.
            value = float(acct.get("available", 0.0) or 0.0)
            if value == 0.0:
                value = float(acct.get("ledger", 0.0) or 0.0)
            total_investments += value

    return {
        "net_worth": round(
            total_cash + total_investments + total_real_assets - total_credit, 2
        ),
        "total_cash": round(total_cash, 2),
        "total_credit_debt": round(total_credit, 2),
        "total_investments": round(total_investments, 2),
        "total_real_assets": round(total_real_assets, 2),
        "linked_accounts": linked_accounts,
        "snaptrade_accounts": snaptrade_accounts,
        "manual_accounts": manual_accounts,
        "cache_fetched_at": cache.get("simplefin_fetched_at"),
    }


def _round_money(value: Decimal) -> float:
    """Half-up to the cent — the rounding a statement uses."""
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


async def compute_carry_cost() -> Dict[str, Any]:
    """What the household's outstanding debt costs per month in interest.

    Nowhere else does the app put a price on carrying a balance — APRs were
    captured per account and read only inside the payoff planner. Simple
    monthly interest, ``balance × apr / 12``: compounding belongs to the payoff
    simulator, which models a schedule; this is the standing monthly cost.

    Balances come from ``balances_service.build_summary`` so a manual card's
    live figure is used, not its starting balance. Installment loans count —
    utilization ignores them, but their interest is real money.
    """
    import balances_service

    summary = await balances_service.build_summary()

    by_account: List[Dict[str, Any]] = []
    monthly_total = 0.0
    missing_apr = 0

    for acct in summary.accounts:
        if classify_account_bucket(acct.type, acct.subtype) != "credit":
            continue
        balance = float(acct.ledger or 0.0)
        if balance <= 0:
            continue

        raw_apr = (state.account_details.get(acct.id) or {}).get("apr")
        try:
            apr = float(raw_apr) if raw_apr is not None else None
        except (TypeError, ValueError):
            apr = None
        if not apr or apr <= 0:
            missing_apr += 1
            continue

        # Decimal, not float: 4200 at 24.99% is exactly 87.465/month, and
        # binary rounding turns that into 87.46 — a cent short on every card.
        monthly = _round_money(
            Decimal(str(balance)) * Decimal(str(apr)) / Decimal(100) / Decimal(12)
        )
        monthly_total += monthly
        by_account.append({
            "account_id": acct.id,
            "name": acct.name,
            "balance": round(balance, 2),
            "apr": apr,
            "monthly_interest": monthly,
        })

    by_account.sort(key=lambda a: a["monthly_interest"], reverse=True)
    monthly_total = round(monthly_total, 2)
    return {
        "monthly_interest": monthly_total,
        "annual_interest": round(monthly_total * 12, 2),
        "accounts_missing_apr": missing_apr,
        "by_account": by_account,
    }


# A statement bills interest as a purchase-shaped line and the wording is the
# issuer's own: "INTEREST CHARGE-PURCHASES", "INTEREST CHARGE ON PURCHASES",
# "INTEREST CHARGED ON PURCHASES". Category is checked first — a normalized
# feed carries "Interest" — and this catches the SimpleFIN rows, which arrive
# uncategorized.
_INTEREST_DESCRIPTION = re.compile(r"\binterest\s+charge", re.I)

_CARD_ACTIVITY_MONTHS = 3

_ACTIVITY_FIELD = {"interest": "interest", "payment": "payments", "spend": "spend"}


def _card_txn_kind(txn: Dict[str, Any]) -> str:
    """``interest`` / ``payment`` / ``spend`` for one credit-card transaction.

    The two feeds disagree on how a payment is signed: SimpleFIN posts it to
    the card as an inflow, Teller as a debit categorized "CC Payment". Both
    shapes have to read as a payment, so category is consulted before
    direction. Interest is settled first — it is an outflow like any purchase,
    and counting it as spending would both inflate the spend figure and hide
    the one number worth surfacing.
    """
    category = (txn.get("category") or "").strip().lower()
    direction = txn_direction(txn)
    description = txn.get("description") or ""
    if category == "interest" or (
        direction == "outflow" and _INTEREST_DESCRIPTION.search(description)
    ):
        return "interest"
    if category == "cc payment" or direction == "inflow":
        return "payment"
    return "spend"


async def compute_card_activity(
    months: int = _CARD_ACTIVITY_MONTHS, today: Optional[date] = None
) -> Dict[str, Any]:
    """Per revolving card, what each complete month actually did to the balance.

    ``compute_carry_cost`` models what a balance *would* cost: today's balance
    times the APR. This reads what the issuer actually billed, because an
    ``INTEREST CHARGE`` line is a posted transaction — it already accounts for
    the grace period and for any mid-cycle payment the model cannot see. The
    two figures disagree by design and both are worth showing: one is the
    receipt, the other the projection if nothing changes.

    Installment loans are excluded. A mortgage's monthly interest is real, but
    it is a fixed schedule rather than something this month's behaviour moved.
    """
    import balances_service

    summary = await balances_service.build_summary()
    cards = {
        a.id: a.name
        for a in summary.accounts
        if classify_account_bucket(a.type, a.subtype) == "credit"
        and not is_installment(a.type, a.subtype)
    }
    empty: Dict[str, Any] = {
        "months": [], "latest_month": None,
        "interest_billed_latest": None, "by_account": {},
    }
    if not cards:
        return empty

    this_month = (today or date.today()).strftime("%Y-%m")
    buckets: Dict[tuple, Dict[str, Any]] = {}

    for txn in state.stored_transactions.values():
        account_id = txn.get("account_id")
        if account_id not in cards:
            continue
        raw_date = txn.get("date") or ""
        month = _parse_month_key(raw_date) if raw_date else ""
        # The running month is a partial cycle. Set beside a full one it reads
        # as a collapse in spending, every time the page is opened on the 3rd.
        if not month or month >= this_month:
            continue
        amount = abs(float(txn.get("amount") or 0.0))
        if amount <= 0:
            continue

        entry = buckets.setdefault((account_id, month), {
            "spend": Decimal("0"),
            "payments": Decimal("0"),
            "interest": Decimal("0"),
            "largest_purchase": None,
        })
        kind = _card_txn_kind(txn)
        entry[_ACTIVITY_FIELD[kind]] += Decimal(str(amount))
        if kind == "spend" and (
            entry["largest_purchase"] is None
            or amount > entry["largest_purchase"]["amount"]
        ):
            entry["largest_purchase"] = {
                "description": txn.get("description") or "",
                "amount": round(amount, 2),
                "date": raw_date,
            }

    if not buckets:
        return empty

    kept = sorted({month for _, month in buckets})[-months:]
    by_account: Dict[str, Any] = {}

    for (account_id, month), entry in buckets.items():
        if month not in kept:
            continue
        spend = _round_money(entry["spend"])
        payments = _round_money(entry["payments"])
        interest = _round_money(entry["interest"])
        by_account.setdefault(account_id, {"name": cards[account_id], "months": []})
        by_account[account_id]["months"].append({
            "month": month,
            "spend": spend,
            "payments": payments,
            "interest": interest,
            # What the month did to what is owed. Positive means the balance
            # grew: the card was used, and charged for, faster than it was paid.
            "net_change": round(spend + interest - payments, 2),
            "largest_purchase": entry["largest_purchase"],
        })

    for record in by_account.values():
        record["months"].sort(key=lambda m: m["month"])
        record["latest"] = record["months"][-1]
        record["avg_net_change"] = round(
            sum(m["net_change"] for m in record["months"]) / len(record["months"]), 2
        )

    latest_month = kept[-1]
    interest_latest = sum(
        m["interest"]
        for record in by_account.values()
        for m in record["months"] if m["month"] == latest_month
    )

    return {
        "months": kept,
        "latest_month": latest_month,
        "interest_billed_latest": round(interest_latest, 2),
        "by_account": by_account,
    }


_INTEREST_HISTORY_MONTHS = 12


def compute_interest_history(
    months: int = _INTEREST_HISTORY_MONTHS, today: Optional[date] = None
) -> Dict[str, Any]:
    """What carrying a balance has actually cost, month by month.

    Scoped by the transaction, not by the account. ``compute_card_activity``
    is joined to the cards that are linked *now*, which is right for a
    per-card row and wrong for a history: the household's Teller-era cards
    were replaced by SimpleFIN ones in July, and reading interest through the
    live account list threw away January through June and made the cost look
    like it appeared from nowhere. An ``INTEREST CHARGE`` line that left the
    account is money paid to a lender whether or not the card is still linked
    — including the CSV-imported rows that carry no ``account_id`` at all.

    The direction guard is what keeps deposit interest out: a savings account
    posts its interest as an inflow, a card bills it as an outflow.
    """
    today = today or date.today()
    this_month = today.strftime("%Y-%m")
    by_month: Dict[str, Decimal] = {}

    for txn in state.stored_transactions.values():
        if txn_direction(txn) != "outflow":
            continue
        category = (txn.get("category") or "").strip().lower()
        if category != "interest" and not _INTEREST_DESCRIPTION.search(
            txn.get("description") or ""
        ):
            continue
        raw_date = txn.get("date") or ""
        month = _parse_month_key(raw_date) if raw_date else ""
        # The running month is a partial cycle and most cards bill once, so it
        # is usually a zero that reads as a collapse.
        if not month or month >= this_month:
            continue
        amount = abs(float(txn.get("amount") or 0.0))
        if amount <= 0:
            continue
        by_month[month] = by_month.get(month, Decimal("0")) + Decimal(str(amount))

    if not by_month:
        return {
            "months": [], "total_paid": 0.0, "latest": None,
            "average": None, "trend": None, "highest": None,
        }

    kept = sorted(by_month)[-months:]
    rows = [{"month": m, "interest": _round_money(by_month[m])} for m in kept]
    amounts = [r["interest"] for r in rows]
    latest = amounts[-1]

    # Against the MEDIAN of the months before it. Not the previous month alone
    # — a card cleared inside its grace period bills nothing, and the next
    # ordinary month would read as a surge off that zero. Not their mean
    # either: one such month drags an average far enough to call a return to
    # normal a rise, which is the same outlier sensitivity that broke income
    # detection.
    prior = amounts[:-1]
    baseline = statistics.median(prior) if prior else None
    if baseline is None or baseline <= 0:
        trend = None
    elif latest > baseline * 1.15:
        trend = "rising"
    elif latest < baseline * 0.85:
        trend = "falling"
    else:
        trend = "steady"

    return {
        "months": rows,
        "total_paid": round(sum(amounts), 2),
        "latest": latest,
        "average": round(sum(amounts) / len(amounts), 2),
        "trend": trend,
        "highest": max(amounts),
    }


def _debts_from_accounts(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract credit-type accounts as debts.  When the user has configured
    per-account details (APR, min payment, due day) via the Accounts tab, those
    are attached here so the advisor can reason over them without asking.
    """
    debts: List[Dict[str, Any]] = []
    for acct in snapshot.get("linked_accounts", []) + snapshot.get("manual_accounts", []):
        if acct.get("type") != "credit":
            continue
        entry: Dict[str, Any] = {
            "account_id": acct.get("id", ""),
            "institution": acct.get("institution", ""),
            "name": acct.get("name", ""),
            "balance": float(acct.get("ledger", 0.0)),
            "subtype": acct.get("subtype", ""),
        }
        details = state.account_details.get(acct.get("id") or "") or {}
        if details.get("apr") is not None:
            entry["apr"] = details["apr"]
        if details.get("minimum_payment") is not None:
            entry["minimum_payment"] = details["minimum_payment"]
        if details.get("credit_limit") is not None:
            entry["credit_limit"] = details["credit_limit"]
        if details.get("due_day") is not None:
            entry["due_day"] = details["due_day"]
        debts.append(entry)
    return debts


def _current_month_key() -> str:
    """Return today's YYYY-MM."""
    return date.today().strftime("%Y-%m")


# Pace bands, as a share of the cap the month is projected to land on.
_PACE_OVER_MARGIN = 1.05    # above this, the month is heading over
_PACE_UNDER_MARGIN = 0.80   # below this, the cap has room the user could use


def _classify_budget_pace(
    limit: float, spent: float, projected: Optional[float]
) -> str:
    """Where a budget is heading, not just where it has been.

    ``over_budget`` is a fact about today; the other three are readings of the
    projection, which is the only one of the four that can still be acted on.
    """
    if limit <= 0:
        return "on_track"
    if spent > limit:
        return "over_budget"
    if projected is None:
        return "on_track"
    if projected > limit * _PACE_OVER_MARGIN:
        return "over_pace"
    if projected < limit * _PACE_UNDER_MARGIN:
        return "under"
    return "on_track"


def compute_budget_statuses(today: Optional[date] = None) -> List[Dict[str, Any]]:
    """For each configured budget, attach current-month spending and its pace.

    Read by ``GET /budgets`` (UI list), the alert feed and
    ``build_financial_snapshot`` (advisor context). Categories are matched
    case-insensitively against the aggregated spending so users don't have to
    mirror the exact casing the bank sends.

    Month-to-date spend against a full-month cap makes every budget look
    healthy on the 5th, so each status also carries how much of the month has
    elapsed and where the current run-rate lands it. ``today`` is a parameter
    so tests don't have to patch a clock.
    """
    today = today or date.today()
    month_key = f"{today.year:04d}-{today.month:02d}"
    days_in_month = _last_day_of_month(today)
    month_progress = today.day / days_in_month

    spending = group_debit_spending().get(month_key, {})
    spending_lc = {k.lower(): v for k, v in spending.items()}

    out: List[Dict[str, Any]] = []
    for raw in state.budgets.values():
        category = raw.get("category", "")
        limit = float(raw.get("monthly_limit", 0.0))
        spent = float(spending_lc.get(category.lower(), 0.0))
        pct = round(spent / limit * 100.0, 1) if limit > 0 else 0.0

        projected = round(spent / month_progress, 2) if month_progress > 0 else None
        pace = _classify_budget_pace(limit, spent, projected)
        overage = (
            round(projected - limit, 2)
            if projected is not None and limit > 0 and projected > limit
            else None
        )

        out.append({
            "category": category,
            "monthly_limit": round(limit, 2),
            "notes": raw.get("notes", ""),
            "current_month_spent": round(spent, 2),
            "percent_used": pct,
            "over_budget": limit > 0 and spent > limit,
            "month_progress_pct": round(month_progress * 100.0, 1),
            "projected_month_end": projected,
            "pace_status": pace,
            "projected_overage": overage,
        })
    out.sort(key=lambda b: b["category"].lower())
    return out


def _account_balance_by_id(account_id: str) -> Optional[float]:
    """Look up an account's `available` balance across cache + manual accounts."""
    if not account_id:
        return None
    for acct in state._balances_cache.get("simplefin_accounts", []) or []:
        if acct.get("id") == account_id:
            return float(acct.get("available", 0.0))
    acct = state._manual_accounts.get(account_id)
    if acct is not None:
        return float(acct.get("available", 0.0))
    return None


def _months_between(start: date, end: date) -> int:
    """Whole months from ``start`` to ``end`` (>= 0).  Used for goal pacing."""
    if end <= start:
        return 0
    return (end.year - start.year) * 12 + (end.month - start.month)


# Velocity classification thresholds (relative to ``monthly_required``):
#   ≥110 % of required → "ahead"
#   ≥ 90 % of required → "on_track"
#   actual > 0          → "behind"
#   actual ≤ 0          → "stalled"
_PACE_AHEAD_RATIO = 1.10
_PACE_ON_TRACK_RATIO = 0.90


def _compute_account_velocity(
    account_id: str,
    snapshots_newest_first: List[Dict[str, Any]],
    days: int = 30,
) -> Optional[float]:
    """Estimate the monthly net contribution to ``account_id`` over the
    last ``days`` days.

    Uses the earliest and most recent snapshots within the window — this
    is robust to irregular snapshot cadence (SimpleFIN sync may not run
    every day) but smooths out daily fluctuations.

    Returns ``None`` when fewer than two snapshots are available within
    the window or the captured-at span is too small to extrapolate.
    """
    relevant = [s for s in snapshots_newest_first if s.get("account_id") == account_id]
    if len(relevant) < 2:
        return None

    latest = relevant[0]
    earliest = relevant[-1]
    latest_value = latest.get("available")
    earliest_value = earliest.get("available")
    if latest_value is None or earliest_value is None:
        return None

    span_days = (latest["captured_at"] - earliest["captured_at"]).days
    if span_days <= 0:
        return None

    delta = float(latest_value) - float(earliest_value)
    return round(delta * (_DAYS_PER_MONTH / span_days), 2)


def _classify_pace(
    actual_monthly: Optional[float],
    monthly_required: Optional[float],
) -> Optional[str]:
    """Translate ``actual`` vs ``required`` into a pace label.

    Returns ``None`` when either input is missing — the caller should
    omit the field rather than invent a state.
    """
    if monthly_required is None or actual_monthly is None:
        return None
    if monthly_required <= 0:
        # No active requirement (goal already funded or no target date).
        return None
    if actual_monthly <= 0:
        return "stalled"
    if actual_monthly >= monthly_required * _PACE_AHEAD_RATIO:
        return "ahead"
    if actual_monthly >= monthly_required * _PACE_ON_TRACK_RATIO:
        return "on_track"
    return "behind"


def compute_goal_statuses() -> List[Dict[str, Any]]:
    """For each goal, attach current_balance (live or stored), progress %, and pacing.

    When ``linked_account_id`` is set, the live account `available` overrides
    the stored ``current_balance`` so the user doesn't have to keep it in sync.
    """
    from db.accounts_repo import get_repo

    today = date.today()
    # Pull a 30-day snapshot window once and reuse for every goal — typical
    # households have <10 goals, so even N×iteration is fine, but the
    # single round-trip keeps latency tight on chat turns.
    snapshots = get_repo().get_snapshots_since(31)

    out: List[Dict[str, Any]] = []
    for raw in state.goals.values():
        target = float(raw.get("target_amount", 0.0))
        linked = raw.get("linked_account_id") or None
        live = _account_balance_by_id(linked) if linked else None
        current = float(live) if live is not None else float(raw.get("current_balance", 0.0))
        progress = round(current / target * 100.0, 1) if target > 0 else 0.0

        months_remaining: Optional[int] = None
        monthly_required: Optional[float] = None
        target_date = raw.get("target_date")
        if target_date:
            try:
                tgt = datetime.strptime(target_date, "%Y-%m-%d").date()
                months_remaining = _months_between(today, tgt)
                if months_remaining > 0 and current < target:
                    monthly_required = round((target - current) / months_remaining, 2)
            except ValueError:
                pass

        actual_monthly = (
            _compute_account_velocity(linked, snapshots) if linked else None
        )
        pace_status = _classify_pace(actual_monthly, monthly_required)

        out.append({
            "id": raw.get("id", ""),
            "name": raw.get("name", ""),
            "kind": raw.get("kind", "savings"),
            "target_amount": round(target, 2),
            "target_date": target_date,
            "linked_account_id": linked,
            "current_balance": round(current, 2),
            "progress_pct": progress,
            "months_remaining": months_remaining,
            "monthly_required": monthly_required,
            "actual_monthly_contribution": actual_monthly,
            "pace_status": pace_status,
            "notes": raw.get("notes", ""),
        })
    out.sort(key=lambda g: (g["kind"] != "emergency_fund", g["name"].lower()))
    return out


# ---------------------------------------------------------------------------
# Recurring / subscription detection
# ---------------------------------------------------------------------------

# Amount-spread tolerance for grouping: utilities/phone/insurance routinely
# vary 30-50% month to month; 0.60 keeps them in while still rejecting genuinely
# noisy categories like gas stations (where the spread is typically > 1.0).
_RECURRING_AMOUNT_SPREAD = 0.60

# Which categories behave which way is data on the category row now, not a
# constant here — see ``categories_service.ROLES``. These used to be frozensets
# of lowercase names, which meant renaming a category silently changed
# recurring detection with nothing raising. The role travels with the row, so
# the behavior survives the rename.
#
#   always_recurring — waive the amount-spread filter (utilities follow the
#     weather, insurance bumps mid-year, phone plans collect one-off fees) as
#     long as the cadence is monthly-ish
#   non_spending     — moves money between household pockets, not out of them
#
# Matching stays case-insensitive against the trimmed category, so call sites
# still compare via ``.strip().lower()``.


# Tighter spread for merchants with no category vouching for them. A real
# subscription bills the same amount every period; 0.35 still absorbs a price
# rise mid-window, but rejects two unrelated shopping trips that happen to land
# in different months.
_RECURRING_TIGHT_SPREAD = 0.35

# Months of evidence required before an uncategorized merchant counts as
# recurring. Two is what a pair of grocery runs produces; three means the
# pattern survived a full billing cycle.
_MIN_MONTHS_UNTRUSTED = 3

# The ``subscription`` role marks a merchant as a subscription rather than a
# bill; ``bill`` routes it to the Bills section. They overlap heavily — the
# seed gives Subscriptions both — but differ in purpose, so they stay two
# roles rather than one with an exception list.

# Bills the user never categorized. Matched against the RAW description, not
# the merchant key — ``merchant_key._ACH_TAIL_RE`` strips exactly these tokens
# when building the key, so by then "MTGPMT" and "INS PREM" are gone.
_BILL_DESCRIPTION_RE = re.compile(
    r"(mortg|mtgpmt|ins\s+prem|insurance|utilit|assn\s+dues|hoa\s+dues"
    r"|electric|water\s+bill|city\s*of\s*\w*util)",
    re.IGNORECASE,
)

# Paying a card or moving money between own accounts. These reach the detector
# only when the transaction was never categorized — a categorized one is
# already filtered by the ``non_spending`` role in ``_is_expense``.
_CARD_PAYMENT_RE = re.compile(
    r"(e-?payment|e-?pymt|online\s+p(?:m|ay)t|online\s+payment|autopay"
    # Bank of America writes "ONLINE/MOBILE PAYMENT" — the slash keeps it out
    # of the `online\s+payment` branch above.
    r"|mobile\s+payment"
    r"|payment\s+thank\s*you|card\s+pmt|visa\s+online"
    # "Payment to Chase card ending in 5637" — a payment, not a merchant.
    r"|card\s+ending|payment\s+to\s+\w+\s+card)",
    re.IGNORECASE,
)

# A card issuer's name next to the word payment. Kept separate from the
# patterns above because the word alone is far too common to match on: plenty
# of real bills ("PROG PREMIER INS PREM", "CITYOFRALUTIL BILLPAY") carry it.
_ISSUER_PAYMENT_RE = re.compile(
    r"\b(chase|amex|american\s+express|discover|barclays?|capital\s+one|citi"
    r"|bank\s+of\s+america|bk\s+of\s+amer|synchrony|wells\s+fargo)\b"
    r"[^a-z]*(payment|pmt|pymt)\b",
    re.IGNORECASE,
)

# The ``non_commitment`` role: repeats that are consequences of a balance
# rather than commitments to anything.


def _is_card_payment(description: str) -> bool:
    """True when a description reads as paying a card off, not buying anything.

    Deliberately narrow. A card payment is money moving between the
    household's own accounts — the spending it settles was already counted
    when each purchase posted to the card — so counting the payment too
    reports the same money twice. A *loan* payment is not the same thing:
    nothing was counted when the mortgage was drawn, so ``TRUIST MORTG OLB
    MTGPMT`` must keep counting, and neither pattern matches it.
    """
    text_ = description or ""
    return bool(_CARD_PAYMENT_RE.search(text_) or _ISSUER_PAYMENT_RE.search(text_))


def _classify_commitment(description: str, category: str) -> Optional[str]:
    """Bucket a recurring merchant: ``bill``, ``subscription`` or
    ``recurring_spend``. ``None`` means it is not a commitment at all and the
    caller should drop it.

    Category wins when the user has set one; description patterns are the
    fallback that keeps an uncategorized mortgage out of the subscriptions
    list. Consumed by ``routers/bills.py`` and ``routers/subscriptions.py``
    so the bill/subscription rule lives in exactly one place.
    """
    cat = (category or "").strip().lower()
    if cat in categories_service.names_with_role(categories_service.NON_COMMITMENT):
        return None
    if cat in categories_service.names_with_role(categories_service.SUBSCRIPTION):
        return "subscription"
    if cat in categories_service.names_with_role(categories_service.BILL):
        return "bill"
    # Uncategorized from here on: fall back to what the bank wrote.
    if _is_card_payment(description):
        return None
    if _BILL_DESCRIPTION_RE.search(description or ""):
        return "bill"
    return "recurring_spend"


def _is_expense(txn: Dict[str, Any]) -> bool:
    """True when ``txn`` represents money leaving the household.

    Shared by ``group_debit_spending``, ``detect_recurring_charges``, and the
    dashboard income/expense rollup so all three agree on what counts as
    spending. Filters:
      * tagged transfers to a manual account drop out (see ``transfer_to_account_id``)
      * known non-spending categories drop out (CC payments, Zelle out, etc.)
      * a card payment the bank never categorized drops out too
      * everything else counts when its money-flow ``direction`` is outflow

    The uncategorized card payment is the one that mattered: SimpleFIN sends
    no category, so ``BANK OF AMERICA PAYMENT`` and ``CHASE CREDIT CRD
    AUTOPAY`` were counted as spending on top of the purchases they settle.
    August read $12,555 against $8,355 of income; $3,395 of it was the same
    money twice, and the savings rate reported -50%.
    """
    if txn.get("transfer_to_account_id"):
        return False
    category = (txn.get("category") or "").strip().lower()
    if category in categories_service.names_with_role(categories_service.NON_SPENDING):
        return False
    # Not gated on a missing category: these rows often carry a wrong one
    # ("BANK OF AMERICA PAYMENT" filed under Service, "Payment to Chase card
    # ending in 5637" under General), so a category is no evidence the row is
    # real spending. The patterns are narrow enough to spare loans and bills.
    if _is_card_payment(txn.get("description") or ""):
        return False
    try:
        float(txn.get("amount", 0))
    except (TypeError, ValueError):
        return False
    return txn_direction(txn) == "outflow"


# Cadence bands: (name, min_median_gap_days, max_median_gap_days,
# charges_per_month). The bands are deliberately loose — real billing dates
# drift around weekends and month lengths.
_CADENCE_BANDS = (
    ("weekly",     5,  10,  52.0 / 12.0),
    ("biweekly",  11,  18,  26.0 / 12.0),
    ("monthly",   24,  38,  1.0),
    ("bimonthly", 50,  75,  0.5),
    ("quarterly", 76, 115,  1.0 / 3.0),
    ("semiannual", 150, 220, 1.0 / 6.0),
    ("annual",   300, 430,  1.0 / 12.0),
)


# Charges per month by cadence name, derived from the bands above so a
# declared cadence and an inferred one price identically.
_CADENCE_PER_MONTH = {name: per_month for name, _, _, per_month in _CADENCE_BANDS}

# Days between charges for each cadence, used when a merchant has a declared
# cadence (no observed gaps to measure) and to judge how overdue it is.
_CADENCE_INTERVAL_DAYS = {
    "weekly": 7, "biweekly": 14, "monthly": 30, "bimonthly": 60,
    "quarterly": 91, "semiannual": 182, "annual": 365,
    # An irregular merchant gets the monthly yardstick — it is what the
    # estimated_monthly_cost already assumes.
    "irregular": 30,
}

# Cycles a merchant can miss before it stops being treated as live. Under 1.5
# is ordinary billing drift; past 3 the charge has almost certainly stopped.
_OVERDUE_CYCLES = 1.5
_DORMANT_CYCLES = 3.0


def _dataset_as_of() -> Optional[date]:
    """Newest transaction date on file.

    Staleness is measured from here, never from ``today``: if nothing has
    been imported for five weeks, every merchant is five weeks quiet and
    would look cancelled. Anchoring on the data's own horizon means a gap in
    *importing* never reads as a gap in *billing*.
    """
    newest: Optional[date] = None
    for txn in state.stored_transactions.values():
        parsed = _parse_date_obj(txn.get("date", ""))
        if parsed and (newest is None or parsed > newest):
            newest = parsed
    return newest


def _staleness(last_seen: date, interval_days: int, as_of: Optional[date]) -> tuple:
    """Return ``(days_since_last, cycles_missed, status)``.

    ``status`` is ``active`` / ``overdue`` / ``dormant``. A merchant billed
    annually is not overdue at 60 days; one billed weekly is. Dividing by the
    merchant's own interval is what makes the three thresholds mean the same
    thing for every cadence.
    """
    anchor = as_of or last_seen
    days_since = max(0, (anchor - last_seen).days)
    cycles = days_since / max(1, interval_days)
    if cycles > _DORMANT_CYCLES:
        status = "dormant"
    elif cycles > _OVERDUE_CYCLES:
        status = "overdue"
    else:
        status = "active"
    return days_since, round(cycles, 2), status


def _classify_cadence(gap_days: List[int]) -> tuple:
    """Return ``(cadence_name, charges_per_month, median_gap)`` from the gaps
    between consecutive charges. ``("irregular", None, median_gap)`` when the
    median gap doesn't fit a known billing band.
    """
    if not gap_days:
        return "irregular", None, None
    median_gap = statistics.median(gap_days)
    for name, lo, hi, per_month in _CADENCE_BANDS:
        if lo <= median_gap <= hi:
            return name, per_month, median_gap
    return "irregular", None, median_gap


def _group_expenses_by_merchant(
    aliases: Dict[str, str]
) -> Dict[str, List[Dict[str, Any]]]:
    """Bucket every expense transaction under its normalized merchant key."""
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for txn in state.stored_transactions.values():
        if not _is_expense(txn):
            continue
        amount = float(txn.get("amount", 0))
        if amount <= 0:
            continue

        date_str = txn.get("date", "")
        parsed = _parse_date_obj(date_str)
        if parsed is None:
            continue
        key = _normalize_merchant(txn.get("description", ""))
        if not key:
            continue
        # A merged merchant's charges join its canonical group, so a service
        # that renamed itself keeps one continuous history.
        key = aliases.get(key, key)

        groups[key].append({
            "description": txn.get("description", ""),
            "amount": amount,
            "date": date_str,
            "date_obj": parsed,
            "month": _parse_month_key(date_str),
            "category": txn.get("category") or "Uncategorized",
        })
    return groups


def _load_subscription_reviews() -> Dict[str, Any]:
    """The user's keep/cancel/declare answers, or ``{}`` if the DB is down.

    Read once per detection — the table is small and this is the detector's
    only round-trip.
    """
    try:
        from db import subscriptions_repo
        return subscriptions_repo.list_reviews()
    except Exception:  # noqa: BLE001 — detection must survive a DB hiccup
        logger.warning("[recurring] could not read subscription reviews", exc_info=True)
        return {}


def _survives_recurrence_gates(
    *,
    commitment_type: str,
    cadence: str,
    category: str,
    months_seen: int,
    spread: float,
    declared_cadence: Optional[str],
    min_occurrences: int,
) -> bool:
    """Whether a merchant group is really recurring, or just repeated.

    Three regimes, and which one applies is the whole policy:

    * **Declared** — the user answered, so no gate is left to apply.
    * **Unvouched** (``recurring_spend``: no category, no bill-shaped
      description) — two grocery runs in two months look exactly like a
      subscription, so this needs a real billing rhythm, a third month, and
      amounts that hold steady.
    * **Vouched** — a category or description backs it, so only the spread
      gate applies, and not even that for utilities and insurance, which
      routinely swing wider than 60% and are still bills.
    """
    if declared_cadence:
        return True

    if commitment_type == "recurring_spend":
        if cadence == "irregular":
            return False
        if months_seen < max(min_occurrences, _MIN_MONTHS_UNTRUSTED):
            return False
        return spread <= _RECURRING_TIGHT_SPREAD

    always = categories_service.names_with_role(categories_service.ALWAYS_RECURRING)
    if (category or "").strip().lower() in always:
        return True
    return spread <= _RECURRING_AMOUNT_SPREAD


def detect_recurring_charges(min_occurrences: int = 2) -> List[Dict[str, Any]]:
    """Find merchants charging the household on a regular cadence.

    Heuristic: group expense transactions by normalized merchant; keep groups
    seen in at least ``min_occurrences`` distinct months with amounts within
    ``_RECURRING_AMOUNT_SPREAD`` of each other. The gaps between consecutive
    charges classify the billing ``cadence`` (weekly … annual), which makes
    ``estimated_monthly_cost`` cadence-aware — an annual renewal contributes
    1/12 of its price, a weekly charge ~4.3x.

    ``price_change_pct`` compares the latest charge to the median so callers
    (alerts, the subscriptions review page) can flag price creep.

    Every survivor carries a ``commitment_type`` — ``bill``, ``subscription``
    or ``recurring_spend`` (see ``_classify_commitment``) — and that is the
    field consumers filter on; none of them re-derive the bucket from the
    category. A merchant with no category and no bill-shaped description faces
    stricter gates than a vouched-for one: it needs a recognized cadence,
    ``_MIN_MONTHS_UNTRUSTED`` months of history, and amounts inside
    ``_RECURRING_TIGHT_SPREAD``. Without that, two grocery runs in two months
    read as a subscription.
    """
    aliases = _merchant_aliases()
    groups = _group_expenses_by_merchant(aliases)
    reviews = _load_subscription_reviews()

    as_of = _dataset_as_of()
    out: List[Dict[str, Any]] = []
    for key, items in groups.items():
        months_seen = sorted({i["month"] for i in items if i["month"]})
        # A cadence the user declared outranks the evidence. Seven months of
        # history can never prove a yearly renewal is yearly, and a car
        # payment that shows up once is still a car payment — so a declared
        # merchant skips the month, cadence and spread gates entirely.
        declared = (reviews.get(key) or {}).get("declared_cadence")
        if not declared and len(months_seen) < min_occurrences:
            continue
        amounts = [i["amount"] for i in items]
        avg = sum(amounts) / len(amounts)
        if avg <= 0:
            continue
        items.sort(key=lambda i: i["date_obj"])
        latest = items[-1]

        review = reviews.get(key) or {}
        commitment_type = (
            review.get("declared_type")
            or _classify_commitment(latest["description"], latest["category"])
        )
        if commitment_type is None:
            continue

        gaps = [
            (items[i]["date_obj"] - items[i - 1]["date_obj"]).days
            for i in range(1, len(items))
        ]
        cadence, per_month, median_gap = _classify_cadence(gaps)

        # A declared cadence replaces the inferred one outright: the user
        # knows an annual renewal is annual after one charge, where the gaps
        # need two years to say so.
        declared_cadence = review.get("declared_cadence")
        if declared_cadence:
            cadence = declared_cadence
            # Take the band's own charges-per-month rather than deriving one
            # from the interval, so a declared "annual" costs exactly what an
            # inferred "annual" costs.
            per_month = _CADENCE_PER_MONTH.get(declared_cadence, 1.0)

        if not _survives_recurrence_gates(
            commitment_type=commitment_type,
            cadence=cadence,
            category=latest["category"],
            months_seen=len(months_seen),
            spread=(max(amounts) - min(amounts)) / avg,
            declared_cadence=declared_cadence,
            min_occurrences=min_occurrences,
        ):
            continue
        # Irregular groups that survived the month/spread gates behave like
        # the old detector: assume one charge a month.
        monthly_cost = avg * per_month if per_month else avg

        median_amount = statistics.median(amounts)
        price_change_pct = (
            round((latest["amount"] - median_amount) / median_amount * 100.0, 1)
            if median_amount > 0 else 0.0
        )

        # Typical day-of-month — median across past charges, used by the Bills
        # page to project the next due date. Resilient to one stray reissue.
        days_of_month = sorted(i["date_obj"].day for i in items)
        typical_day = days_of_month[len(days_of_month) // 2] if days_of_month else None

        # How long since this merchant last billed, in its own cycles.
        interval = (
            int(median_gap) if (median_gap and not declared_cadence)
            else _CADENCE_INTERVAL_DAYS.get(cadence, 30)
        )
        days_since, cycles_missed, status = _staleness(
            latest["date_obj"], interval, as_of,
        )
        out.append({
            "merchant_key": key,
            "sample_description": latest["description"],
            "category": latest["category"],
            "average_amount": round(avg, 2),
            "latest_amount": round(latest["amount"], 2),
            "price_change_pct": price_change_pct,
            "occurrences": len(items),
            "months_seen": len(months_seen),
            "first_seen": items[0]["date_obj"].isoformat(),
            "last_seen": latest["date_obj"].isoformat(),
            "typical_day": typical_day,
            "cadence": cadence,
            "interval_days": int(median_gap) if median_gap is not None else None,
            "estimated_monthly_cost": round(monthly_cost, 2),
            "commitment_type": commitment_type,
            "days_since_last": days_since,
            "cycles_missed": cycles_missed,
            "status": status,
            "as_of": as_of.isoformat() if as_of else None,
            "cadence_declared": bool(declared_cadence),
            "merged_from": sorted(a for a, c in aliases.items() if c == key),
        })

    out.sort(key=lambda r: r["estimated_monthly_cost"], reverse=True)
    return out


def list_commitment_candidates(limit: int = 60) -> List[Dict[str, Any]]:
    """Merchants the detector did **not** claim, offered up for declaring.

    The detector needs two charges to measure a gap, so a yearly renewal in a
    seven-month history and a car payment that billed once are both invisible
    to it — and invisible means the user can never even declare them. This is
    the list they pick from: every expense merchant that isn't already a
    detected commitment, biggest first.

    Card payments, transfers and interest are excluded the same way they are
    everywhere else, via ``_classify_commitment`` returning ``None``.
    """
    claimed = {r["merchant_key"] for r in detect_recurring_charges()}
    aliases = _merchant_aliases()

    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for txn in state.stored_transactions.values():
        if not _is_expense(txn):
            continue
        try:
            amount = float(txn.get("amount", 0))
        except (TypeError, ValueError):
            continue
        if amount <= 0:
            continue
        parsed = _parse_date_obj(txn.get("date", ""))
        if parsed is None:
            continue
        key = _normalize_merchant(txn.get("description", ""))
        if not key:
            continue
        key = aliases.get(key, key)
        if key in claimed:
            continue
        groups[key].append({
            "description": txn.get("description", ""),
            "amount": amount,
            "date_obj": parsed,
            "category": txn.get("category") or "Uncategorized",
        })

    out: List[Dict[str, Any]] = []
    for key, items in groups.items():
        items.sort(key=lambda i: i["date_obj"])
        latest = items[-1]
        if _classify_commitment(latest["description"], latest["category"]) is None:
            continue
        amounts = [i["amount"] for i in items]
        out.append({
            "merchant_key": key,
            "sample_description": latest["description"],
            "category": latest["category"],
            "latest_amount": round(latest["amount"], 2),
            "average_amount": round(sum(amounts) / len(amounts), 2),
            "occurrences": len(items),
            "last_seen": latest["date_obj"].isoformat(),
        })

    out.sort(key=lambda r: r["latest_amount"], reverse=True)
    return out[:limit]


# ---------------------------------------------------------------------------
# Balance trajectory — surface the slope of net worth over recent windows so
# the advisor can frame answers around direction, not just current totals.
# Reads ``balance_snapshots`` via the repo abstraction; never calls SimpleFIN.
# ---------------------------------------------------------------------------

_TREND_LOOKBACK_DAYS = (30, 60, 90)


def _live_account_ids() -> set:
    """Ids of the accounts the household still holds.

    An account that was disconnected keeps its ``balance_snapshots`` rows, and
    the walker below carries each account's last known balance forward
    indefinitely — so a Teller card unplugged in May went on contributing its
    final balance to every point in the series after it. Nine such ghosts sat
    between the trend figure and the real one.

    Read from the balances cache rather than a live fetch: this runs inside a
    per-day loop, and the callers are sync.
    """
    snapshot = _balances_snapshot()
    return {
        acct.get("id")
        for acct in (
            (snapshot.get("linked_accounts") or [])
            + (snapshot.get("snaptrade_accounts") or [])
            + (snapshot.get("manual_accounts") or [])
        )
        if acct.get("id")
    }


def _net_worth_at(
    snapshots_newest_first: List[Dict[str, Any]],
    target_ts: datetime,
    live_ids: Optional[set] = None,
) -> Optional[float]:
    """Approximate net worth at ``target_ts`` using the latest snapshot per
    account at or before that timestamp.

    ``live_ids`` restricts the walk to accounts the household still holds; an
    empty or absent set counts everything, which is the right answer before any
    balances have been cached.

    Returns ``None`` if no account has a snapshot at or before
    ``target_ts`` — the trend block can't compute deltas in that case.
    """
    chosen: Dict[str, Dict[str, Any]] = {}
    for snap in snapshots_newest_first:
        captured = snap.get("captured_at")
        if not isinstance(captured, datetime):
            continue
        if captured.tzinfo is None:
            captured = captured.replace(tzinfo=timezone.utc)
        if captured > target_ts:
            continue
        aid = snap["account_id"]
        if live_ids and aid not in live_ids:
            continue
        if aid in chosen:
            continue
        chosen[aid] = snap
    if not chosen:
        return None

    total = 0.0
    for snap in chosen.values():
        bucket = classify_account_bucket(
            snap.get("type") or "", snap.get("subtype") or ""
        )
        if bucket in ("cash", "real_asset"):
            # A real asset only ever changes value when the user revalues it,
            # and every edit writes a snapshot — so it belongs in the
            # timeseries on the same terms as cash, just never as cash.
            total += float(snap.get("available") or 0.0)
        elif bucket == "credit":
            # ``ledger`` on a credit card is the balance owed — counts as debt.
            total -= float(snap.get("ledger") or 0.0)
        elif bucket == "investment":
            # SnapTrade snapshots write the account's total value to both
            # ``available`` and ``ledger``; prefer ``available`` for parity
            # with the cash branch.
            val = snap.get("available")
            if val is None:
                val = snap.get("ledger")
            total += float(val or 0.0)
    return total


def _trend_label(delta_30d: Optional[float], current_nw: float) -> str:
    """Translate a 30-day net-worth delta into a short human label.

    Buckets are tuned so "stable" means ±1 % of net worth — anything
    inside that band is noise to a household-finance reader. The label
    is consumed by the advisor's system prompt; the underlying numbers
    are also exposed so the LLM can quote them directly.
    """
    if delta_30d is None:
        return "insufficient history"
    ref = abs(current_nw) if current_nw != 0 else 1.0
    pct = delta_30d / ref * 100
    if pct >= 5:
        return "rising fast"
    if pct >= 1:
        return "rising"
    if pct <= -5:
        return "declining fast"
    if pct <= -1:
        return "declining"
    return "stable"


def compute_balance_trend(
    lookbacks: tuple = _TREND_LOOKBACK_DAYS,
) -> Dict[str, Any]:
    """Return current net worth plus deltas over each lookback window.

    Shape::

        {
          "available": True,
          "current_net_worth": 12345.67,
          "net_worth_30d_ago": 12000.00,
          "delta_30d": 345.67,
          "net_worth_60d_ago": 11500.00,
          "delta_60d": 845.67,
          "net_worth_90d_ago": 11000.00,
          "delta_90d": 1345.67,
          "label": "rising"
        }

    When there are no snapshots yet, returns
    ``{"available": False, "reason": "..."}`` so the snapshot block
    stays present and the advisor can mention the gap explicitly.
    """
    from db.accounts_repo import get_repo

    max_days = max(lookbacks)
    snapshots = get_repo().get_snapshots_since(max_days + 1)
    if not snapshots:
        return {"available": False, "reason": "no balance snapshots yet"}

    live_ids = _live_account_ids()
    now = datetime.now(timezone.utc)
    current = _net_worth_at(snapshots, now, live_ids)
    if current is None:
        return {"available": False, "reason": "no usable snapshots"}

    out: Dict[str, Any] = {
        "available": True,
        "current_net_worth": round(current, 2),
    }
    delta_30d: Optional[float] = None
    for d in lookbacks:
        past_ts = now - timedelta(days=d)
        past_nw = _net_worth_at(snapshots, past_ts, live_ids)
        if past_nw is None:
            continue
        delta = current - past_nw
        out[f"net_worth_{d}d_ago"] = round(past_nw, 2)
        out[f"delta_{d}d"] = round(delta, 2)
        if d == 30:
            delta_30d = delta

    out["label"] = _trend_label(delta_30d, current)
    return out


def compute_net_worth_timeseries(months: int) -> List[Dict[str, Any]]:
    """Return a list of ``{"date": "YYYY-MM-DD", "net_worth": float}`` points
    spanning the last ``months`` months, suitable for a Dashboard line chart.

    Uses the same per-account snapshot walker as :func:`compute_balance_trend`
    so cash/credit classification stays consistent. Sample cadence:
    daily for ≤6 months, weekly for longer windows (keeps the chart light
    without losing trend shape). Returns ``[]`` when no snapshots exist.
    """
    from db.accounts_repo import get_repo

    days = max(1, int(months)) * 31
    snapshots = get_repo().get_snapshots_since(days + 1)
    if not snapshots:
        return []

    live_ids = _live_account_ids()
    step_days = 1 if months <= 6 else 7
    now = datetime.now(timezone.utc)
    out: List[Dict[str, Any]] = []
    cursor = now - timedelta(days=days)
    while cursor <= now:
        nw = _net_worth_at(snapshots, cursor, live_ids)
        if nw is not None:
            out.append({
                "date": cursor.date().isoformat(),
                "net_worth": round(nw, 2),
            })
        cursor += timedelta(days=step_days)
    return out


# ---------------------------------------------------------------------------
# Income / paycheck detection — finds the recurring inbound flows on
# depository accounts so the advisor stops asking "what's your income?" on
# every chat. Sister to ``detect_recurring_charges`` (subscriptions);
# heuristics differ on two axes:
#   * tighter amount-spread tolerance (paychecks vary little within a job)
#   * cadence-aware monthly conversion (biweekly paychecks → ×2.166/mo)
# ---------------------------------------------------------------------------

# How far a single deposit may sit from the stream's MEDIAN and still count as
# one of its paycheques. Deliberately generous: a bonus month, a tax-bracket
# shift or a three-paycheque month all land inside 25%, and the rows that fall
# outside are dropped rather than disqualifying the stream.
#
# The predecessor was a spread test — (max − min) / mean > 0.15 threw the whole
# group away — and it is the most outlier-sensitive statistic available for the
# job. One $872.21 adjustment deposit beside a normal $3,889.73 on the same day
# took an 18-paycheque salary from a 0.12 spread to 0.91 and disqualified it,
# after which the only stream regular enough to survive was a $1,000 recurring
# P2P transfer. Income read a quarter of its real value, at "high" confidence,
# and fed the savings rate, DTI, the health score and the advisor's snapshot.
_INCOME_MEDIAN_BAND = 0.25
_INCOME_MIN_OCCURRENCES = 2
# Strict P2P-platform signals: Venmo/Zelle/Cash App/PayPal in a description
# almost always indicates a person-to-person transfer, never a paycheck.
# Used both to *exclude* such rows from income detection (PR2) and to
# *include* them in recurring inbound-transfer detection (PR4).
_P2P_RE = re.compile(
    r"\b(venmo|zelle|cashapp|cash\s*app|paypal|p2p)\b",
    re.IGNORECASE,
)

# Broader signals for "this is a reimbursement / split, not income". P2P
# platforms plus reimbursement keywords. Generic "transfer" / "ACH" tokens
# are deliberately *not* matched here because real direct-deposit paychecks
# routinely include them in their description.
_INBOUND_TRANSFER_RE = re.compile(
    r"\b(venmo|zelle|cashapp|cash\s*app|paypal|reimburs)\b",
    re.IGNORECASE,
)


def _credit_account_ids() -> set:
    """Ids of every credit-type account, from the balances snapshot.

    Read from the same cache the rest of the module uses rather than a live
    fetch — this runs inside transaction walks, and the account list is not
    worth a provider round-trip.
    """
    snapshot = _balances_snapshot()
    return {
        acct.get("id")
        for acct in (
            (snapshot.get("linked_accounts") or [])
            + (snapshot.get("manual_accounts") or [])
        )
        if classify_account_bucket(acct.get("type") or "", acct.get("subtype") or "")
        == "credit"
        and acct.get("id")
    }


def _is_income_candidate(
    txn: Dict[str, Any], credit_account_ids: Optional[set] = None
) -> bool:
    """Return True if ``txn`` could plausibly be income.

    Filters:
    * Must be an inflow (money coming in).
    * Amount must be positive — sources occasionally return signed amounts;
      we standardize to positive elsewhere but keep the guard.
    * Exclude credit-card account credits (statement payments / refunds).
      A payment posts to the card as an inflow and is emphatically not income.
    * Exclude P2P-platform credits (Venmo/Zelle/Cash App/PayPal/P2P). Those
      flow through ``detect_recurring_inbound_transfers`` instead so a
      roommate's rent split doesn't get treated as a household paycheck.

    ``credit_account_ids`` is the reliable way to spot the first case and
    callers should pass it. The ``account_type`` string alone is not
    trustworthy: Teller sets it to ``credit_card``, but SimpleFIN puts the
    account's *display name* there ("Amazon Prime Rewards Visa Signature
    (5637)"), which contains no "credit" at all — so a substring test let
    every SimpleFIN card payment through as a paycheque.
    """
    if txn_direction(txn) != "inflow":
        return False
    try:
        amount = float(txn.get("amount") or 0)
    except (TypeError, ValueError):
        return False
    if amount <= 0:
        return False
    if credit_account_ids and txn.get("account_id") in credit_account_ids:
        return False
    acct_type = (txn.get("account_type") or "").lower()
    if "credit" in acct_type:
        return False
    if (txn.get("category") or "").strip().lower() == "cc payment":
        return False
    description = txn.get("description", "") or ""
    # The account-id set is the reliable signal, but it can only speak for
    # accounts the balances cache knows. This catches the payment whose
    # account cannot be classified — a CSV import, a disconnected card.
    if _is_card_payment(description):
        return False
    if _P2P_RE.search(description):
        return False
    return True


def _transfer_destination(txn: Dict[str, Any]) -> Optional[str]:
    """Which account the money ended up in — the tag if there is one.

    ``transfer_to_account_id`` is set by the user on the *source* row, so an
    outflow from checking into a Roth lands in the Roth. Untagged rows land
    wherever they were posted.
    """
    return txn.get("transfer_to_account_id") or txn.get("account_id") or None


def _is_inbound_transfer_candidate(
    txn: Dict[str, Any], include_tagged_transfers: bool = False
) -> bool:
    """Return True if ``txn`` looks like a P2P / reimbursement credit.

    Same baseline filters as ``_is_income_candidate`` (inflow, positive,
    depository) but *requires* the description to match
    ``_INBOUND_TRANSFER_RE`` and does *not* exclude P2P keywords.

    ``include_tagged_transfers`` widens the net to outflows the user tagged
    with a destination account. Those are inbound from the destination's point
    of view, and the tag is a stronger signal than any description regex, so
    they skip the keyword test. Off by default: the split-expense reader wants
    only money arriving in a spendable account.
    """
    direction = txn_direction(txn)
    try:
        amount = float(txn.get("amount") or 0)
    except (TypeError, ValueError):
        return False
    if amount <= 0:
        return False
    if include_tagged_transfers and txn.get("transfer_to_account_id"):
        return True
    if direction != "inflow":
        return False
    acct_type = (txn.get("account_type") or "").lower()
    if "credit" in acct_type:
        return False
    return bool(_INBOUND_TRANSFER_RE.search(txn.get("description", "") or ""))


def detect_recurring_income(
    min_occurrences: int = _INCOME_MIN_OCCURRENCES,
    median_band: float = _INCOME_MEDIAN_BAND,
) -> List[Dict[str, Any]]:
    """Find recurring inbound flows that look like a paycheck or stipend.

    Groups income-candidate credits by normalized merchant key
    (``_normalize_merchant``), then, per group, keeps the deposits within
    ``median_band`` of the group's MEDIAN and judges the stream on those:
      * at least ``min_occurrences`` rows survive the band
      * they cover ≥1 distinct month (a single-month burst is noise)

    Trimming rather than disqualifying is the point. A salary is a stream with
    the occasional odd deposit in it — an adjustment, a correction, a final
    stub — and a rule that reads the whole stream through its widest pair of
    values throws away eighteen good paycheques over one bad one. The median
    is unmoved by a handful of outliers, which is exactly the property wanted.

    Returns one entry per detected source with ``cadence_days`` (median gap
    between charges) and ``monthly_estimate`` so the snapshot block can sum
    a single household-level income figure.
    """
    credit_ids = _credit_account_ids()
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for txn in state.stored_transactions.values():
        if not _is_income_candidate(txn, credit_ids):
            continue
        date_str = txn.get("date", "")
        if not date_str:
            continue
        key = _normalize_merchant(txn.get("description", ""))
        if not key:
            continue
        groups[key].append({
            "description": txn.get("description", ""),
            "amount": float(txn.get("amount") or 0),
            "date": date_str,
            "month": _parse_month_key(date_str),
        })

    out: List[Dict[str, Any]] = []
    for key, items in groups.items():
        if len(items) < min_occurrences:
            continue

        median_amount = statistics.median(i["amount"] for i in items)
        if median_amount <= 0:
            continue
        # The band is what separates "a salary with an odd deposit in it" from
        # "lumpy freelance work": trimming a couple of strays leaves a stream,
        # while a genuinely irregular one loses most of its rows here and fails
        # the occurrence test below.
        kept = [
            i for i in items
            if abs(i["amount"] - median_amount) / median_amount <= median_band
        ]
        if len(kept) < min_occurrences:
            continue
        months_seen = {i["month"] for i in kept if i["month"]}
        if len(months_seen) < 1:
            continue

        amounts = [i["amount"] for i in kept]
        avg = sum(amounts) / len(amounts)
        if avg <= 0:
            continue

        # Cadence: median gap between consecutive charges in days.
        parsed = sorted(
            d for d in (_parse_date_obj(i["date"]) for i in kept) if d is not None
        )
        if len(parsed) >= 2:
            gaps = [(parsed[i + 1] - parsed[i]).days for i in range(len(parsed) - 1)]
            cadence_days = max(int(statistics.median(gaps)), 1)
        else:
            cadence_days = 30

        monthly_estimate = avg * (_DAYS_PER_MONTH / cadence_days)

        out.append({
            "merchant_key": key,
            "sample_description": kept[-1]["description"],
            "average_amount": round(avg, 2),
            # The kept rows, not every row that carried the name: they are what
            # the estimate is built from, and what the confidence test should
            # be counting. The strays are reported beside them, not hidden.
            "occurrences": len(kept),
            "deposits_ignored": len(items) - len(kept),
            "months_seen": len(months_seen),
            "cadence_days": cadence_days,
            "monthly_estimate": round(monthly_estimate, 2),
            "last_seen": max(i["date"] for i in kept),
        })

    out.sort(key=lambda r: r["monthly_estimate"], reverse=True)
    return out


def detect_recurring_inbound_transfers(
    min_occurrences: int = 2,
    max_spread: float = 0.5,
    include_tagged_transfers: bool = False,
) -> List[Dict[str, Any]]:
    """Find recurring P2P / reimbursement credits (rent splits, Venmo, Zelle).

    Heuristic differs from income detection on two axes:
    * Description must hit ``_INBOUND_TRANSFER_RE`` (P2P platform or
      "reimburs"). Random ACH credits don't qualify.
    * Spread tolerance is looser (``max_spread=0.5`` vs 0.15 for income)
      because rent splits and reimbursements vary more month-to-month.

    Returns one entry per detected stream with ``monthly_estimate`` and
    ``total_received`` so the advisor can reconcile against
    ``shared_split_recent.per_person`` to flag who is over- or
    under-paying their share. ``account_id`` names the destination account
    when every row in the stream agrees on one, and is ``None`` otherwise —
    a stream that lands in two places can't be attributed to either.
    """
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for txn in state.stored_transactions.values():
        if not _is_inbound_transfer_candidate(txn, include_tagged_transfers):
            continue
        date_str = txn.get("date", "")
        if not date_str:
            continue
        key = _normalize_merchant(txn.get("description", ""))
        if not key:
            continue
        groups[key].append({
            "description": txn.get("description", ""),
            "amount": float(txn.get("amount") or 0),
            "date": date_str,
            "month": _parse_month_key(date_str),
            "destination": _transfer_destination(txn),
        })

    out: List[Dict[str, Any]] = []
    for key, items in groups.items():
        if len(items) < min_occurrences:
            continue
        amounts = [i["amount"] for i in items]
        avg = sum(amounts) / len(amounts)
        if avg <= 0:
            continue
        spread = (max(amounts) - min(amounts)) / avg
        if spread > max_spread:
            continue

        parsed = sorted(
            d for d in (_parse_date_obj(i["date"]) for i in items) if d is not None
        )
        if len(parsed) >= 2:
            gaps = [(parsed[i + 1] - parsed[i]).days for i in range(len(parsed) - 1)]
            cadence_days = max(int(statistics.median(gaps)), 1)
        else:
            cadence_days = 30

        destinations = {i["destination"] for i in items if i["destination"]}
        out.append({
            "merchant_key": key,
            "account_id": destinations.pop() if len(destinations) == 1 else None,
            "sample_description": items[-1]["description"],
            "average_amount": round(avg, 2),
            "occurrences": len(items),
            "months_seen": len({i["month"] for i in items if i["month"]}),
            "cadence_days": cadence_days,
            "monthly_estimate": round(avg * (_DAYS_PER_MONTH / cadence_days), 2),
            "total_received": round(sum(amounts), 2),
            "last_seen": max(i["date"] for i in items),
        })

    out.sort(key=lambda r: r["monthly_estimate"], reverse=True)
    return out


def compute_income_estimate() -> Dict[str, Any]:
    """Aggregate detected income sources into a snapshot-ready block.

    Shape::

        {
          "monthly_estimate": 7250.0,
          "sources": [{...}, {...}, {...}],   # top 3 by monthly_estimate
          "confidence": "high",                # "high" | "low" | "none"
        }

    ``confidence`` is "high" when at least one source has ≥3 occurrences
    spanning ≥2 months — enough history that the advisor should treat the
    figure as reliable. "low" means we found something but it's a single
    short streak. "none" means nothing detected; the advisor should ask.
    """
    sources = detect_recurring_income()
    monthly = sum(s["monthly_estimate"] for s in sources)
    if not sources:
        confidence = "none"
    elif any(s["occurrences"] >= 3 and s["months_seen"] >= 2 for s in sources):
        confidence = "high"
    else:
        confidence = "low"
    return {
        "monthly_estimate": round(monthly, 2),
        "sources": sources[:3],
        "confidence": confidence,
    }


def category_spending_summary(
    category: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Aggregate activity for one category across a date range.

    Returns count / outflow / inflow / net_outflow / average / monthly
    breakdown. Used by the Fin agent harness for "average / total / how
    much did I spend / save on X" style questions — the right tool when
    the user wants a roll-up, not a similarity search.

    Direction split matters for **transfer-tagged categories** (e.g. the
    user's ``Savings`` category contains positive-amount debit rows for
    money going INTO savings and credit rows for money coming back).
    ``outflow`` and ``inflow`` follow the canonical money-flow
    ``direction`` field. ``net_outflow`` is outflow minus inflow — the
    right number for "how much did I actually put into Savings".

    For pure spending categories (Dining, Drinks, Groceries…), ``inflow``
    will be ~0 and ``outflow`` is the total spend. ``total`` is kept as
    an alias of ``outflow`` so existing prompts that say "total" still
    make sense.

    Category match is case-insensitive against ``txn.category`` after
    normalization. Date bounds are inclusive ISO ``YYYY-MM-DD`` strings;
    when omitted, the range is unbounded on that side.
    """
    needle = (category or "").strip().lower()
    empty = {
        "category": category, "count": 0,
        "outflow": 0.0, "inflow": 0.0, "net_outflow": 0.0,
        "total": 0.0, "average": 0.0, "by_month": {},
        "start_date": start_date, "end_date": end_date,
    }
    if not needle:
        return empty

    outflow = 0.0
    inflow = 0.0
    count = 0
    by_month: Dict[str, float] = {}
    for txn in state.stored_transactions.values():
        cat = (txn.get("category") or "").strip().lower()
        if cat != needle:
            continue
        date_str = (txn.get("date") or "")[:10]
        if not date_str:
            continue
        if start_date and date_str < start_date:
            continue
        if end_date and date_str > end_date:
            continue
        try:
            amount = float(txn.get("amount", 0))
        except (TypeError, ValueError):
            continue
        if amount <= 0:
            continue

        is_outflow = txn_direction(txn) == "outflow"
        if is_outflow:
            outflow += amount
        else:
            inflow += amount
        count += 1
        month_key = _parse_month_key(date_str)
        if month_key:
            # by_month tracks outflow only (matches existing spending-view
            # mental model). Inflow shows up in the top-level inflow field.
            delta = amount if is_outflow else 0.0
            by_month[month_key] = round(by_month.get(month_key, 0.0) + delta, 2)

    outflow = round(outflow, 2)
    inflow = round(inflow, 2)
    net_outflow = round(outflow - inflow, 2)
    average = round((outflow + inflow) / count, 2) if count else 0.0
    return {
        "category": category,
        "count": count,
        "outflow": outflow,
        "inflow": inflow,
        "net_outflow": net_outflow,
        "total": outflow,         # back-compat alias for spending categories
        "average": average,
        "by_month": dict(sorted(by_month.items())),
        "start_date": start_date,
        "end_date": end_date,
    }


# Complete months of history the discretionary baseline is drawn from — the
# same window health_service uses for its expense figure.
_DISCRETIONARY_LOOKBACK_MONTHS = 3


def _next_due_date(today: date, due_day: int) -> date:
    """Return the next calendar date matching ``due_day`` on or after ``today``.

    Caps day at the last day of the month for shorter months (Feb 30 → Feb 28/29),
    so a bill that always lands on the 30th is not projected early.
    """
    due_day = max(1, min(31, int(due_day)))
    year, month = today.year, today.month
    last = calendar.monthrange(year, month)[1]
    candidate = date(year, month, min(due_day, last))
    if candidate < today:
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
        last = calendar.monthrange(year, month)[1]
        candidate = date(year, month, min(due_day, last))
    return candidate


def _discretionary_baseline(today: date) -> Dict[str, Any]:
    """Typical monthly spend that no recurring merchant explains.

    Median across the last complete months — a mean lets one holiday month set
    the baseline, and the in-progress month is excluded for the same reason the
    dashboard stopped comparing against it. Recurring merchants are removed by
    the detector's own ``_normalize_merchant`` key so no expense is counted as
    both a bill and discretionary spend.

    ``confidence`` follows history depth: three complete months "high", two
    "low", fewer "none" — in which case ``monthly`` is None and the caller is
    expected to say the projection is incomplete.
    """
    recurring_keys = {
        r.get("merchant_key") for r in detect_recurring_charges() if r.get("merchant_key")
    }
    # Detected keys are canonical, so an alias's raw key has to be mapped
    # before the comparison or its charges count as discretionary on top of
    # the recurring total they already belong to.
    aliases = _merchant_aliases()
    totals: Dict[str, float] = {}
    for txn in state.stored_transactions.values():
        if not _is_expense(txn):
            continue
        try:
            amount = float(txn.get("amount", 0))
        except (TypeError, ValueError):
            continue
        if amount <= 0:
            continue
        month = _parse_month_key(txn.get("date", "") or "")
        if not month:
            continue
        # A month holding nothing but bills is a real zero, not a missing month.
        totals.setdefault(month, 0.0)
        merchant = _normalize_merchant(txn.get("description", "") or "")
        if aliases.get(merchant, merchant) in recurring_keys:
            continue
        totals[month] += amount

    current_month = f"{today.year:04d}-{today.month:02d}"
    complete = sorted(m for m in totals if m < current_month)
    recent = complete[-_DISCRETIONARY_LOOKBACK_MONTHS:]
    months = len(recent)
    if months >= _DISCRETIONARY_LOOKBACK_MONTHS:
        confidence = "high"
    elif months == 2:
        confidence = "low"
    else:
        confidence = "none"
    monthly = (
        round(statistics.median(totals[m] for m in recent), 2)
        if confidence != "none" else None
    )
    return {
        "method": "median_of_complete_months",
        "months": months,
        "monthly": monthly,
        "confidence": confidence,
    }


def project_cashflow(horizon_days: int = 30) -> Dict[str, Any]:
    """Project net cashflow over the next ``horizon_days`` days.

    Composes existing analytics — recurring charges, recurring inbound
    transfers, the income estimate and a discretionary baseline — into a
    forward-looking view. Used by the Fin agent harness as the
    ``project_cashflow`` tool and by ``GET /api/cashflow/projection``.

    Shape::

        {
          "horizon_days": 30,
          "expected_income": 7250.0,
          "expected_recurring_outflow": 3420.5,
          "expected_inbound_transfers": 850.0,
          "expected_discretionary_outflow": 1820.0,
          "discretionary_basis": {"method": "median_of_complete_months",
                                  "months": 3, "monthly": 1820.0,
                                  "confidence": "high"},
          "projection_incomplete": False,
          "net": 2859.5,
          "upcoming_bills": [
            {"merchant": "...", "amount": 84.99, "estimated_date": "2026-06-04"},
            ...
          ],
        }

    ``net`` is income + inbound − recurring − discretionary. Leaving
    discretionary spend out made it optimistic in one direction every time.
    Under two complete months of history the discretionary figure is omitted
    and ``projection_incomplete`` says so, rather than passing a
    recurring-only net off as the whole picture.

    ``upcoming_bills`` projects each recurring charge's next due date from
    its ``typical_day`` (median day-of-month from history), filtered to the
    horizon window. Dates are best-effort — the user's calendar of truth
    lives elsewhere; this exists for *rough* planning.
    """
    if horizon_days <= 0:
        horizon_days = 30

    today = datetime.now().date()
    horizon_end = today + timedelta(days=horizon_days)

    income = compute_income_estimate()
    monthly_income = float(income.get("monthly_estimate") or 0.0)
    expected_income = round(monthly_income * (horizon_days / 30.0), 2)

    inbound = detect_recurring_inbound_transfers()
    monthly_inbound = sum(float(i.get("monthly_estimate") or 0.0) for i in inbound)
    expected_inbound = round(monthly_inbound * (horizon_days / 30.0), 2)

    recurring = detect_recurring_charges()
    upcoming: List[Dict[str, Any]] = []
    total_outflow = 0.0
    for r in recurring:
        typical_day = r.get("typical_day")
        amount = float(r.get("estimated_monthly_cost") or 0.0)
        if not typical_day or amount <= 0:
            continue
        # Projecting a charge that stopped months ago inflates the outflow.
        if r.get("status") == "dormant":
            continue
        # Project each occurrence of typical_day inside the horizon.
        cursor = today
        for _ in range(int(horizon_days / 28) + 2):
            candidate = _next_due_date(cursor, int(typical_day))
            if candidate > horizon_end:
                break
            upcoming.append({
                "merchant": r.get("sample_description") or r.get("merchant_key"),
                "category": r.get("category"),
                "amount": amount,
                "estimated_date": candidate.isoformat(),
            })
            total_outflow += amount
            cursor = candidate + timedelta(days=1)

    basis = _discretionary_baseline(today)
    monthly_discretionary = basis["monthly"] or 0.0
    expected_discretionary = round(monthly_discretionary * (horizon_days / 30.0), 2)

    upcoming.sort(key=lambda x: x["estimated_date"])
    return {
        "horizon_days": horizon_days,
        "expected_income": expected_income,
        "expected_recurring_outflow": round(total_outflow, 2),
        "expected_inbound_transfers": expected_inbound,
        "expected_discretionary_outflow": expected_discretionary,
        "discretionary_basis": basis,
        "projection_incomplete": basis["confidence"] == "none",
        "net": round(
            expected_income + expected_inbound - total_outflow - expected_discretionary, 2
        ),
        "upcoming_bills": upcoming[:30],
    }


def _load_user_profile() -> Optional[Dict[str, Any]]:
    """Read the household profile row, or None if unset.

    Imported lazily because the router module isn't always available at
    test-collection time (unit tests may swap stores before main is imported).
    Returns the dict shape the snapshot serializer wants directly, with
    ``updated_at`` already stringified.
    """
    try:
        from db import profile_repo

        row = profile_repo.load()
    except Exception as e:
        logger.warning("[analytics] user_profile read failed: %s", e)
        return None
    if not row:
        return None
    # Unset fields are omitted rather than sent as nulls: the snapshot is
    # prompt context, and "dependents: null" reads as a fact about the
    # household that nobody stated.
    # Numeric fields keep a stored 0 — "dependents: 0" is an answer; text
    # fields drop the empty string, which is how "unset" is stored for notes.
    text_fields = ("risk_tolerance", "debt_strategy", "notes")
    numeric_fields = (
        "time_horizon_years", "dependents", "monthly_income", "emergency_fund_months",
    )
    out: Dict[str, Any] = {k: row[k] for k in text_fields if row.get(k)}
    out.update({k: row[k] for k in numeric_fields if row.get(k) is not None})
    return out or None


def _investments_snapshot() -> Optional[Dict[str, Any]]:
    """Per-holding investment detail for the advisor.

    Returns None when the household has no synced holdings so Fin's context
    stays lean. The ``holdings`` list is capped and account-level value
    history is omitted — net-worth trend already covers value over time.
    """
    from db.accounts_repo import get_repo

    holdings = get_repo().get_holdings()
    if not holdings:
        return None
    summary = summarize_holdings(holdings)
    top = [
        {
            "symbol": h["symbol"],
            "account": h.get("account_name", ""),
            "asset_type": h["asset_type"],
            "quantity": round(float(h.get("quantity") or 0.0), 6),
            "market_value": h.get("market_value"),
            "cost_basis": h.get("cost_basis"),
            "unrealized_gain": h.get("unrealized_gain"),
            "gain_pct": h.get("gain_pct"),
            "cost_basis_source": h.get("cost_basis_source"),
        }
        for h in summary["holdings"][:30]
    ]
    largest_pct = summary["concentration"][0]["pct"] if summary["concentration"] else 0.0
    return {
        "total_value": summary["total_value"],
        "total_cost": summary["total_cost"],
        "total_gain": summary["total_gain"],
        "total_gain_pct": summary["total_gain_pct"],
        "holding_count": summary["holding_count"],
        "allocation": summary["allocation"],
        "concentration": summary["concentration"],
        "largest_position_pct": largest_pct,
        "concentrated": largest_pct >= 25.0,
        "holdings": top,
    }


def build_financial_snapshot(months: int = 6) -> Dict[str, Any]:
    """Return a compact dict describing the household's financial state.

    Used as the advisor's grounding context.  Everything is read from the DB
    / in-memory stores (no SimpleFIN / SnapTrade / GSheet calls) so this is
    safe to call on every chat turn.
    """
    spending_by_month = group_debit_spending()
    recent = sorted(spending_by_month.keys())[-months:]
    trimmed = {m: spending_by_month[m] for m in recent}

    balances = _balances_snapshot()
    debts = _debts_from_accounts(balances)
    shared = _shared_split_totals(recent_months=2)
    budgets = compute_budget_statuses()
    goals = compute_goal_statuses()
    recurring = detect_recurring_charges()
    inbound_transfers = detect_recurring_inbound_transfers()
    balance_trend = compute_balance_trend()
    income = compute_income_estimate()
    user_profile = _load_user_profile()
    investments = _investments_snapshot()

    snapshot: Dict[str, Any] = {
        "balances": {
            "net_worth": balances["net_worth"],
            "total_cash": balances["total_cash"],
            "total_credit_debt": balances["total_credit_debt"],
            "total_investments": balances["total_investments"],
            "total_real_assets": balances["total_real_assets"],
            "cache_fetched_at": balances["cache_fetched_at"],
        },
        "balance_trend": balance_trend,
        "income": income,
        "accounts": {
            "simplefin": balances["linked_accounts"],
            "snaptrade": balances["snaptrade_accounts"],
            "manual": balances["manual_accounts"],
        },
        "debts": debts,
        "spending_by_month": trimmed,
        "shared_split_recent": shared,
        "budgets": budgets,
        "goals": goals,
        "recurring_charges": recurring,
        "recurring_inbound_transfers": inbound_transfers,
        "transaction_count": len(state.stored_transactions),
    }
    if user_profile:
        snapshot["user_profile"] = user_profile
    if investments:
        snapshot["investments"] = investments
    return snapshot
