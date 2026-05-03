"""Alerts router — surfaces actionable warnings derived from existing analytics.

Rule-based, no LLM: composes budget statuses, goal pacing, credit
utilization, and recurring-charge anomalies into a single feed.  Severity
levels are advisory: ``info`` = nice to know, ``warn`` = attention soon,
``error`` = act now.
"""
import statistics
from typing import Any, Dict, List

from fastapi import APIRouter

import state
from analytics import (
    compute_budget_statuses,
    compute_goal_statuses,
    detect_recurring_charges,
)

router = APIRouter()


def _budget_alerts() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for status in compute_budget_statuses():
        if not status.get("over_budget"):
            # Also warn at 90%+ of cap.
            if status.get("percent_used", 0.0) >= 90.0:
                out.append({
                    "severity": "warn",
                    "category": "budget",
                    "message": (
                        f"{status['category']} budget at {status['percent_used']:.0f}% "
                        f"(${status['current_month_spent']:.0f} / ${status['monthly_limit']:.0f})"
                    ),
                    "link": "/finances/plan",
                })
            continue
        out.append({
            "severity": "error",
            "category": "budget",
            "message": (
                f"{status['category']} over budget — spent ${status['current_month_spent']:.0f} "
                f"vs. ${status['monthly_limit']:.0f} cap"
            ),
            "link": "/finances/plan",
        })
    return out


def _goal_alerts() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for goal in compute_goal_statuses():
        pace = goal.get("pace_status")
        if pace in ("behind", "stalled"):
            out.append({
                "severity": "warn" if pace == "behind" else "error",
                "category": "goal",
                "message": (
                    f"Goal '{goal['name']}' is {pace.replace('_', ' ')} — "
                    f"need ~${goal.get('monthly_required') or 0:.0f}/mo to hit target"
                ),
                "link": "/finances/plan",
            })
    return out


def _credit_utilization_alerts() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    teller_accounts = state._balances_cache.get("teller_accounts", []) or []
    manual_accounts = list(state._manual_accounts.values())
    for acct in list(teller_accounts) + manual_accounts:
        if (acct.get("type") or "").lower() != "credit":
            continue
        details = state.account_details.get(acct.get("id") or "") or {}
        limit = details.get("credit_limit")
        try:
            limit_f = float(limit) if limit is not None else None
        except (TypeError, ValueError):
            limit_f = None
        if not limit_f or limit_f <= 0:
            continue
        balance = float(acct.get("ledger") or 0.0)
        pct = balance / limit_f * 100.0
        if pct < 50.0:
            continue
        sev = "error" if pct >= 80.0 else "warn"
        name = acct.get("name") or "Credit card"
        out.append({
            "severity": sev,
            "category": "credit",
            "message": f"{name} utilization at {pct:.0f}% — consider paying down",
            "link": "/finances/accounts",
        })
    return out


def _recurring_anomaly_alerts() -> List[Dict[str, Any]]:
    """Flag recurring charges where the latest amount diverges from the median.

    ``detect_recurring_charges`` returns the average and last_seen but not
    the per-charge series, so we re-derive medians inline using the same
    grouping key.
    """
    from analytics import _normalize_merchant, _parse_month_key  # noqa: WPS450

    by_key: Dict[str, List[Dict[str, Any]]] = {}
    for txn in state.stored_transactions.values():
        try:
            amount = float(txn.get("amount") or 0)
        except (TypeError, ValueError):
            continue
        if amount <= 0:
            continue
        if txn.get("transaction_type") != "debit" and not (
            txn.get("source") == "discover"
            and txn.get("transaction_type") == "credit"
        ):
            continue
        key = _normalize_merchant(txn.get("description", ""))
        if not key:
            continue
        date_str = txn.get("date", "")
        by_key.setdefault(key, []).append({
            "amount": amount,
            "date": date_str,
            "month": _parse_month_key(date_str) if date_str else "",
        })

    out: List[Dict[str, Any]] = []
    for entry in detect_recurring_charges():
        key = entry["merchant_key"]
        items = by_key.get(key, [])
        amounts = [i["amount"] for i in items]
        if len(amounts) < 2:
            continue
        # Latest by date.
        latest = max(items, key=lambda i: i["date"])
        median = statistics.median(amounts)
        if median <= 0:
            continue
        diff_pct = abs(latest["amount"] - median) / median * 100.0
        if diff_pct < 20.0:
            continue
        direction = "up" if latest["amount"] > median else "down"
        out.append({
            "severity": "info",
            "category": "recurring",
            "message": (
                f"{entry['sample_description'][:40]} charged ${latest['amount']:.2f} "
                f"({diff_pct:.0f}% {direction} vs. usual ${median:.2f})"
            ),
            "link": None,
        })
    return out


@router.get("/alerts")
async def list_alerts() -> Dict[str, Any]:
    alerts: List[Dict[str, Any]] = []
    alerts.extend(_budget_alerts())
    alerts.extend(_goal_alerts())
    alerts.extend(_credit_utilization_alerts())
    alerts.extend(_recurring_anomaly_alerts())

    severity_rank = {"error": 0, "warn": 1, "info": 2}
    alerts.sort(key=lambda a: severity_rank.get(a["severity"], 99))

    counts: Dict[str, int] = {"error": 0, "warn": 0, "info": 0}
    for a in alerts:
        counts[a["severity"]] = counts.get(a["severity"], 0) + 1

    return {"alerts": alerts, "counts": counts}
