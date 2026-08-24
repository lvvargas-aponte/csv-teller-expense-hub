"""The factors a credit score is built from — measured, never scored.

This module deliberately produces no composite number. A score is a model fit
to a bureau file: payment history is 35% of FICO and its reportable events (a
30+ day delinquency, a charge-off, a collection) are invisible to a bank feed;
length of history and hard inquiries are not in this system at all; and every
figure here covers only the accounts the user connected, while a real file
covers all of them, open and closed. An estimate built on roughly a third of
the inputs would be wrong by tens of points, and people quote displayed scores
in real borrowing decisions. The panel shows levers; the user gets the number
free from their issuer.

The one factor this app measures well is utilization — 30% of the score, and
the only one that can move within a single month. Most tools get it wrong: a
bureau sees the balance on the *statement* date, not today's and not the
post-payment one. ``statement_day`` is already stored per card and
``balance_snapshots`` already records every refresh, so the reported figure is
derivable from data on disk.
"""
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import balances_service
import state
from analytics import classify_account_bucket

logger = logging.getLogger(__name__)

# A refresh doesn't land on the statement day to the hour. Outside this window
# there is no reported figure — today's balance is a different number, not a
# stand-in for it.
STATEMENT_TOLERANCE_DAYS = 3

# Utilization thresholds worth naming. 30% is the conventional shelf; 10% is
# where the factor stops costing anything.
UTILIZATION_TARGETS = (30.0, 10.0)

_SNAPSHOT_LOOKBACK_DAYS = 400
_INSTALLMENT_SUBTYPES = frozenset({"loan", "mortgage", "student", "auto"})


def _as_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _details(account_id: str) -> Dict[str, Any]:
    return state.account_details.get(account_id) or {}


