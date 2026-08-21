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
from typing import Any, Dict, List, Mapping, Optional

import state

logger = logging.getLogger(__name__)

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

    Discover CSVs store purchases as transaction_type="credit" with a positive
    amount (raw CSV amounts are negative for charges); other sources use
    transaction_type="debit".  Both are counted as spending here.
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


def _classify_account_bucket(acct_type: str, subtype: str) -> str:
    """Return ``'cash'`` / ``'credit'`` / ``'investment'`` / ``'other'``.

    Investment matching is intentionally permissive — both ``type='investment'``
    and any recognized retirement/brokerage ``subtype`` qualify so the user
    can flag a 401(k) as a manual depository account with the right subtype
    and have it accounted for correctly.
    """
    t = (acct_type or "").lower()
    s = (subtype or "").lower().strip()
    if t == "investment" or s in _INVESTMENT_SUBTYPES:
        return "investment"
    if t == "depository":
        return "cash"
    if t == "credit":
        return "credit"
    return "other"


def is_empty_synced_account(acct: Mapping[str, Any]) -> bool:
    """True for a synced account that reports no value at all.

    Several brokerages hand the aggregator an auto-created sub-account every
    customer gets whether or not they ever funded it — Robinhood's separate
    crypto account is the common one. Showing a $0 card on Investments and a
    $0 row in Accounts for something the household doesn't own is pure noise,
    so the display layers (``routers/investments`` and ``routers/balances``)
    filter on this rather than the sync dropping it: the sync's job is to
    record what the brokerage reported, and an account reappears the instant
    it reports a balance.

    Only applied to *synced* accounts. A manual account with a $0 balance was
    typed in deliberately and always shows. Note the value here is the
    brokerage-reported account total, not a sum of positions, so an account
    that is funded but hasn't propagated its positions yet still passes.
    """
    return (
        float(acct.get("available") or 0.0) == 0.0
        and float(acct.get("ledger") or 0.0) == 0.0
    )


