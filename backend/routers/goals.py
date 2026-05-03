"""Savings goal routes — named targets with optional account linkage.

Goals can be linked to an account (Teller or manual) so that progress reflects
the live ``available`` balance, or tracked manually via ``current_balance``.
The advisor consumes goals through ``build_financial_snapshot``.
"""
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, HTTPException

import state
from analytics import compute_goal_statuses
from models import Goal, GoalIn, GoalStatus

router = APIRouter()


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _validate(req: GoalIn) -> None:
    if not req.name.strip():
        raise HTTPException(status_code=422, detail="Goal name must not be empty")
    if req.target_amount <= 0:
        raise HTTPException(status_code=422, detail="target_amount must be > 0")
    if req.kind not in ("savings", "emergency_fund"):
        raise HTTPException(status_code=422, detail="kind must be 'savings' or 'emergency_fund'")


def _status_for(goal_id: str) -> GoalStatus:
    for status in compute_goal_statuses():
        if status["id"] == goal_id:
            return status
    raise HTTPException(status_code=500, detail="Goal saved but status not found")


@router.get("/goals", response_model=List[GoalStatus])
async def list_goals():
    """Return all goals with current_balance + progress attached."""
    return compute_goal_statuses()


@router.post("/goals", response_model=GoalStatus, status_code=201)
async def create_goal(req: GoalIn):
    """Create a new goal.  Returns the status-enriched view used by the UI."""
    _validate(req)

    goal_id = f"goal_{uuid.uuid4().hex[:12]}"
    state.goals[goal_id] = {
        "id":                goal_id,
        "name":              req.name.strip(),
        "target_amount":     float(req.target_amount),
        "target_date":       req.target_date,
        "linked_account_id": req.linked_account_id,
        "current_balance":   float(req.current_balance),
        "kind":              req.kind,
        "notes":             req.notes,
        "created":           _now_iso(),
        "updated":           _now_iso(),
    }
    state._goals_store.save()
    return _status_for(goal_id)


@router.put("/goals/{goal_id}", response_model=GoalStatus)
async def update_goal(goal_id: str, req: GoalIn):
    """Update an existing goal in place — preserves created timestamp."""
    if goal_id not in state.goals:
        raise HTTPException(status_code=404, detail="Goal not found")
    _validate(req)

    existing = state.goals[goal_id]
    state.goals[goal_id] = {
        "id":                goal_id,
        "name":              req.name.strip(),
        "target_amount":     float(req.target_amount),
        "target_date":       req.target_date,
        "linked_account_id": req.linked_account_id,
        "current_balance":   float(req.current_balance),
        "kind":              req.kind,
        "notes":             req.notes,
        "created":           existing.get("created", _now_iso()),
        "updated":           _now_iso(),
    }
    state._goals_store.save()
    return _status_for(goal_id)


@router.delete("/goals/{goal_id}", status_code=204)
async def delete_goal(goal_id: str):
    """Remove a goal permanently."""
    if goal_id not in state.goals:
        raise HTTPException(status_code=404, detail="Goal not found")
    del state.goals[goal_id]
    state._goals_store.save()
