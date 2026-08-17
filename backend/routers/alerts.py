"""Alerts router — a projection of the coach's rule set.

This endpoint used to carry its own copies of the budget, goal, credit-
utilization and recurring-charge rules. The coach later grew its own, and
the two drifted: the dashboard and the Today page could disagree about
whether a category was over budget, which is the kind of inconsistency that
makes a user stop trusting every other number in the app.

There is now one rule set, in ``coach.py``, and two presentations of it.
``/api/coach/actions`` returns the ranked, dollar-quantified form the Today
page renders; this returns the flat ``{severity, category, message, link}``
feed the dashboard's Alerts card was built against. The mapping lives in
``coach.build_alerts`` so this module holds no logic of its own.
"""
from typing import Any, Dict

from fastapi import APIRouter

import coach

router = APIRouter()


@router.get("/alerts")
async def list_alerts() -> Dict[str, Any]:
    return coach.build_alerts()
