"""Trace the transactions that are paying down a single debt.

The Payoff Planner needs to answer two questions about a debt the user is
actively working on: how far it has moved from where it started, and which
transactions moved it.

Neither is a plain lookup. A card payment lands in the ledger twice — once as
a credit on the card itself, once as a debit on whatever account funded it —
and the funding-side row is the one the user recognises ("my Truist payment").
Showing both would double the total, so the two sides are reconciled into one
payment per real-world event.

Balances are floats to match the rest of the app; these are display figures
reconciled against statements by eye, not ledger postings.
"""
import logging
import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

# A funding-side debit is treated as the same real payment as a card-side
# credit when the amounts match and the dates are this close. Card payments
# post to the two accounts a few days apart; a week is wide enough to cover
# a weekend plus a bank holiday without swallowing the next month's payment.
_MATCH_WINDOW_DAYS = 7

# Words that appear in so many account names they'd match half the ledger.
_GENERIC_TOKENS = frozenset({
    "BANK", "CREDIT", "CARD", "CARDS", "LOAN", "LOANS", "ACCOUNT", "CHECKING",
    "SAVINGS", "LINE", "RATE", "FIXED", "YEAR", "UNION", "FEDERAL", "NATIONAL",
    "FINANCIAL", "SERVICES", "MORTGAGE", "PAYMENT", "PLATINUM", "REWARDS",
    "CASH", "BLUE", "DOUBLE", "EVERYDAY", "PREFERRED", "SIGNATURE",
})


def match_keywords(name: str, institution: str) -> List[str]:
    """Distinctive uppercase tokens identifying this debt in a description.

    "Synchrony - Credit Cards CARECREDIT / SYNCHRONY BANK (0742)" yields
    {CARECREDIT, SYNCHRONY} — enough to spot "CARECREDIT/SYNCB PAYMENT" on the
    funding account, without "CREDIT" or "BANK" dragging in every other row.

    Tokens shorter than four characters are dropped: they produce far more
    false positives than matches, and an account whose every token is generic
    simply gets no funding-side matching rather than bad matching.
    """
    tokens = re.findall(r"[A-Za-z]{4,}", f"{name} {institution}")
    seen: List[str] = []
    for tok in tokens:
        upper = tok.upper()
        if upper in _GENERIC_TOKENS or upper in seen:
            continue
        seen.append(upper)
    return seen


def _parse_date(value: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _is_card_side_payment(txn: Dict[str, Any], debt_account_id: str) -> bool:
    """A credit posted on the debt account itself.

    SimpleFIN signs by balance effect, so on a liability a credit is money
    arriving — a payment. Refunds and merchant returns look identical here and
    are counted as progress, which is honest: they do reduce the balance.
    """
    return (
        txn.get("account_id") == debt_account_id
        and txn.get("transaction_type") == "credit"
    )


def _is_funding_side_payment(
    txn: Dict[str, Any], funding_account_id: str, keywords: Sequence[str]
) -> bool:
    """A debit on the funding account whose description names this debt."""
    if not funding_account_id or txn.get("account_id") != funding_account_id:
        return False
    if txn.get("transaction_type") != "debit":
        return False
    description = (txn.get("description") or "").upper()
    return any(kw in description for kw in keywords)


def _reconcile(
    card_side: List[Dict[str, Any]], funding_side: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Collapse the two sides of each payment into one row.

    Greedy nearest-date match on equal amounts. Each card-side row is consumed
    at most once, so two identical payments in the same week still reconcile
    to two payments rather than one — the count matters as much as the total.
    """
    unmatched = list(card_side)
    out: List[Dict[str, Any]] = []

    for funding in funding_side:
        fdate = funding["_date"]
        best: Optional[Dict[str, Any]] = None
        best_gap: Optional[timedelta] = None
        for candidate in unmatched:
            if abs(candidate["amount"] - funding["amount"]) >= 0.005:
                continue
            gap = abs(candidate["_date"] - fdate)
            if gap > timedelta(days=_MATCH_WINDOW_DAYS):
                continue
            if best_gap is None or gap < best_gap:
                best, best_gap = candidate, gap
        if best is not None:
            unmatched.remove(best)
            merged = dict(funding)
            merged["source"] = "both"
            merged["posted_date"] = best["date"]
            out.append(merged)
        else:
            out.append(funding)

    out.extend(unmatched)
    out.sort(key=lambda p: p["date"], reverse=True)
    return out


def debt_payment_progress(
    debt_account_id: str,
    details: Optional[Dict[str, Any]],
    account_meta: Optional[Dict[str, Any]],
    transactions: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Payments against one debt, plus how far it has moved from its start.

    ``details`` supplies ``payoff_start_balance`` (what was owed when the user
    started tracking), ``payoff_start_date`` (payments before it are another
    chapter and are ignored) and ``payment_account_id`` (the funding account).
    All three are optional — with none set this still returns the card-side
    payments, which is the useful half.

    ``paid_down`` deliberately comes from the balances, not from summing
    payments: interest, fees and anything the matcher missed all sit in the
    gap, and a progress figure that disagreed with the balance on screen would
    be worse than no figure. ``total_payments`` is reported alongside it so a
    divergence is visible rather than hidden.
    """
    details = details or {}
    account_meta = account_meta or {}

    start_balance = details.get("payoff_start_balance")
    start_balance = float(start_balance) if start_balance is not None else None
    start_date = _parse_date(details.get("payoff_start_date"))
    funding_account_id = details.get("payment_account_id") or ""

    keywords = match_keywords(
        account_meta.get("name", ""), account_meta.get("institution", "")
    )

    card_side: List[Dict[str, Any]] = []
    funding_side: List[Dict[str, Any]] = []

    for txn in transactions:
        txn_date = _parse_date(txn.get("date"))
        if txn_date is None:
            continue
        if start_date is not None and txn_date < start_date:
            continue

        is_card = _is_card_side_payment(txn, debt_account_id)
        is_funding = _is_funding_side_payment(txn, funding_account_id, keywords)
        if not (is_card or is_funding):
            continue

        row = {
            "transaction_id": txn.get("transaction_id") or txn.get("id"),
            "date": str(txn.get("date"))[:10],
            "description": txn.get("description") or "",
            "amount": round(abs(float(txn.get("amount") or 0.0)), 2),
            "account_id": txn.get("account_id"),
            "institution": txn.get("institution") or "",
            "source": "account" if is_card else "funding",
            "_date": txn_date,
        }
        if row["amount"] <= 0:
            continue
        (card_side if is_card else funding_side).append(row)

    payments = _reconcile(card_side, funding_side)
    for p in payments:
        p.pop("_date", None)

    total_payments = round(sum(p["amount"] for p in payments), 2)

    current_balance = abs(float(account_meta.get("ledger") or 0.0))
    paid_down = (
        round(start_balance - current_balance, 2)
        if start_balance is not None
        else None
    )
    percent_paid = (
        round(max(0.0, min(100.0, (paid_down / start_balance) * 100)), 2)
        if start_balance and start_balance > 0 and paid_down is not None
        else None
    )

    return {
        "account_id": debt_account_id,
        "start_balance": start_balance,
        "start_date": start_date.isoformat() if start_date else None,
        "current_balance": round(current_balance, 2),
        "paid_down": paid_down,
        "percent_paid": percent_paid,
        "remaining": round(current_balance, 2),
        "payment_account_id": funding_account_id or None,
        "matched_keywords": keywords,
        "total_payments": total_payments,
        "payment_count": len(payments),
        "payments": payments,
    }
