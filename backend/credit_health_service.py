"""Credit utilization composition — per-card balance vs. configured limit.

One composition, three readers: the Credit Health card, the alert feed, and
the health score. It reads balances from ``balances_service.build_summary``
rather than walking the account stores itself — a manual account's stored
``ledger`` is only its *starting* balance, so a hand-rolled walk reports a
figure the Accounts page contradicts.
"""
from typing import Any, Dict, List, Optional

import analytics
import balances_service
import state
from analytics import _INSTALLMENT_SUBTYPES, classify_account_bucket

# Utilization thresholds worth naming. 30% is the conventional shelf; 10% is
# where the factor stops costing anything.
UTILIZATION_TARGETS = (30.0, 10.0)
SHELF_PCT = 30.0        # the conventional "keep under this" line
HIGH_PCT = 50.0         # where a lender stops reading the balance as noise
CLEAR_PCT = 10.0        # where utilization stops costing anything
MAXED_PCT = 100.0       # the limit itself — the last band a card can cross

# Installment debt (mortgage, auto, student) — ``simplefin.infer_account_bucket``
# tags these ``subtype="loan"`` — is listed but not rated: a revolving-utilization
# ratio says nothing useful about a fixed-schedule loan. The set itself lives in
# analytics, which is also where /accounts/metadata serves it to the frontend.


def _status_for(pct: float) -> str:
    if pct >= HIGH_PCT:
        return "high"
    if pct >= SHELF_PCT:
        return "warn"
    return "good"


def _levers_for(balance: float, limit: float) -> List[Dict[str, Any]]:
    """What to pay to land under each utilization threshold, nearest first.

    Deliberately computed from today's balance rather than the statement-date
    one. The statement-date figure is the more correct answer to "what will the
    bureau see", but it needs a ``statement_day`` and a snapshot taken near it,
    and neither exists for a SimpleFIN card. An amount that is right today
    beats a blank where the right one would go.
    """
    out: List[Dict[str, Any]] = []
    for target in UTILIZATION_TARGETS:
        allowed = limit * target / 100.0
        if balance > allowed:
            out.append({
                "gets_to_pct": target,
                "amount": round(balance - allowed, 2),
            })
    return out


def _projection_for(
    balance: float, limit: float, net_change: Optional[float]
) -> Optional[Dict[str, Any]]:
    """Where this card lands next month if it keeps doing what it just did.

    Only reported when the balance is growing. A shrinking card needs no
    warning, and projecting a payoff date off one month of history would put a
    precise-looking date on a number that a single large payment invented.
    """
    if not net_change or net_change <= 0 or limit <= 0:
        return None
    projected = balance + net_change
    projected_pct = round(projected / limit * 100.0, 1)
    current_pct = balance / limit * 100.0
    crosses = next(
        (band for band in (SHELF_PCT, HIGH_PCT, MAXED_PCT)
         if current_pct <= band < projected_pct),
        None,
    )
    headroom = limit - balance
    return {
        "net_change": round(net_change, 2),
        "projected_pct": projected_pct,
        "crosses": crosses,
        "months_to_limit": (
            int(headroom // net_change) if headroom > 0 else 0
        ),
    }


def _limit_for(account_id: str) -> Optional[float]:
    raw = (state.account_details.get(account_id) or {}).get("credit_limit")
    try:
        return float(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


async def build() -> Dict[str, Any]:
    """Per-card utilization plus the household totals.

    Cards without a configured limit are still returned so the UI can prompt
    the user to fill one in; they contribute nothing to the overall figure.

    Installment loans are dropped entirely. They were once listed as
    ``not_applicable`` so the page could show every debt in one place, which
    rendered a mortgage as a row with no percentage and an empty bar — the
    loan belongs on /debt's own list, not in a utilization composition.
    """
    summary = await balances_service.build_summary()
    activity = await analytics.compute_card_activity()

    out: List[Dict[str, Any]] = []
    total_balance = 0.0
    total_limit = 0.0

    for acct in summary.accounts:
        if classify_account_bucket(acct.type, acct.subtype) != "credit":
            continue
        # A closed card's limit is gone with it. Counting it would divide the
        # balances by headroom that no longer exists and understate utilization.
        if acct.closed_on:
            continue
        if (acct.subtype or "").lower().strip() in _INSTALLMENT_SUBTYPES:
            continue

        balance = float(acct.ledger or 0.0)
        limit = _limit_for(acct.id)

        if limit and limit > 0:
            pct = round(balance / limit * 100.0, 1)
            status = _status_for(pct)
            total_balance += balance
            total_limit += limit
        else:
            pct = None
            status = "unknown"

        card_activity = (activity.get("by_account") or {}).get(acct.id)
        latest = (card_activity or {}).get("latest")
        rated = bool(limit and limit > 0)

        out.append({
            "account_id": acct.id,
            "institution": acct.institution,
            "name": acct.name,
            "balance": round(balance, 2),
            "credit_limit": round(limit, 2) if limit is not None else None,
            "utilization_pct": pct,
            "status": status,
            "headroom": round(limit - balance, 2) if rated else None,
            "levers": _levers_for(balance, limit) if rated else [],
            "projection": (
                _projection_for(balance, limit, (latest or {}).get("net_change"))
                if rated else None
            ),
            "activity": card_activity,
        })

    overall_pct = (
        round(total_balance / total_limit * 100.0, 1) if total_limit > 0 else None
    )
    # Per-card and aggregate utilization are separate inputs to a score, and
    # they can disagree loudly: five cards can average a comfortable 20% while
    # one of them sits at 46%. Naming the count is what stops the headline
    # figure from reading as an all-clear.
    def _to_target(target: float) -> float:
        return round(
            sum(
                lever["amount"]
                for card in out
                for lever in card["levers"]
                if lever["gets_to_pct"] == target
            ),
            2,
        )

    return {
        "accounts": out,
        "total_balance": round(total_balance, 2),
        "total_limit": round(total_limit, 2),
        "overall_utilization_pct": overall_pct,
        "overall_status": _status_for(overall_pct) if overall_pct is not None else "unknown",
        "cards_over_30": sum(
            1 for c in out
            if c["utilization_pct"] is not None and c["utilization_pct"] > SHELF_PCT
        ),
        "to_30_total": _to_target(SHELF_PCT),
        "to_10_total": _to_target(CLEAR_PCT),
        "interest_billed_latest": activity.get("interest_billed_latest"),
        "latest_month": activity.get("latest_month"),
    }
