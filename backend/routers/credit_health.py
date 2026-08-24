"""Credit utilization endpoint — per-card balance vs. credit_limit.

Thin serializer over :func:`credit_health_service.build`, which the health
score reads as well.
"""
from typing import Any, Dict

from fastapi import APIRouter

import analytics
import credit_health_service

router = APIRouter()


@router.get("/accounts/credit-health")
async def credit_health() -> Dict[str, Any]:
    composition = await credit_health_service.build()
    # What the balances cost per month rides along: the card that shows
    # utilization is where "and it costs you $214/month" belongs.
    composition["carry_cost"] = await analytics.compute_carry_cost()
    return composition
