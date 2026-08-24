"""Weekly digest builder — composes signals the app already computes into
one reviewable summary: alerts, week-over-week spending, bills due in the
next 7 days, and subscription review flags, plus an optional Ollama-written
narrative (gracefully absent when Ollama is down).

Pure composition: every section reuses the canonical source (``collect_alerts``,
``upcoming_bills``, ``list_subscriptions``, ``_is_expense``) rather than
re-deriving its own numbers.
"""
import logging
from datetime import date, timedelta
from typing import Any, Dict, List

import state
from analytics import _is_expense, _parse_date_obj
from llm_client import ask_ollama

logger = logging.getLogger(__name__)

_TOP_CATEGORIES = 5
_MAX_ALERTS = 6


def _week_over_week_spending(today: date) -> Dict[str, Any]:
    this_start = today - timedelta(days=7)
    prior_start = today - timedelta(days=14)

    this_week = 0.0
    prior_week = 0.0
    by_category: Dict[str, float] = {}
    for txn in state.stored_transactions.values():
        if not _is_expense(txn):
            continue
        d = _parse_date_obj(txn.get("date", ""))
        if d is None or d < prior_start or d >= today:
            continue
        amount = float(txn.get("amount", 0))
        if d >= this_start:
            this_week += amount
            cat = txn.get("category") or "Uncategorized"
            by_category[cat] = by_category.get(cat, 0.0) + amount
        else:
            prior_week += amount

    change_pct = (
        round((this_week - prior_week) / prior_week * 100.0, 1)
        if prior_week > 0 else None
    )
    top = sorted(by_category.items(), key=lambda kv: -kv[1])[:_TOP_CATEGORIES]
    return {
        "this_week": round(this_week, 2),
        "prior_week": round(prior_week, 2),
        "change_pct": change_pct,
        "top_categories": [
            {"category": c, "amount": round(a, 2)} for c, a in top
        ],
    }


async def _narrative(payload: Dict[str, Any]) -> Dict[str, Any]:
    spend = payload["spending"]
    lines = [
        "You are a friendly household finance assistant. Write a 2-3 sentence "
        "weekly check-in based on these facts. Be specific with dollar amounts, "
        "warm but not salesy. No bullet points, no headings.",
        f"Spent this week: ${spend['this_week']:.2f} "
        f"(prior week ${spend['prior_week']:.2f}).",
    ]
    for c in spend["top_categories"][:3]:
        lines.append(f"Top category {c['category']}: ${c['amount']:.2f}.")
    for a in payload["alerts"][:3]:
        lines.append(f"Alert: {a['message']}.")
    if payload["subscriptions"]["needs_review_count"]:
        lines.append(
            f"{payload['subscriptions']['needs_review_count']} subscriptions "
            "are waiting for a keep/cancel review."
        )
    for b in payload["upcoming_bills"][:3]:
        lines.append(f"Bill due {b['due_date']}: {b['name']} (${b['balance']:.2f}).")
    return await ask_ollama("\n".join(lines))


async def build_digest() -> Dict[str, Any]:
    # Imported lazily: routers pull in the full app surface and this module
    # is imported by one of them.
    from routers.alerts import collect_alerts
    from routers.bills import upcoming_bills
    from routers.subscriptions import list_subscriptions

    today = date.today()
    alerts_feed = await collect_alerts()
    bills = (await upcoming_bills(window_days=7))["bills"]
    subs = await list_subscriptions()

    price_increases: List[Dict[str, Any]] = [
        {
            "merchant_key": s["merchant_key"],
            "sample_description": s["sample_description"],
            "price_change_pct": s["price_change_since_review_pct"] or s["price_change_pct"],
            "latest_amount": s["latest_amount"],
        }
        for s in subs["subscriptions"]
        if (s["price_change_since_review_pct"] or s["price_change_pct"]) >= 10.0
        and (s["review"] is None or s["review"]["decision"] != "ignore")
    ]

    payload: Dict[str, Any] = {
        "week_start": (today - timedelta(days=7)).isoformat(),
        "week_end": today.isoformat(),
        "spending": _week_over_week_spending(today),
        "alerts": alerts_feed["alerts"][:_MAX_ALERTS],
        "alert_counts": alerts_feed["counts"],
        "upcoming_bills": bills,
        "subscriptions": {
            "needs_review_count": subs["summary"]["needs_review_count"],
            "active_monthly_cost": subs["summary"]["active_monthly_cost"],
            "price_increases": price_increases,
        },
    }

    try:
        result = await _narrative(payload)
        payload["ai_available"] = result["ai_available"]
        payload["narrative"] = result["text"] if result["ai_available"] else None
    except Exception as e:  # Ollama down mid-call — digest still ships.
        logger.warning(f"[digest] narrative generation failed: {e}")
        payload["ai_available"] = False
        payload["narrative"] = None

    return payload