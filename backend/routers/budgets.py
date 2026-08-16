"""Budget routes — monthly per-category spending caps.

Budgets are keyed by category name (case-preserved on write, matched
case-insensitively against transaction categories at read time).  The list
endpoint returns each budget enriched with current-month spend so the UI and
advisor can show progress without recomputing.
"""
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

import state
from analytics import compute_budget_statuses, compute_safe_to_spend
from models import BudgetIn, BudgetStatus

router = APIRouter()


@router.get("/budgets/safe-to-spend")
async def safe_to_spend(
    as_of: Optional[str] = Query(
        None, description="ISO date; defaults to today. Used to show the delta vs. yesterday."
    ),
) -> Dict[str, Any]:
    """Today's and this week's discretionary allowance.

    Declared before ``/budgets/{category}`` so "safe-to-spend" isn't
    captured as a category name.

    Returns ``available: false`` when no income can be detected rather than
    inventing a figure from a guessed salary.
    """
    parsed: Optional[date] = None
    if as_of:
        try:
            parsed = date.fromisoformat(as_of)
        except ValueError:
            raise HTTPException(status_code=422, detail="as_of must be ISO YYYY-MM-DD")
    return compute_safe_to_spend(as_of=parsed)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


@router.get("/budgets", response_model=List[BudgetStatus])
async def list_budgets():
    """Return all budgets with current-month spend + percent_used attached."""
    return compute_budget_statuses()


@router.put("/budgets/{category}", response_model=BudgetStatus)
async def upsert_budget(category: str, req: BudgetIn):
    """Create or replace the budget for a category.

    Path ``category`` is the source of truth — the body's ``category`` field
    is ignored to avoid the path/body mismatch class of bugs.
    """
    if not category.strip():
        raise HTTPException(status_code=422, detail="Category must not be empty")
    if req.monthly_limit < 0:
        raise HTTPException(status_code=422, detail="monthly_limit must be >= 0")

    existing = state.budgets.get(category)
    state.budgets[category] = {
        "category":      category,
        "monthly_limit": float(req.monthly_limit),
        "notes":         req.notes,
        "created":       existing.get("created", _now_iso()) if existing else _now_iso(),
        "updated":       _now_iso(),
    }
    state._budgets_store.save()

    # Re-derive status (simpler than duplicating the spend-lookup logic here).
    for status in compute_budget_statuses():
        if status["category"] == category:
            return status
    raise HTTPException(status_code=500, detail="Budget saved but status not found")


@router.delete("/budgets/{category}", status_code=204)
async def delete_budget(category: str):
    """Remove the budget for a category."""
    if category not in state.budgets:
        raise HTTPException(status_code=404, detail="Budget not found")
    del state.budgets[category]
    state._budgets_store.save()