def summarize_holdings(holdings: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate a flat list of holdings into a portfolio summary.

    Single source of truth for both ``GET /investments/portfolio`` and the
    advisor's ``investments`` snapshot block. Each input holding is the dict
    shape ``accounts_repo.get_holdings()`` returns. Output: per-holding rows
    enriched with ``cost_basis`` / ``unrealized_gain`` / ``gain_pct`` plus
    portfolio totals, allocation by asset type, and concentration ranking.
    """
    enriched: List[Dict[str, Any]] = []
    total_value = 0.0
    total_cost = 0.0
    for h in holdings:
        mv = h.get("market_value")
        qty = float(h.get("quantity") or 0.0)
        avg = h.get("average_purchase_price")
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
        enriched.append(
            {**h, "cost_basis": cost, "unrealized_gain": gain, "gain_pct": gain_pct}
        )

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
    ``_classify_account_bucket`` so investment / retirement accounts surface
    as their own bucket — the pre-summed ``simplefin_cash`` /
    ``simplefin_credit_debt`` scalars in the cache only cover depository +
    credit and would otherwise silently drop investment value from net worth.
    SnapTrade-synced investment accounts live under their own
    ``snaptrade_accounts`` cache key; the valueless ones are filtered so the
    advisor's account list matches what the Accounts tab shows.
    """
    cache = state._balances_cache or {}
    linked_accounts = list(cache.get("simplefin_accounts", []) or [])
    snaptrade_accounts = [
        a for a in (cache.get("snaptrade_accounts", []) or [])
        if not is_empty_synced_account(a)
    ]

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
    credit_account_ids = set()
    for acct in list(linked_accounts) + list(snaptrade_accounts) + manual_accounts:
        bucket = _classify_account_bucket(acct.get("type", ""), acct.get("subtype", ""))
        if bucket == "cash":
            total_cash += float(acct.get("available", 0.0) or 0.0)
        elif bucket == "credit":
            total_credit += float(acct.get("ledger", 0.0) or 0.0)
            credit_account_ids.add(acct.get("id"))
        elif bucket == "investment":
            # Investments report value via ``available`` (the convention for
            # non-depository accounts is to put the position value there);
            # fall back to ``ledger`` if available is empty.
            value = float(acct.get("available", 0.0) or 0.0)
            if value == 0.0:
                value = float(acct.get("ledger", 0.0) or 0.0)
            total_investments += value

    # Imported in-body to keep the module dependency direction one-way
    # (properties -> analytics), matching how db.accounts_repo is reached.
    import properties as properties_domain
    real_estate = properties_domain.compute_real_estate_position(
        counted_account_ids=credit_account_ids
    )

    net_worth = (
        total_cash + total_investments - total_credit
        + real_estate["total_value"] - real_estate["unlinked_debt"]
    )
    return {
        "net_worth": round(net_worth, 2),
        "total_cash": round(total_cash, 2),
        "total_credit_debt": round(total_credit, 2),
        "total_investments": round(total_investments, 2),
        "total_property_value": real_estate["total_value"],
        "total_property_debt": real_estate["total_debt"],
        "total_property_equity": real_estate["total_equity"],
        "linked_accounts": linked_accounts,
        "snaptrade_accounts": snaptrade_accounts,
        "manual_accounts": manual_accounts,
        "cache_fetched_at": cache.get("simplefin_fetched_at"),
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


def compute_budget_statuses() -> List[Dict[str, Any]]:
    """For each configured budget, attach current-month spending + percent used.

    Read by both ``GET /budgets`` (UI list) and ``build_financial_snapshot``
    (advisor context).  Categories are matched case-insensitively against the
    aggregated spending so users don't have to mirror the exact casing the bank
    sends.
    """
    spending = group_debit_spending().get(_current_month_key(), {})
    spending_lc = {k.lower(): v for k, v in spending.items()}

    out: List[Dict[str, Any]] = []
    for raw in state.budgets.values():
        category = raw.get("category", "")
        limit = float(raw.get("monthly_limit", 0.0))
        spent = float(spending_lc.get(category.lower(), 0.0))
        pct = round(spent / limit * 100.0, 1) if limit > 0 else 0.0
        out.append({
            "category": category,
            "monthly_limit": round(limit, 2),
            "notes": raw.get("notes", ""),
            "current_month_spent": round(spent, 2),
            "percent_used": pct,
            "over_budget": limit > 0 and spent > limit,
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

# Strip transaction-noise tokens that vary between charges of the same merchant.
# Digits + ``#`` + ``*`` always go; the second pass below tackles structured
# tails (WEB ID:, ACH/PMT tokens, state codes) and processor prefixes
# (SQ *, TST*, PP*) so the same merchant collapses to one key across months.
_NOISE_RE = re.compile(r"[\d#*]+")
_WHITESPACE_RE = re.compile(r"[\s\-_/]+")
# Mixed-alphanumeric "session id" tokens like ``F4KP2T``, ``6BVHGR`` that some
# merchants embed in every charge — strip so the same merchant doesn't fork
# into one merchant-key per charge. Gated to tokens 4–10 chars with at least
# one letter AND at least one digit so real words ("4G", "AT&T") survive.
_SESSION_ID_RE = re.compile(
    r"\b(?=[a-z0-9]*[a-z])(?=[a-z0-9]*\d)[a-z0-9]{4,10}\b",
    re.IGNORECASE,
)
_PROCESSOR_PREFIX_RE = re.compile(
    r"^(sq\s*\*|tst\s*\*|pp\s*\*|paypal\s*\*|amzn\s+mktp\s+us\*?)\s*",
    re.IGNORECASE,
)
_ACH_TAIL_RE = re.compile(
    r"\b(web\s*id|ach|pmt|payment|epayment|xfer|pos|recur|aut(?:o|opay)?|mob|olb|mtgpmt|mortg)\b[:\s]*",
    re.IGNORECASE,
)
_STATE_CODE_TAIL_RE = re.compile(r"\s+[a-z]{2}\s*$", re.IGNORECASE)

# Amount-spread tolerance for grouping: utilities/phone/insurance routinely
# vary 30-50% month to month; 0.60 keeps them in while still rejecting genuinely
# noisy categories like gas stations (where the spread is typically > 1.0).
_RECURRING_AMOUNT_SPREAD = 0.60

# Categories where the merchant is *always* a recurring bill, regardless of how
# much the dollar amount swings month-to-month (utilities follow the weather,
# insurance bumps mid-year, phone plans get one-off fees). For these we skip
# the amount-spread filter as long as the cadence is monthly-ish.
_ALWAYS_RECURRING_CATEGORIES = frozenset({
    "utilities",
    "insurance",
    "rent",
    "mortgage",
    "phone",
    "internet",
    "subscription",
    "subscriptions",
})

# Categories that move money between household pockets rather than out of it.
# Match is case-insensitive against the trimmed category. Kept in lowercase
# so callers can compare via ``.strip().lower()``.
_NON_SPENDING_CATEGORIES = frozenset({
    "cc payment",
    "credit card payment",
    "payments and credits",
    "zelle out",
    "transfer",
    "transfers",
})


def _normalize_merchant(description: str) -> str:
    """Collapse description into a stable merchant key.

    Pipeline:
      1. Lowercase.
      2. Drop processor prefixes (``SQ *``, ``TST*``, ``AMZN MKTP US``).
      3. Strip ACH/wire tail tokens (``WEB ID:``, ``ACH``, ``PMT``…).
      4. Replace remaining digits / ``#`` / ``*`` with spaces.
      5. Drop a trailing 2-letter state code (``... Doral FL`` → ``... doral``).
      6. Collapse whitespace, trim to 40 chars.
    """
    if not description:
        return ""
    cleaned = description.lower()
    cleaned = _PROCESSOR_PREFIX_RE.sub("", cleaned)
    cleaned = _ACH_TAIL_RE.sub(" ", cleaned)
    # Strip mixed-alphanumeric session ids *before* the digit-only sweep so
    # ``F4KP2T`` doesn't survive as ``fkpt``.
    cleaned = _SESSION_ID_RE.sub(" ", cleaned)
    cleaned = _NOISE_RE.sub(" ", cleaned)
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    cleaned = _STATE_CODE_TAIL_RE.sub("", cleaned).strip()
    return cleaned[:40]


def _is_expense(txn: Dict[str, Any]) -> bool:
    """True when ``txn`` represents money leaving the household.

    Shared by ``group_debit_spending``, ``detect_recurring_charges``, and the
    dashboard income/expense rollup so all three agree on what counts as
    spending. Filters:
      * tagged transfers to a manual account drop out (see ``transfer_to_account_id``)
      * known non-spending categories drop out (CC payments, Zelle out, etc.)
      * Discover credits with positive amount stay in (their sign convention is inverted)
      * other debits / null-typed positive amounts stay in
    """
    if txn.get("transfer_to_account_id"):
        return False
    category = (txn.get("category") or "").strip().lower()
    if category in _NON_SPENDING_CATEGORIES:
        return False

    txn_type = txn.get("transaction_type")
    try:
        amount = float(txn.get("amount", 0))
    except (TypeError, ValueError):
        return False
    source = txn.get("source", "")

    return (
        txn_type == "debit"
        or (source == "discover" and txn_type == "credit" and amount > 0)
        or (txn_type is None and amount > 0)
    )


def detect_recurring_charges(min_occurrences: int = 2) -> List[Dict[str, Any]]:
    """Find merchants charging the household on a regular cadence.

    Heuristic: group debit transactions by normalized merchant; keep groups
    that appear in at least ``min_occurrences`` distinct months with amounts
    within ``_RECURRING_AMOUNT_SPREAD`` of each other.  Returns one entry per
    detected subscription with ``estimated_monthly_cost`` so the advisor can
    flag total spend.
    """
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for txn in state.stored_transactions.values():
        if not _is_expense(txn):
            continue
        amount = float(txn.get("amount", 0))
        if amount <= 0:
            continue

        date_str = txn.get("date", "")
        if not date_str:
            continue
        key = _normalize_merchant(txn.get("description", ""))
        if not key:
            continue

        groups[key].append({
            "description": txn.get("description", ""),
            "amount": amount,
            "date": date_str,
            "month": _parse_month_key(date_str),
            "category": txn.get("category") or "Uncategorized",
        })

    out: List[Dict[str, Any]] = []
    for key, items in groups.items():
        months_seen = sorted({i["month"] for i in items if i["month"]})
        if len(months_seen) < min_occurrences:
            continue
        amounts = [i["amount"] for i in items]
        avg = sum(amounts) / len(amounts)
        if avg <= 0:
            continue
        spread = (max(amounts) - min(amounts)) / avg
        # Skip the spread gate for always-recurring categories — utilities and
        # insurance routinely swing wider than 60% but are still bills.
        item_cat = (items[-1]["category"] or "").strip().lower()
        if item_cat not in _ALWAYS_RECURRING_CATEGORIES and spread > _RECURRING_AMOUNT_SPREAD:
            continue

        last_seen = max(i["date"] for i in items)
        # Typical day-of-month — median across past charges, used by the Bills
        # page to project the next due date. Resilient to one stray reissue.
        days_of_month = sorted(
            int(i["date"][8:10]) for i in items if len(i["date"]) >= 10
        )
        typical_day = days_of_month[len(days_of_month) // 2] if days_of_month else None
        out.append({
            "merchant_key": key,
            "sample_description": items[-1]["description"],
            "category": items[-1]["category"],
            "average_amount": round(avg, 2),
            "occurrences": len(items),
            "months_seen": len(months_seen),
            "last_seen": last_seen,
            "typical_day": typical_day,
            "estimated_monthly_cost": round(avg, 2),
        })

    out.sort(key=lambda r: r["estimated_monthly_cost"], reverse=True)
    return out


# ---------------------------------------------------------------------------
# Balance trajectory — surface the slope of net worth over recent windows so
# the advisor can frame answers around direction, not just current totals.
# Reads ``balance_snapshots`` via the repo abstraction; never calls SimpleFIN.
# ---------------------------------------------------------------------------

_TREND_LOOKBACK_DAYS = (30, 60, 90)


def _net_worth_at(
    snapshots_newest_first: List[Dict[str, Any]],
    target_ts: datetime,
) -> Optional[float]:
    """Approximate net worth at ``target_ts`` using the latest snapshot per
    account at or before that timestamp.

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
        if aid in chosen:
            continue
        chosen[aid] = snap
    if not chosen:
        return None

    total = 0.0
    credit_account_ids = set()
    for aid, snap in chosen.items():
        bucket = _classify_account_bucket(
            snap.get("type") or "", snap.get("subtype") or ""
        )
        if bucket == "cash":
            total += float(snap.get("available") or 0.0)
        elif bucket == "credit":
            # ``ledger`` on a credit card is the balance owed — counts as debt.
            total -= float(snap.get("ledger") or 0.0)
            credit_account_ids.add(aid)
        elif bucket == "investment":
            # SnapTrade snapshots write the account's total value to both
            # ``available`` and ``ledger``; prefer ``available`` for parity
            # with the cash branch.
            val = snap.get("available")
            if val is None:
                val = snap.get("ledger")
            total += float(val or 0.0)

    # Real estate, on the same basis as the headline figure — otherwise the
    # trend line and the net-worth number on the same screen disagree by the
    # value of the house.
    import properties as properties_domain
    total += properties_domain.real_estate_at(
        target_ts.date(), counted_account_ids=credit_account_ids
    )["net_contribution"]
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

    now = datetime.now(timezone.utc)
    current = _net_worth_at(snapshots, now)
    if current is None:
        return {"available": False, "reason": "no usable snapshots"}

    out: Dict[str, Any] = {
        "available": True,
        "current_net_worth": round(current, 2),
    }
    delta_30d: Optional[float] = None
    for d in lookbacks:
        past_ts = now - timedelta(days=d)
        past_nw = _net_worth_at(snapshots, past_ts)
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

    step_days = 1 if months <= 6 else 7
    now = datetime.now(timezone.utc)
    out: List[Dict[str, Any]] = []
    cursor = now - timedelta(days=days)
    while cursor <= now:
        nw = _net_worth_at(snapshots, cursor)
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

# Spread of paycheck amounts within the same job is typically <5%; we allow
# a little extra slack for bonus-month bumps and tax-bracket shifts.
_INCOME_AMOUNT_SPREAD = 0.15
_INCOME_MIN_OCCURRENCES = 2
# Strict P2P-platform signals: Venmo/Zelle/Cash App/PayPal in a description
# almost always indicates a person-to-person transfer, never a paycheck.
# Used both to *exclude* such rows from income detection (PR2) and to
# *include* them in recurring inbound-transfer detection (PR4).
_P2P_RE = re.compile(
    r"\b(venmo|zelle|cashapp|cash\s*app|paypal)\b",
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


def _is_income_candidate(txn: Dict[str, Any]) -> bool:
    """Return True if ``txn`` could plausibly be income.

    Filters:
    * Must be a credit (money coming in).
    * Amount must be positive — sources occasionally return signed amounts;
      we standardize to positive elsewhere but keep the guard.
    * Discover CSVs use ``transaction_type='credit'`` for *purchases* (their
      sign convention is inverted), so we exclude them outright.
    * Exclude credit-card account credits (statement payments / refunds).
      ``account_type`` from SimpleFIN is e.g. ``credit_card``; CSV uploads to
      a credit-typed account also tag the row.
    * Exclude P2P-platform credits (Venmo/Zelle/Cash App/PayPal). Those flow
      through ``detect_recurring_inbound_transfers`` instead so a roommate's
      rent split doesn't get treated as a household paycheck.
    """
    if txn.get("transaction_type") != "credit":
        return False
    try:
        amount = float(txn.get("amount") or 0)
    except (TypeError, ValueError):
        return False
    if amount <= 0:
        return False
    if txn.get("source") == "discover":
        return False
    acct_type = (txn.get("account_type") or "").lower()
    if "credit" in acct_type:
        return False
    if _P2P_RE.search(txn.get("description", "") or ""):
        return False
    return True


def _is_inbound_transfer_candidate(txn: Dict[str, Any]) -> bool:
    """Return True if ``txn`` looks like a P2P / reimbursement credit.

    Same baseline filters as ``_is_income_candidate`` (credit, positive,
    depository, not Discover) but *requires* the description to match
    ``_INBOUND_TRANSFER_RE`` and does *not* exclude P2P keywords.
    """
    if txn.get("transaction_type") != "credit":
        return False
    try:
        amount = float(txn.get("amount") or 0)
    except (TypeError, ValueError):
        return False
    if amount <= 0:
        return False
    if txn.get("source") == "discover":
        return False
    acct_type = (txn.get("account_type") or "").lower()
    if "credit" in acct_type:
        return False
    return bool(_INBOUND_TRANSFER_RE.search(txn.get("description", "") or ""))


def detect_recurring_income(
    min_occurrences: int = _INCOME_MIN_OCCURRENCES,
    max_spread: float = _INCOME_AMOUNT_SPREAD,
) -> List[Dict[str, Any]]:
    """Find recurring inbound flows that look like a paycheck or stipend.

    Groups income-candidate credits by normalized merchant key
    (``_normalize_merchant``), then keeps groups that:
      * have at least ``min_occurrences`` rows
      * have amount spread within ``max_spread`` of the average
      * cover ≥1 distinct month (single-month bursts are noise, not income)

    Returns one entry per detected source with ``cadence_days`` (median gap
    between charges) and ``monthly_estimate`` so the snapshot block can sum
    a single household-level income figure.
    """
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for txn in state.stored_transactions.values():
        if not _is_income_candidate(txn):
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
        months_seen = {i["month"] for i in items if i["month"]}
        if len(months_seen) < 1:
            continue

        amounts = [i["amount"] for i in items]
        avg = sum(amounts) / len(amounts)
        if avg <= 0:
            continue
        spread = (max(amounts) - min(amounts)) / avg
        if spread > max_spread:
            continue

        # Cadence: median gap between consecutive charges in days.
        parsed = sorted(
            d for d in (_parse_date_obj(i["date"]) for i in items) if d is not None
        )
        if len(parsed) >= 2:
            gaps = [(parsed[i + 1] - parsed[i]).days for i in range(len(parsed) - 1)]
            cadence_days = max(int(statistics.median(gaps)), 1)
        else:
            cadence_days = 30

        monthly_estimate = avg * (_DAYS_PER_MONTH / cadence_days)

        out.append({
            "merchant_key": key,
            "sample_description": items[-1]["description"],
            "average_amount": round(avg, 2),
            "occurrences": len(items),
            "months_seen": len(months_seen),
            "cadence_days": cadence_days,
            "monthly_estimate": round(monthly_estimate, 2),
            "last_seen": max(i["date"] for i in items),
        })

    out.sort(key=lambda r: r["monthly_estimate"], reverse=True)
    return out


def detect_recurring_inbound_transfers(
    min_occurrences: int = 2,
    max_spread: float = 0.5,
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
    under-paying their share.
    """
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for txn in state.stored_transactions.values():
        if not _is_inbound_transfer_candidate(txn):
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

        out.append({
            "merchant_key": key,
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
    ``outflow`` is debits (Discover credits with positive amount also
    count here — Discover's sign convention is inverted). ``inflow`` is
    non-Discover credits. ``net_outflow`` is outflow minus inflow — the
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

        txn_type = txn.get("transaction_type")
        source = (txn.get("source") or "")
        # Discover stores charges as ``credit`` with positive amount — count
        # those as outflow. Everything else: debit = outflow, credit = inflow.
        is_outflow = (
            txn_type == "debit"
            or (source == "discover" and txn_type == "credit")
            or (txn_type is None)
        )
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


def _monthly_debt_minimums() -> float:
    """Minimum payments across credit cards plus scheduled loan payments.

    Loan payments include escrow: the household really does have to send
    that money every month, even though escrow doesn't reduce principal.
    (Property *economics* excludes escrow from debt service for a different
    reason — there it would double-count against operating expenses. Both
    are correct in their own context.)
    """
    total = 0.0
    for details in state.account_details.values():
        minimum = (details or {}).get("minimum_payment")
        if minimum:
            try:
                total += float(minimum)
            except (TypeError, ValueError):
                continue

    try:
        import properties as properties_domain
        from db import properties_repo
        for loan in properties_repo.get_repo().list_loans():
            total += properties_domain.loan_payment(loan)
            total += float(loan.get("escrow_monthly") or 0)
    except Exception:  # noqa: BLE001 - properties are optional
        pass

    return round(total, 2)


def _required_goal_contributions() -> float:
    """What the household's goals demand each month to land on time."""
    total = 0.0
    for goal in compute_goal_statuses():
        required = goal.get("monthly_required")
        if required and required > 0:
            total += required
    return round(total, 2)


def compute_safe_to_spend(as_of: Optional[date] = None) -> Dict[str, Any]:
    """How much is genuinely free to spend today, and this week.

    The envelope is what's left after everything already promised::

        discretionary_pool = income
                           − fixed bills
                           − minimum debt payments
                           − required goal contributions

        remaining = discretionary_pool − discretionary spend so far this month
        daily     = remaining / days left in the month (today inclusive)

    **Overspending lowers tomorrow's number by construction.** ``remaining``
    is recomputed from actual month-to-date spend on every call while
    ``days_left`` shrinks by one each day, so spending $200 over today
    automatically tightens tomorrow. There is deliberately no carry-over
    ledger: it would be a second source of truth that drifts from the
    transactions it claims to summarize.

    ``as_of`` exists so the UI can recompute at yesterday and show the
    delta — seeing the number move because of last night's dinner is what
    turns it from a readout into a consequence.

    Two refusals rather than fabrications:

    * No detected income → ``available: false``. A safe-to-spend figure
      derived from a guessed salary is worse than no figure.
    * A negative pool → the daily number clamps to 0 and ``over_budget``
      is set. "You're $340 past plan" is useful; a negative allowance is
      not a spendable instruction.
    """
    today = as_of or date.today()

    income_block = compute_income_estimate()
    monthly_income = float(income_block.get("monthly_estimate") or 0.0)
    inbound = sum(
        float(t.get("monthly_estimate") or 0.0)
        for t in detect_recurring_inbound_transfers()
    )

    # Rental profit is real income the household can spend. Only positive
    # cash flow counts — a property running at a loss is already reflected
    # in the transactions it generates.
    rental_net = 0.0
    try:
        import properties as properties_domain
        portfolio = properties_domain.compute_portfolio(as_of=today)
        rental_net = max(0.0, float(portfolio.get("monthly_cash_flow") or 0.0))
    except Exception:  # noqa: BLE001 - properties are optional
        rental_net = 0.0

    total_income = round(monthly_income + inbound + rental_net, 2)

    if income_block.get("confidence") == "none" and total_income <= 0:
        return {
            "available": False,
            "reason": "no_income_detected",
            "as_of": today.isoformat(),
            "detail": (
                "No recurring income found in your transactions. Add an "
                "income estimate and this becomes a real number."
            ),
        }

    # Fixed bills: recurring charges in categories that are unambiguously
    # obligations. Anything else is treated as discretionary, which keeps
    # a monthly restaurant habit from being quietly reclassified as a bill.
    bill_merchants: set = set()
    fixed_bills = 0.0
    for charge in detect_recurring_charges():
        category = (charge.get("category") or "").strip().lower()
        if category in _ALWAYS_RECURRING_CATEGORIES:
            fixed_bills += float(charge.get("estimated_monthly_cost") or 0.0)
            bill_merchants.add(charge["merchant_key"])
    fixed_bills = round(fixed_bills, 2)

    minimum_debt = _monthly_debt_minimums()
    required_savings = _required_goal_contributions()

    commitments = round(fixed_bills + minimum_debt + required_savings, 2)
    discretionary_pool = round(total_income - commitments, 2)

    # Month-to-date discretionary spend: expenses, minus anything already
    # counted as a fixed bill or a debt payment, so no dollar is subtracted
    # from the pool twice.
    month_key = f"{today.year:04d}-{today.month:02d}"
    spent_so_far = 0.0
    excluded_categories: set = set()
    for txn in state.stored_transactions.values():
        if not _is_expense(txn):
            continue
        date_str = txn.get("date", "")
        if _parse_month_key(date_str) != month_key:
            continue
        parsed = _parse_date_obj(date_str)
        if parsed is None or parsed > today:
            continue

        category = (txn.get("category") or "").strip().lower()
        if category in _ALWAYS_RECURRING_CATEGORIES:
            excluded_categories.add(txn.get("category") or "")
            continue
        if _normalize_merchant(txn.get("description", "")) in bill_merchants:
            excluded_categories.add(txn.get("category") or "Recurring bill")
            continue
        try:
            spent_so_far += abs(float(txn.get("amount", 0)))
        except (TypeError, ValueError):
            continue
    spent_so_far = round(spent_so_far, 2)

    remaining = round(discretionary_pool - spent_so_far, 2)
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    days_left = days_in_month - today.day + 1          # today counts
    daily = round(max(0.0, remaining) / days_left, 2)
    weekly = round(daily * min(7, days_left), 2)

    # Straight-line expectation for pace: at day 10 of 30, roughly a third
    # of the pool should be gone.
    elapsed = today.day
    expected = round(discretionary_pool * elapsed / days_in_month, 2) if days_in_month else 0.0
    if spent_so_far > expected * 1.1:
        pace = "over"
    elif spent_so_far < expected * 0.9:
        pace = "under"
    else:
        pace = "on_track"

    caveats: List[str] = []
    if income_block.get("confidence") == "low":
        caveats.append(
            "Income is estimated from a short history, so this figure may move."
        )
    if not state.budgets:
        caveats.append(
            "No budgets set — the pool is everything left after bills, "
            "debt minimums and goals."
        )
    if discretionary_pool < 0:
        caveats.append(
            "Committed spending exceeds income, so there is no discretionary "
            "pool to draw from this month."
        )

    return {
        "available": True,
        "as_of": today.isoformat(),
        "period": {
            "start": f"{month_key}-01",
            "days_total": days_in_month,
            "days_elapsed": elapsed,
            "days_remaining": days_left,
        },
        "income": {
            "monthly": total_income,
            "confidence": income_block.get("confidence"),
            "components": {
                "paychecks": round(monthly_income, 2),
                "inbound_transfers": round(inbound, 2),
                "rental_net": round(rental_net, 2),
            },
        },
        "commitments": {
            "fixed_bills": fixed_bills,
            "minimum_debt_payments": minimum_debt,
            "required_goal_contributions": required_savings,
            "total": commitments,
        },
        "discretionary_pool": discretionary_pool,
        "spent_so_far": spent_so_far,
        "remaining_pool": remaining,
        "daily_safe_to_spend": daily,
        "weekly_safe_to_spend": weekly,
        "over_budget": remaining < 0,
        "overspend_amount": round(abs(remaining), 2) if remaining < 0 else 0.0,
        "pace": pace,
        "expected_spend_to_date": expected,
        # Surfaced so the number can be argued with. The most common failure
        # of a safe-to-spend figure is the user not believing it.
        "excluded_categories": sorted(c for c in excluded_categories if c),
        "assumptions": {
            "basis": "calendar_month",
            "fixed_bill_source": "detected_recurring",
            "days_remaining_includes_today": True,
        },
        "caveats": caveats,
    }


def project_cashflow(horizon_days: int = 30) -> Dict[str, Any]:
    """Project net cashflow over the next ``horizon_days`` days.

    Composes existing analytics — recurring charges, recurring inbound
    transfers, and income estimate — into a forward-looking view. Used by
    the Fin agent harness as the ``project_cashflow`` tool so the advisor
    can answer "what's my next 30 days look like" precisely.

    Shape::

        {
          "horizon_days": 30,
          "expected_income": 7250.0,
          "expected_recurring_outflow": 3420.5,
          "expected_inbound_transfers": 850.0,
          "net": 4679.5,
          "upcoming_bills": [
            {"merchant": "...", "amount": 84.99, "estimated_date": "2026-06-04"},
            ...
          ],
        }

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
        # Project the next due date in or after today using typical_day.
        year, month = today.year, today.month
        for _ in range(int(horizon_days / 28) + 2):
            try:
                candidate = date(year, month, min(int(typical_day), 28))
            except ValueError:
                break
            if candidate >= today and candidate <= horizon_end:
                upcoming.append({
                    "merchant": r.get("sample_description") or r.get("merchant_key"),
                    "category": r.get("category"),
                    "amount": amount,
                    "estimated_date": candidate.isoformat(),
                })
                total_outflow += amount
            month += 1
            if month > 12:
                month = 1
                year += 1
            if candidate > horizon_end:
                break

    upcoming.sort(key=lambda x: x["estimated_date"])
    return {
        "horizon_days": horizon_days,
        "expected_income": expected_income,
        "expected_recurring_outflow": round(total_outflow, 2),
        "expected_inbound_transfers": expected_inbound,
        "net": round(expected_income + expected_inbound - total_outflow, 2),
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
        from sqlalchemy import text as _text
        from db.base import sync_engine as _engine
    except Exception:
        return None
    try:
        with _engine.connect() as conn:
            row = conn.execute(
                _text(
                    "SELECT risk_tolerance, time_horizon_years, dependents, "
                    "       debt_strategy, notes, updated_at "
                    "FROM user_profile WHERE id = 'household'"
                )
            ).fetchone()
    except Exception as e:
        logger.debug(f"[analytics] user_profile read skipped: {e}")
        return None
    if not row:
        return None
    out: Dict[str, Any] = {}
    if row[0]:
        out["risk_tolerance"] = row[0]
    if row[1] is not None:
        out["time_horizon_years"] = int(row[1])
    if row[2] is not None:
        out["dependents"] = int(row[2])
    if row[3]:
        out["debt_strategy"] = row[3]
    if row[4]:
        out["notes"] = row[4]
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


def _wealth_rollups() -> Dict[str, Any]:
    """Roll-up-only blocks for the advisor's grounding context.

    Deliberately thin. Every one of these has a dedicated tool that returns
    the full detail on request, so the snapshot carries just enough for the
    model to know the capability exists and is worth reaching for — putting
    fifty projection rows in front of it on every turn would crowd out the
    conversation and get misquoted besides.

    Each block is omitted entirely when there's nothing to say, matching how
    ``investments`` already behaves.
    """
    out: Dict[str, Any] = {}

    try:
        sts = compute_safe_to_spend()
        if sts.get("available"):
            out["safe_to_spend"] = {
                "daily": sts["daily_safe_to_spend"],
                "weekly": sts["weekly_safe_to_spend"],
                "remaining_pool": sts["remaining_pool"],
                "days_remaining": sts["period"]["days_remaining"],
                "over_budget": sts["over_budget"],
                "pace": sts["pace"],
            }
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[analytics] safe-to-spend rollup skipped: {e}")

    try:
        import properties as properties_domain
        portfolio = properties_domain.compute_portfolio()
        if portfolio.get("count"):
            out["properties"] = {
                "count": portfolio["count"],
                "total_value": portfolio["total_value"],
                "total_debt": portfolio["total_debt"],
                "total_equity": portfolio["total_equity"],
                "monthly_cash_flow": portfolio["monthly_cash_flow"],
                "ytd_principal_paid": portfolio["ytd_principal_paid"],
                "underperforming": [p["name"] for p in portfolio["underperforming"]],
                "watch": [p["name"] for p in portfolio["watch"]],
            }
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[analytics] properties rollup skipped: {e}")

    try:
        from db import properties_repo
        loans = properties_repo.get_repo().list_loans()
        if loans:
            out["loans"] = [
                {
                    "name": loan.get("name"),
                    "type": loan.get("loan_type"),
                    "rate_pct": loan.get("interest_rate_pct"),
                    "payment": loan.get("payment_amount"),
                }
                for loan in loans
            ]
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[analytics] loans rollup skipped: {e}")

    try:
        import retirement as retirement_domain
        inputs = retirement_domain.build_retirement_inputs()
        if inputs.properties or inputs.investment_balance > 0:
            projection = retirement_domain.project_retirement(inputs)
            out["retirement"] = {
                "feasible": projection["feasible"],
                "earliest_retirement_year": projection["earliest_retirement_year"],
                "earliest_retirement_age": projection["earliest_retirement_age"],
                "model": "deterministic",
                "warnings": projection["warnings"],
            }
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[analytics] retirement rollup skipped: {e}")

    try:
        import coach
        actions = coach.build_actions(limit=3)
        if actions["actions"]:
            out["next_actions"] = [
                {
                    "urgency": a["urgency"],
                    "title": a["title"],
                    "amount": a["amount"],
                }
                for a in actions["actions"]
            ]
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[analytics] next-actions rollup skipped: {e}")

    return out


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
    snapshot.update(_wealth_rollups())
    return snapshot
