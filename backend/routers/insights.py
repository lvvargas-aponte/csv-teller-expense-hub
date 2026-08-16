"""Insights routes: spending summary and forecast."""
import logging
import statistics
from datetime import date
from typing import Any, Dict

from fastapi import APIRouter

import state
from analytics import group_debit_spending
from llm_client import ask_ollama

logger = logging.getLogger(__name__)
router = APIRouter()


# Spending aggregation is deliberately NOT reimplemented here.
#
# This module used to carry private _parse_month_key and _group_debit_spending
# copies whose expense test predated analytics._is_expense. They ignored
# transfer-tagged transactions and _NON_SPENDING_CATEGORIES, so the forecast
# could disagree with the dashboard about the same month. Consolidated onto
# the canonical implementation, which was verified to produce identical
# totals on the existing data at the time of the change.


@router.post("/insights/spending-summary")
async def spending_summary() -> Dict[str, Any]:
    """Summarize spending by month/category and optionally enrich with a local LLM insight."""

    spending_by_month = group_debit_spending()
    sorted_months = sorted(spending_by_month.keys())[-6:]
    trimmed = {m: spending_by_month[m] for m in sorted_months}

    if not trimmed:
        return {
            "ai_available": False,
            "no_data": True,
            "spending_by_month": trimmed,
            "ai_summary": None,
        }

    # --- Build prompt ---
    lines = ["You are a personal finance assistant. Here is the user's spending history by category:\n"]
    for month in sorted_months:
        lines.append(f"[Month {month}]")
        for cat, total in sorted(trimmed[month].items(), key=lambda x: -x[1]):
            lines.append(f"  {cat}: ${total:.2f}")
        lines.append("")
    lines.append("Provide:")
    lines.append("1. A 2-3 sentence summary of recent spending patterns")
    lines.append("2. One specific savings opportunity")
    lines.append("3. A spending forecast for next month")
    lines.append("\nBe concise and specific. Use dollar amounts.")
    prompt_text = "\n".join(lines)

    result = await ask_ollama(prompt_text)
    return {
        "ai_available": result["ai_available"],
        "spending_by_month": trimmed,
        "ai_summary": result["text"],
    }


@router.get("/insights/forecast")
async def spending_forecast() -> Dict[str, Any]:
    """Forecast next month's spending per category using a weighted 3-month average."""

    spending_by_month = group_debit_spending()
    sorted_months = sorted(spending_by_month.keys())
    recent_3 = sorted_months[-3:]  # up to 3 most recent complete months

    # --- Collect all categories that appear in any of the 3 months ---
    all_categories: set[str] = set()
    for m in recent_3:
        all_categories.update(spending_by_month[m].keys())

    # --- Compute next calendar month ---
    today = date.today()
    if today.month == 12:
        forecast_date = date(today.year + 1, 1, 1)
    else:
        forecast_date = date(today.year, today.month + 1, 1)
    forecast_month = forecast_date.strftime("%Y-%m")

    w1, w2, w3 = state._FORECAST_WEIGHTS
    categories_out = []
    for cat in all_categories:
        m1 = spending_by_month.get(recent_3[-1], {}).get(cat, 0.0) if len(recent_3) >= 1 else 0.0
        m2 = spending_by_month.get(recent_3[-2], {}).get(cat, 0.0) if len(recent_3) >= 2 else 0.0
        m3 = spending_by_month.get(recent_3[-3], {}).get(cat, 0.0) if len(recent_3) >= 3 else 0.0

        predicted = m1 * w1 + m2 * w2 + m3 * w3
        available = [v for v in [m1, m2, m3] if v > 0]
        std_dev = statistics.pstdev(available) if available else 0.0
        low = max(0.0, predicted - std_dev)
        high = predicted + std_dev

        categories_out.append({
            "category": cat,
            "predicted": round(predicted, 2),
            "low": round(low, 2),
            "high": round(high, 2),
            "months_of_data": len(available),
        })

    categories_out.sort(key=lambda x: -x["predicted"])

    return {
        "forecast_month": forecast_month,
        "categories": categories_out,
    }
