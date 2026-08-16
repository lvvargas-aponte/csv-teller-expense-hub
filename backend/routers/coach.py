"""Coach routes — ranked next actions, optional narration, dismissals.

``/api/alerts`` stays exactly as it is; the AlertsCard depends on it. This
is an additive surface answering a different question: not "what's wrong?"
but "what should I do about it?".
"""
import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

import coach as coach_domain
import state
from llm_client import ask_ollama

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/coach/actions")
async def list_actions(
    limit: int = Query(coach_domain.DEFAULT_LIMIT, ge=1, le=30),
    as_of: Optional[str] = Query(None, description="ISO date; defaults to today"),
) -> Dict[str, Any]:
    """Ranked actions: what to do, how much, and by when."""
    parsed: Optional[date] = None
    if as_of:
        try:
            parsed = date.fromisoformat(as_of)
        except ValueError:
            raise HTTPException(status_code=422, detail="as_of must be ISO YYYY-MM-DD")
    return coach_domain.build_actions(today=parsed, limit=limit)


@router.post("/coach/narrate")
async def narrate(limit: int = Query(3, ge=1, le=5)) -> Dict[str, Any]:
    """Optional one-paragraph rewrite of the top actions.

    Voice only. The rules decide what matters, in what order, and for how
    much; this just reads them back in a sentence. Degrades to
    ``narration: null`` when Ollama isn't running, exactly like the other AI
    surfaces in this app.

    Any narration containing a number the rules didn't produce is discarded.
    A fabricated dollar figure the user then acts on is the worst outcome
    available here, and dropping the paragraph costs nothing.
    """
    payload = coach_domain.build_actions(limit=limit)
    actions = payload["actions"]
    if not actions:
        return {"ai_available": True, "narration": None, "actions": []}

    lines = [
        "You are a direct, practical financial coach. Below are the household's "
        "top priorities right now, already calculated.\n",
        "Summarize them in 2-3 sentences, in second person, as if talking to a "
        "friend who asked what to focus on.\n",
        "STRICT RULE: use ONLY the numbers given. Do not calculate, estimate, "
        "round differently, or introduce any figure not listed here.\n",
    ]
    for i, action in enumerate(actions, start=1):
        lines.append(f"{i}. {action['title']} — {action['detail']}")

    result = await ask_ollama("\n".join(lines))
    if not result["ai_available"]:
        return {"ai_available": False, "narration": None, "actions": actions}

    narration = (result["text"] or "").strip()
    if not coach_domain.verify_narration(narration, actions):
        logger.warning(
            "Discarding coach narration — it contained figures absent from the "
            "computed actions."
        )
        return {
            "ai_available": True,
            "narration": None,
            "narration_rejected": True,
            "actions": actions,
        }

    return {"ai_available": True, "narration": narration, "actions": actions}


@router.post("/coach/actions/{action_id}/dismiss", status_code=204)
async def dismiss_action(action_id: str) -> None:
    """Hide one action.

    Action ids embed the period they belong to, so dismissing
    ``over_budget:Dining:2026-08`` silences it for August only — September's
    equivalent has a different id and returns on its own.
    """
    state.coach_dismissals[action_id] = {
        "dismissed_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
    }


@router.delete("/coach/actions/{action_id}/dismiss", status_code=204)
async def undismiss_action(action_id: str) -> None:
    if action_id in state.coach_dismissals:
        del state.coach_dismissals[action_id]
