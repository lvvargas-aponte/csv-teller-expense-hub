"""Alerts router — surfaces actionable warnings derived from existing analytics.

Rule-based, no LLM: composes budget statuses, goal pacing, credit
utilization, and recurring-charge anomalies into a single feed.  Severity
levels are advisory: ``info`` = nice to know, ``warn`` = attention soon,
``error`` = act now.
"""
from typing import Any, Dict, List

from fastapi import APIRouter

import credit_health_service
from analytics import (
    compute_budget_statuses,
    compute_goal_statuses,
    detect_recurring_charges,
    project_cashflow,
)

router = APIRouter()


def _budget_alerts() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for status in compute_budget_statuses():
        if not status.get("over_budget"):
            # Pacing over the cap fires while the month can still be changed;
            # 90%-of-cap is usually too late to act on.
            if status.get("pace_status") == "over_pace":
                out.append({
                    "severity": "warn",
                    "category": "budget",
                    "message": (
                        f"{status['category']} is pacing to "
                        f"${status['projected_month_end']:.0f} against a "
                        f"${status['monthly_limit']:.0f} cap"
                    ),
                    "tab": "budgets",
                })
                continue
            # Also warn at 90%+ of cap.
            if status.get("percent_used", 0.0) >= 90.0:
                out.append({
                    "severity": "warn",
                    "category": "budget",
                    "message": (
                        f"{status['category']} budget at {status['percent_used']:.0f}% "
                        f"(${status['current_month_spent']:.0f} / ${status['monthly_limit']:.0f})"
                    ),
                    "tab": "budgets",
                })
            continue
        out.append({
            "severity": "error",
            "category": "budget",
            "message": (
                f"{status['category']} over budget — spent ${status['current_month_spent']:.0f} "
                f"vs. ${status['monthly_limit']:.0f} cap"
            ),
            "tab": "budgets",
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
                "tab": "goals",
            })
    return out


async def _credit_utilization_alerts() -> List[Dict[str, Any]]:
    """Read the same composition the Credit Health card shows.

    This used to walk the account stores itself and take a manual account's
    *starting* ledger, so the feed could warn about a utilization no other
    screen agreed with. Cards with no limit and installment loans carry a
    null ``utilization_pct`` and drop out here.
    """
    out: List[Dict[str, Any]] = []
    composition = await credit_health_service.build()
    for row in composition["accounts"]:
        pct = row["utilization_pct"]
        if pct is None or pct < 50.0:
            continue
        sev = "error" if pct >= 80.0 else "warn"
        name = row["name"] or "Credit card"
        out.append({
            "severity": sev,
            "category": "credit",
            "message": f"{name} utilization at {pct:.0f}% — consider paying down",
            "tab": "accounts",
        })
    return out


def _recurring_anomaly_alerts() -> List[Dict[str, Any]]:
    """Flag recurring charges where the latest amount diverges from the median."""
    out: List[Dict[str, Any]] = []
    for entry in detect_recurring_charges():
        if entry["occurrences"] < 2:
            continue
        diff_pct = abs(entry["price_change_pct"])
        if diff_pct < 20.0:
            continue
        latest = entry["latest_amount"]
        usual = latest / (1 + entry["price_change_pct"] / 100.0)
        direction = "up" if entry["price_change_pct"] > 0 else "down"
        out.append({
            "severity": "info",
            "category": "recurring",
            "message": (
                f"{entry['sample_description'][:40]} charged ${latest:.2f} "
                f"({diff_pct:.0f}% {direction} vs. usual ${usual:.2f})"
            ),
            "tab": "commitments",
        })
    return out


def _cashflow_alerts() -> List[Dict[str, Any]]:
    """Warn once when the 30-day projection lands below zero.

    Phrased exactly as the outlook card phrases it — this is an estimate built
    from typical months, and hedging it in one place and not the other would
    read as two different claims.
    """
    projection = project_cashflow(horizon_days=30)
    net = projection.get("net") or 0.0
    if net >= 0:
        return []
    return [{
        "severity": "warn",
        "category": "cashflow",
        "message": (
            f"Spending is projected to exceed income by about ${abs(net):,.0f} "
            f"over the next {projection['horizon_days']} days"
        ),
        "tab": "dashboard",
    }]


async def collect_alerts() -> Dict[str, Any]:
    """Compose every alert source, sorted by severity. Shared with the
    weekly digest builder so both surfaces show the same feed."""
    alerts: List[Dict[str, Any]] = []
    alerts.extend(_budget_alerts())
    alerts.extend(_goal_alerts())
    alerts.extend(await _credit_utilization_alerts())
    alerts.extend(_recurring_anomaly_alerts())
    alerts.extend(_cashflow_alerts())

    severity_rank = {"error": 0, "warn": 1, "info": 2}
    alerts.sort(key=lambda a: severity_rank.get(a["severity"], 99))

    counts: Dict[str, int] = {"error": 0, "warn": 0, "info": 0}
    for a in alerts:
        counts[a["severity"]] = counts.get(a["severity"], 0) + 1

    return {"alerts": alerts, "counts": counts}


@router.get("/alerts")
async def list_alerts() -> Dict[str, Any]:
    return await collect_alerts()