def _float_or_none(value: Any) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _parse_day(value: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _statement_date(today: date, statement_day: int) -> date:
    """The most recent statement cut on or before ``today``."""
    day = max(1, min(31, int(statement_day)))
    cursor = today.replace(day=1)
    last_day = _last_day_of(cursor)
    candidate = cursor.replace(day=min(day, last_day))
    if candidate > today:
        cursor = (cursor - timedelta(days=1)).replace(day=1)
        last_day = _last_day_of(cursor)
        candidate = cursor.replace(day=min(day, last_day))
    return candidate


def _next_statement_date(today: date, statement_day: int) -> date:
    """The next statement cut strictly after ``today``."""
    cut = _statement_date(today, statement_day)
    cursor = (cut.replace(day=1) + timedelta(days=32)).replace(day=1)
    last_day = _last_day_of(cursor)
    return cursor.replace(day=min(max(1, min(31, int(statement_day))), last_day))


def _last_day_of(any_day: date) -> int:
    first_next = date(
        any_day.year + (1 if any_day.month == 12 else 0),
        1 if any_day.month == 12 else any_day.month + 1,
        1,
    )
    return (first_next - timedelta(days=1)).day


def _snapshots_by_account() -> Dict[str, List[Dict[str, Any]]]:
    from db.accounts_repo import get_repo

    out: Dict[str, List[Dict[str, Any]]] = {}
    for snap in get_repo().get_snapshots_since(_SNAPSHOT_LOOKBACK_DAYS):
        captured = _as_datetime(snap.get("captured_at"))
        if captured is None:
            continue
        out.setdefault(snap["account_id"], []).append({**snap, "captured_at": captured})
    return out


def _statement_balance(
    snapshots: List[Dict[str, Any]], cut: date
) -> tuple[Optional[float], Optional[date]]:
    """The snapshot nearest the statement cut, within tolerance."""
    best = None
    best_distance = None
    for snap in snapshots:
        captured = snap["captured_at"].date()
        distance = abs((captured - cut).days)
        if distance > STATEMENT_TOLERANCE_DAYS:
            continue
        if best_distance is None or distance < best_distance:
            best, best_distance = snap, distance
    if best is None:
        return None, None
    return float(best.get("ledger") or 0.0), best["captured_at"].date()


def _lever(
    reported_balance: float, limit: float, today: date, statement_day: Optional[int]
) -> Optional[Dict[str, Any]]:
    """What to pay, and by when, to land under a utilization threshold.

    The deadline is the statement day, not the due day: paying after the cut
    still clears the balance but the bureau has already seen the old one.
    """
    for target in UTILIZATION_TARGETS:
        allowed = limit * target / 100.0
        if reported_balance > allowed:
            pay_by = (
                _next_statement_date(today, statement_day).isoformat()
                if statement_day else None
            )
            return {
                "pay_by": pay_by,
                "amount": round(reported_balance - allowed, 2),
                "gets_to_pct": target,
            }
    return None


def _utilization_block(cards, snapshots, today: date) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    reported_balance_total = 0.0
    reported_limit_total = 0.0
    current_balance_total = 0.0
    current_limit_total = 0.0

    for acct in cards:
        details = _details(acct.id)
        limit = _float_or_none(details.get("credit_limit"))
        if not limit or limit <= 0:
            continue
        statement_day = details.get("statement_day")
        current_balance = float(acct.ledger or 0.0)

        reported_balance, as_of = (None, None)
        if statement_day:
            reported_balance, as_of = _statement_balance(
                snapshots.get(acct.id, []), _statement_date(today, int(statement_day))
            )

        reported_pct = (
            round(reported_balance / limit * 100.0, 1)
            if reported_balance is not None else None
        )
        current_pct = round(current_balance / limit * 100.0, 1)

        current_balance_total += current_balance
        current_limit_total += limit
        if reported_balance is not None:
            reported_balance_total += reported_balance
            reported_limit_total += limit

        rows.append({
            "account_id": acct.id,
            "name": acct.name,
            "reported_pct": reported_pct,
            "current_pct": current_pct,
            "statement_day": int(statement_day) if statement_day else None,
            "limit": round(limit, 2),
            "reported_balance": (
                round(reported_balance, 2) if reported_balance is not None else None
            ),
            "as_of": as_of.isoformat() if as_of else None,
            "lever": (
                _lever(reported_balance, limit, today, statement_day)
                if reported_balance is not None else None
            ),
        })

    rows.sort(key=lambda r: r["reported_pct"] if r["reported_pct"] is not None else -1,
              reverse=True)
    return {
        "overall_reported_pct": (
            round(reported_balance_total / reported_limit_total * 100.0, 1)
            if reported_limit_total > 0 else None
        ),
        "overall_current_pct": (
            round(current_balance_total / current_limit_total * 100.0, 1)
            if current_limit_total > 0 else None
        ),
        "cards": rows,
        "cards_over_30": sum(
            1 for r in rows
            if r["reported_pct"] is not None and r["reported_pct"] > 30.0
        ),
        "all_cards_at_zero": bool(rows) and all(
            (r["reported_pct"] or 0.0) == 0.0 and r["current_pct"] == 0.0 for r in rows
        ),
    }


def _timeliness_block(cards, today: date) -> Dict[str, Any]:
    """Per card per cycle, was a payment seen on or before the due day?

    Counts *observed* cycles only. The app cannot see a delinquency and cannot
    see an account the user has not connected, so this is a statement about
    what was observed — never a clean bill of health.
    """
    card_ids = {acct.id for acct in cards}
    cycles: Dict[tuple, Dict[str, Any]] = {}

    for txn in state.stored_transactions.values():
        account_id = txn.get("account_id")
        if account_id not in card_ids:
            continue
        paid_on = _parse_day(txn.get("date"))
        if paid_on is None or paid_on > today:
            continue
        if (txn.get("direction") or "") != "inflow":
            continue

        due_day = _details(account_id).get("due_day")
        if not due_day:
            continue
        last_day = _last_day_of(paid_on)
        due_on = paid_on.replace(day=min(int(due_day), last_day))
        key = (account_id, f"{paid_on.year:04d}-{paid_on.month:02d}")

        entry = cycles.get(key)
        # Earliest payment in the cycle is the one that answers the question.
        if entry is None or paid_on < entry["paid_on_date"]:
            cycles[key] = {
                "account_id": account_id,
                "cycle": key[1],
                "paid_on_date": paid_on,
                "paid_on": paid_on.isoformat(),
                "due_on": due_on.isoformat(),
                "on_time": paid_on <= due_on,
            }

    observed = sorted(cycles.values(), key=lambda c: c["cycle"], reverse=True)
    return {
        "cycles_observed": len(observed),
        "cycles_with_payment_before_due": sum(1 for c in observed if c["on_time"]),
        "latest": [
            {k: v for k, v in c.items() if k != "paid_on_date"} for c in observed[:6]
        ],
    }


def _months_between(opened: date, today: date) -> int:
    months = (today.year - opened.year) * 12 + (today.month - opened.month)
    if today.day < opened.day:
        months -= 1
    return max(0, months)


def _history_block(accounts, today: date) -> Dict[str, Any]:
    ages: List[int] = []
    missing = 0
    for acct in accounts:
        opened = _parse_day(_details(acct.id).get("opened_on"))
        if opened is None:
            missing += 1
            continue
        ages.append(_months_between(opened, today))
    return {
        "average_age_months": round(sum(ages) / len(ages)) if ages else None,
        "oldest_account_months": max(ages) if ages else None,
        "accounts_missing_opened_on": missing,
    }


def _new_credit_block(accounts, today: date) -> Dict[str, Any]:
    cutoff = today - timedelta(days=365)
    opened_recently = 0
    for acct in accounts:
        opened = _parse_day(_details(acct.id).get("opened_on"))
        if opened is not None and opened >= cutoff:
            opened_recently += 1
    return {"opened_last_12_months": opened_recently}


def _mix_block(accounts) -> Dict[str, Any]:
    revolving = 0
    installment = 0
    for acct in accounts:
        if (acct.subtype or "").lower().strip() in _INSTALLMENT_SUBTYPES:
            installment += 1
        else:
            revolving += 1
    return {"revolving": revolving, "installment": installment}


async def compute(today: Optional[date] = None) -> Dict[str, Any]:
    """Every credit factor this app can honestly measure, and no score."""
    today = today or date.today()
    summary = await balances_service.build_summary()
    credit_accounts = [
        a for a in summary.accounts
        if classify_account_bucket(a.type, a.subtype) == "credit"
    ]
    revolving = [
        a for a in credit_accounts
        if (a.subtype or "").lower().strip() not in _INSTALLMENT_SUBTYPES
    ]
    snapshots = _snapshots_by_account()
    count = len(credit_accounts)

    return {
        "utilization": _utilization_block(revolving, snapshots, today),
        "payment_timeliness": _timeliness_block(revolving, today),
        "history": _history_block(credit_accounts, today),
        "new_credit": _new_credit_block(credit_accounts, today),
        "mix": _mix_block(credit_accounts),
        "coverage_note": (
            f"Measured on {count} connected account{'' if count == 1 else 's'}."
        ),
    }
