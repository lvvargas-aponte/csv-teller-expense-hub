"""Analytics helpers — shared aggregations used by insights and advisor routers.

Keeps the advisor lightweight: reads from in-memory stores and the balances
cache (never triggers a live Teller fetch) so chat turns stay fast.
"""
from __future__ import annotations

import logging
import re
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import state

logger = logging.getLogger(__name__)


def _parse_month_key(date_str: str) -> str:
    """Return a YYYY-MM string from either YYYY-MM-DD or MM/DD/YYYY input."""
    if len(date_str) == 10 and date_str[2] == "/":
        parts = date_str.split("/")
        return f"{parts[2]}-{parts[0]}"
    return date_str[:7]


def _parse_date_obj(date_str: str) -> Optional[date]:
    """Parse a transaction date string into a ``date`` object.

    Accepts YYYY-MM-DD or MM/DD/YYYY (the two formats CSV imports + Teller
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
        txn_type = txn.get("transaction_type")
        amount = float(txn.get("amount", 0))
        source = txn.get("source", "")

        is_expense = (
            txn_type == "debit"
            or (source == "discover" and txn_type == "credit" and amount > 0)
            or (txn_type is None and amount > 0)
        )
        if not is_expense:
            continue

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
# Teller surfaces ``type='investment'`` reliably, but subtype labels vary
# across institutions — match case-insensitively against the user's free-text
# input from the Accounts modal too.
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


def _balances_snapshot() -> Dict[str, Any]:
    """Read cached Teller balances + live manual accounts without calling Teller.

    Walks the raw account list and reclassifies each one through
    ``_classify_account_bucket`` so investment / retirement accounts surface
    as their own bucket — the pre-summed ``teller_cash`` / ``teller_credit_debt``
    scalars in the cache only cover depository + credit and would otherwise
    silently drop investment value from net worth.
    """
    cache = state._balances_cache or {}
    teller_accounts = cache.get("teller_accounts", []) or []

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
    for acct in list(teller_accounts) + manual_accounts:
        bucket = _classify_account_bucket(acct.get("type", ""), acct.get("subtype", ""))
        if bucket == "cash":
            total_cash += float(acct.get("available", 0.0) or 0.0)
        elif bucket == "credit":
            total_credit += float(acct.get("ledger", 0.0) or 0.0)
        elif bucket == "investment":
            # Investments report value via ``available`` (Teller's convention
            # for non-depository accounts is to put the position value there);
            # fall back to ``ledger`` if available is empty.
            value = float(acct.get("available", 0.0) or 0.0)
            if value == 0.0:
                value = float(acct.get("ledger", 0.0) or 0.0)
            total_investments += value

    return {
        "net_worth": round(total_cash + total_investments - total_credit, 2),
        "total_cash": round(total_cash, 2),
        "total_credit_debt": round(total_credit, 2),
        "total_investments": round(total_investments, 2),
        "teller_accounts": teller_accounts,
        "manual_accounts": manual_accounts,
        "cache_fetched_at": cache.get("fetched_at"),
    }


def _debts_from_accounts(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract credit-type accounts as debts.  When the user has configured
    per-account details (APR, min payment, due day) via the Accounts tab, those
    are attached here so the advisor can reason over them without asking.
    """
    debts: List[Dict[str, Any]] = []
    for acct in snapshot.get("teller_accounts", []) + snapshot.get("manual_accounts", []):
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
    for acct in state._balances_cache.get("teller_accounts", []) or []:
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
    is robust to irregular snapshot cadence (Teller sync may not run
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

# Strip transaction-noise tokens that vary between charges of the same merchant
# (transaction ids, location codes, dates embedded in descriptions, "*REF12345").
_NOISE_RE = re.compile(r"[\d#*]+")
_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_merchant(description: str) -> str:
    """Collapse description into a stable merchant key (lowercase, no digits)."""
    if not description:
        return ""
    cleaned = _NOISE_RE.sub(" ", description.lower())
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    return cleaned[:40]


def detect_recurring_charges(min_occurrences: int = 2) -> List[Dict[str, Any]]:
    """Find merchants charging the household on a regular cadence.

    Heuristic: group debit transactions by normalized merchant; keep groups
    that appear in at least ``min_occurrences`` distinct months with amounts
    within 25% of each other.  Returns one entry per detected subscription
    with ``estimated_monthly_cost`` so the advisor can flag total spend.
    """
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for txn in state.stored_transactions.values():
        txn_type = txn.get("transaction_type")
        amount = float(txn.get("amount", 0))
        source = txn.get("source", "")

        is_expense = (
            txn_type == "debit"
            or (source == "discover" and txn_type == "credit" and amount > 0)
            or (txn_type is None and amount > 0)
        )
        if not is_expense or amount <= 0:
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
        # Reject highly variable groups — true subscriptions are tightly priced.
        spread = (max(amounts) - min(amounts)) / avg
        if spread > 0.25:
            continue

        last_seen = max(i["date"] for i in items)
        # Rough monthly cost: average per-charge × distinct-months frequency / span.
        # For monthly subscriptions this collapses to ≈ average amount.
        out.append({
            "merchant_key": key,
            "sample_description": items[-1]["description"],
            "category": items[-1]["category"],
            "average_amount": round(avg, 2),
            "occurrences": len(items),
            "months_seen": len(months_seen),
            "last_seen": last_seen,
            "estimated_monthly_cost": round(avg, 2),
        })

    out.sort(key=lambda r: r["estimated_monthly_cost"], reverse=True)
    return out


# ---------------------------------------------------------------------------
# Balance trajectory — surface the slope of net worth over recent windows so
# the advisor can frame answers around direction, not just current totals.
# Reads ``balance_snapshots`` via the repo abstraction; never calls Teller.
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
    for snap in chosen.values():
        acct_type = (snap.get("type") or "").lower()
        if acct_type == "depository":
            total += float(snap.get("available") or 0.0)
        elif acct_type == "credit":
            # ``ledger`` on a credit card is the balance owed — counts as debt.
            total -= float(snap.get("ledger") or 0.0)
        # Other types (investment, loan, etc.) are intentionally skipped
        # here — PR3 will handle investment as a separate bucket.
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
# 30 days / typical paycheck cadence:
#   weekly   → 7d   → ×4.286
#   biweekly → 14d  → ×2.143
#   semi-mo  → 15d  → ×2.000
#   monthly  → 30d  → ×1.000
_DAYS_PER_MONTH = 30.0


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
    * Amount must be positive — Teller occasionally returns signed amounts;
      we standardize to positive elsewhere but keep the guard.
    * Discover CSVs use ``transaction_type='credit'`` for *purchases* (their
      sign convention is inverted), so we exclude them outright.
    * Exclude credit-card account credits (statement payments / refunds).
      ``account_type`` from Teller is e.g. ``credit_card``; CSV uploads to
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


def build_financial_snapshot(months: int = 6) -> Dict[str, Any]:
    """Return a compact dict describing the household's financial state.

    Used as the advisor's grounding context.  Everything is read from memory
    (no Teller / GSheet calls) so this is safe to call on every chat turn.
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
            "teller": balances["teller_accounts"],
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
    return snapshot
