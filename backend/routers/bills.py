"""Upcoming bills — thin HTTP layer.

The projection logic lives in ``backend/bills.py`` so the coach reasons
about due dates using the same code this page renders. Two implementations
would eventually disagree, and the user would have no way to tell which
answer to trust.
"""
from typing import Any, Dict

from fastapi import APIRouter

import bills as bills_domain

router = APIRouter()


@router.get("/bills/upcoming")
async def upcoming_bills(window_days: int = 30) -> Dict[str, Any]:
    return bills_domain.upcoming_bills(window_days=window_days)
